import os
import asyncio
from typing import Any, Dict, Optional
import asyncpg

from api.models import Feedback

def _postgres_dsn_from_env() -> str:
    """
    Resolve Postgres DSN from env.
    """
    raw = os.getenv("DATABASE_URL", "").strip()
    if not raw:
        raise RuntimeError(
            "Feedback logger requires Postgres DSN via DATABASE_URL"
        )
    if not raw.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("Feedback logger only supports PostgreSQL DSNs")
    return raw

class FeedbackLogger:
    """Async Postgres logger for user feedbacks"""

    def __init__(self, database_url: Optional[str] = None) -> None:
        self._database_url = database_url or _postgres_dsn_from_env()
        self._max_feedback_chars = int(os.getenv("FEEDBACK_LOG_MAX_FEEDBACK_CHARS", "12000"))
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
                CREATE TABLE IF NOT EXISTS feedbacks (
                    id BIGSERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    user_id TEXT NOT NULL,
                    section TEXT NOT NULL,
                    feedback TEXT NULL
                );
                """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_feedback_session ON feedbacks(user_id);"
            )
    
    async def log_feedback(
        self,
        feedbacks: list[Feedback],
    ) -> None:
        pool = await self._ensure_pool()
        for feedback in feedbacks:
            if feedback.title == "Additional Comments":
                feedback.output = self._truncate(feedback.output, self._max_feedback_chars)
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO feedbacks (
                        user_id,
                        section,
                        feedback
                    ) VALUES ($1, $2, $3)
                    """,
                    str(feedback.user_id),
                    feedback.title,
                    feedback.output,
                )