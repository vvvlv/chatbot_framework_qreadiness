"""
Lightweight interaction event logging for runtime debugging.
This logger persists events in PostgreSQL for local observability and easy
inspection in tools like pgAdmin.
"""

import asyncio
import json
import os
from typing import Any, Dict, Optional

import asyncpg


def _postgres_dsn_from_env() -> str:
    """
    Resolve Postgres DSN from env.
    Priority:
    1) INTERACTION_LOG_DB_URL
    2) DATABASE_URL
    """
    raw = (
        os.getenv("INTERACTION_LOG_DB_URL", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
    )
    if not raw:
        raise RuntimeError(
            "Interaction logger requires Postgres DSN via INTERACTION_LOG_DB_URL or DATABASE_URL"
        )
    if not raw.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("Interaction logger only supports PostgreSQL DSNs")
    return raw


class InteractionLogger:
    """Async Postgres logger for interaction events."""

    def __init__(self, database_url: Optional[str] = None) -> None:
        self._database_url = database_url or _postgres_dsn_from_env()
        self._max_message_chars = int(os.getenv("INTERACTION_LOG_MAX_MESSAGE_CHARS", "4000"))
        self._max_payload_chars = int(os.getenv("INTERACTION_LOG_MAX_PAYLOAD_CHARS", "12000"))
        self._pool: Optional[asyncpg.Pool] = None
        self._pool_lock = asyncio.Lock()

    def _truncate(self, value: Optional[str], limit: int) -> Optional[str]:
        if value is None:
            return None
        if len(value) <= limit:
            return value
        return value[:limit] + " ...[truncated]"

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
                CREATE TABLE IF NOT EXISTS interaction_events (
                    id BIGSERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    app_name TEXT NULL,
                    tool_name TEXT NULL,
                    user_message TEXT NULL,
                    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb
                );
                """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_interactions_session ON interaction_events(session_id);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_interactions_event_type ON interaction_events(event_type);"
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_messages (
                    id BIGSERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    session_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    message TEXT NOT NULL,
                    is_resume BOOLEAN NOT NULL DEFAULT FALSE,
                    prompt_id TEXT NULL,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
                );
                """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_messages_session ON user_messages(session_id);"
            )

    async def log_event(
        self,
        *,
        session_id: str,
        event_type: str,
        user_id: str,
        app_name: Optional[str] = None,
        tool_name: Optional[str] = None,
        user_message: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        pool = await self._ensure_pool()
        payload_json = self._truncate(json.dumps(payload or {}, ensure_ascii=False), self._max_payload_chars)
        user_message = self._truncate(user_message, self._max_message_chars)
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO interaction_events (
                    session_id,
                    event_type,
                    user_id,
                    app_name,
                    tool_name,
                    user_message,
                    payload_json
                ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                """,
                session_id,
                event_type,
                user_id,
                app_name,
                tool_name,
                user_message,
                payload_json or "{}",
            )

    async def recent_events(
        self,
        *,
        limit: int = 100,
        session_id: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        limit = max(1, min(limit, 500))
        pool = await self._ensure_pool()
        if session_id:
            query = """
                SELECT id, created_at, session_id, event_type, user_id, app_name, tool_name, user_message, payload_json
                FROM interaction_events
                WHERE session_id = $1
                ORDER BY id DESC
                LIMIT $2
            """
            params = (session_id, limit)
        else:
            query = """
                SELECT id, created_at, session_id, event_type, user_id, app_name, tool_name, user_message, payload_json
                FROM interaction_events
                ORDER BY id DESC
                LIMIT $1
            """
            params = (limit,)

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        events = []
        for row in rows:
            payload = row["payload_json"] or {}
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = {"raw": payload}
            events.append(
                {
                    "id": row["id"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "session_id": row["session_id"],
                    "event_type": row["event_type"],
                    "user_id": row["user_id"],
                    "app_name": row["app_name"],
                    "tool_name": row["tool_name"],
                    "user_message": row["user_message"],
                    "payload": payload,
                }
            )
        return events

    async def log_user_message(
        self,
        *,
        session_id: str,
        user_id,
        message: str,
        is_resume: bool = False,
        prompt_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        pool = await self._ensure_pool()
        safe_message = self._truncate(message, self._max_message_chars) or ""
        payload_json = self._truncate(
            json.dumps(metadata or {}, ensure_ascii=False),
            self._max_payload_chars,
        )
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_messages (
                    session_id,
                    user_id,
                    message,
                    is_resume,
                    prompt_id,
                    metadata
                ) VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                """,
                session_id,
                user_id,
                safe_message,
                is_resume,
                prompt_id,
                payload_json or "{}",
            )

    async def close(self) -> None:
        """Close DB pool gracefully."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None