"""
PostgreSQL checkpointer setup.

PostgreSQL serves as the single persistence layer for conversation checkpoints
and vector embeddings.
"""
import os

from langgraph.checkpoint.memory import InMemorySaver


async def get_checkpointer():
    """Get checkpointer for LangGraph state persistence."""
    database_url = os.getenv("DATABASE_URL")

    if database_url:
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            checkpointer = AsyncPostgresSaver.from_conn_string(database_url)
            await checkpointer.setup()
            print("✓ Using AsyncPostgresSaver for state persistence")
            return checkpointer
        except ImportError:
            print("⚠ langgraph-checkpoint-postgres not installed, using InMemorySaver")
        except Exception as e:
            print(f"⚠ Error setting up AsyncPostgresSaver: {e}, using InMemorySaver")

    print("⚠ Using InMemorySaver (state lost on restart)")
    return InMemorySaver()

