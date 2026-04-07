import pytest
import asyncio

from core.checkpointer import get_checkpointer


def test_checkpointer_fails_in_prod_without_database(monkeypatch):
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError):
        asyncio.run(get_checkpointer())

