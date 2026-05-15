"""
LLM usage tracking backed by LiteLLM token/cost metadata and PostgreSQL.

Stores one row per completion for timeframe queries, per-session totals, and aggregates.
"""
import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import asyncpg
import litellm


def _postgres_dsn_from_env() -> str:
    raw = (
        os.getenv("USAGE_TRACKER_DB_URL", "").strip()
        or os.getenv("INTERACTION_LOG_DB_URL", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
    )
    if not raw:
        raise RuntimeError(
            "Usage tracker requires Postgres DSN via USAGE_TRACKER_DB_URL, "
            "INTERACTION_LOG_DB_URL, or DATABASE_URL"
        )
    if not raw.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("Usage tracker only supports PostgreSQL DSNs")
    return raw


def extract_usage_from_response(response: Any, model: str) -> Dict[str, Any]:
    """Read token usage and estimated cost from a LiteLLM completion response."""
    usage_raw: Dict[str, Any] = {}
    if isinstance(response, dict):
        usage_raw = response.get("usage") or {}
    elif hasattr(response, "usage") and response.usage is not None:
        usage = response.usage
        if hasattr(usage, "model_dump"):
            usage_raw = usage.model_dump()
        else:
            usage_raw = {
                "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                "completion_tokens": getattr(usage, "completion_tokens", 0),
                "total_tokens": getattr(usage, "total_tokens", 0),
            }

    prompt_tokens = int(usage_raw.get("prompt_tokens") or 0)
    completion_tokens = int(usage_raw.get("completion_tokens") or 0)
    total_tokens = int(usage_raw.get("total_tokens") or (prompt_tokens + completion_tokens))

    cost_usd = 0.0
    try:
        cost_usd = float(litellm.completion_cost(completion_response=response, model=model))
    except Exception:
        cost_usd = 0.0

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_usd": cost_usd,
    }


class UsageTracker:
    """Async Postgres logger for per-call LLM usage."""

    def __init__(self, database_url: Optional[str] = None) -> None:
        self._database_url = database_url or _postgres_dsn_from_env()
        self._pool: Optional[asyncpg.Pool] = None
        self._pool_lock = asyncio.Lock()

    async def _ensure_pool(self) -> asyncpg.Pool:
        if self._pool is not None:
            return self._pool
        async with self._pool_lock:
            if self._pool is None:
                self._pool = await asyncpg.create_pool(
                    dsn=self._database_url,
                    min_size=1,
                    max_size=10,
                )
                await self._init_schema()
        return self._pool

    async def _init_schema(self) -> None:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_usage_events (
                    id BIGSERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    session_id TEXT NULL,
                    user_id TEXT NULL,
                    model TEXT NOT NULL,
                    caller TEXT NULL,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
                );
                """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_llm_usage_created_at ON llm_usage_events(created_at);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_llm_usage_session_id ON llm_usage_events(session_id);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_llm_usage_user_id ON llm_usage_events(user_id);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_llm_usage_model ON llm_usage_events(model);"
            )

    async def log_completion(
        self,
        *,
        response: Any,
        model: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        caller: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        usage = extract_usage_from_response(response, model)
        pool = await self._ensure_pool()
        payload = json.dumps(metadata or {}, ensure_ascii=False)
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO llm_usage_events (
                    session_id,
                    user_id,
                    model,
                    caller,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    cost_usd,
                    metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
                """,
                session_id,
                user_id,
                model,
                caller,
                usage["prompt_tokens"],
                usage["completion_tokens"],
                usage["total_tokens"],
                usage["cost_usd"],
                payload,
            )

    async def get_stats(
        self,
        *,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        pool = await self._ensure_pool()
        where_parts = ["1=1"]
        params: List[Any] = []
        idx = 1

        if session_id:
            where_parts.append(f"session_id = ${idx}")
            params.append(session_id)
            idx += 1
        if user_id:
            where_parts.append(f"user_id = ${idx}")
            params.append(user_id)
            idx += 1
        if start:
            where_parts.append(f"created_at >= ${idx}")
            params.append(start)
            idx += 1
        if end:
            where_parts.append(f"created_at <= ${idx}")
            params.append(end)
            idx += 1

        where_sql = " AND ".join(where_parts)

        async with pool.acquire() as conn:
            totals = await conn.fetchrow(
                f"""
                SELECT
                    COUNT(*)::bigint AS requests,
                    COALESCE(SUM(prompt_tokens), 0)::bigint AS prompt_tokens,
                    COALESCE(SUM(completion_tokens), 0)::bigint AS completion_tokens,
                    COALESCE(SUM(total_tokens), 0)::bigint AS total_tokens,
                    COALESCE(SUM(cost_usd), 0)::float AS cost_usd
                FROM llm_usage_events
                WHERE {where_sql}
                """,
                *params,
            )

            by_session = await conn.fetch(
                f"""
                SELECT
                    COALESCE(session_id, 'unknown') AS session_id,
                    COUNT(*)::bigint AS requests,
                    COALESCE(SUM(total_tokens), 0)::bigint AS total_tokens,
                    COALESCE(SUM(cost_usd), 0)::float AS cost_usd,
                    MIN(created_at) AS first_seen,
                    MAX(created_at) AS last_seen
                FROM llm_usage_events
                WHERE {where_sql}
                GROUP BY session_id
                ORDER BY cost_usd DESC
                LIMIT {max(1, min(limit, 500))}
                """,
                *params,
            )

            by_model = await conn.fetch(
                f"""
                SELECT
                    model,
                    COUNT(*)::bigint AS requests,
                    COALESCE(SUM(total_tokens), 0)::bigint AS total_tokens,
                    COALESCE(SUM(cost_usd), 0)::float AS cost_usd
                FROM llm_usage_events
                WHERE {where_sql}
                GROUP BY model
                ORDER BY cost_usd DESC
                """,
                *params,
            )

            by_day = await conn.fetch(
                f"""
                SELECT
                    date_trunc('day', created_at) AS day,
                    COUNT(*)::bigint AS requests,
                    COALESCE(SUM(total_tokens), 0)::bigint AS total_tokens,
                    COALESCE(SUM(cost_usd), 0)::float AS cost_usd
                FROM llm_usage_events
                WHERE {where_sql}
                GROUP BY day
                ORDER BY day ASC
                """,
                *params,
            )

            recent = await conn.fetch(
                f"""
                SELECT
                    id,
                    created_at,
                    session_id,
                    user_id,
                    model,
                    caller,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    cost_usd
                FROM llm_usage_events
                WHERE {where_sql}
                ORDER BY id DESC
                LIMIT {max(1, min(limit, 500))}
                """,
                *params,
            )

        return {
            "timeframe": {
                "start": start.isoformat() if start else None,
                "end": end.isoformat() if end else None,
            },
            "filters": {
                "session_id": session_id,
                "user_id": user_id,
            },
            "totals": dict(totals) if totals else {},
            "by_session": [dict(row) for row in by_session],
            "by_model": [dict(row) for row in by_model],
            "by_day": [
                {
                    **dict(row),
                    "day": row["day"].isoformat() if row["day"] else None,
                }
                for row in by_day
            ],
            "recent_events": [
                {
                    **dict(row),
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                }
                for row in recent
            ],
        }

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
