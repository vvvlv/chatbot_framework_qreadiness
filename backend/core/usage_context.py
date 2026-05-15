"""Request-scoped context for LLM usage attribution."""
from contextvars import ContextVar
from typing import Optional

_session_id: ContextVar[Optional[str]] = ContextVar("usage_session_id", default=None)
_user_id: ContextVar[Optional[str]] = ContextVar("usage_user_id", default=None)
_caller: ContextVar[Optional[str]] = ContextVar("usage_caller", default=None)


def set_usage_context(
    *,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    caller: Optional[str] = None,
) -> None:
    if session_id is not None:
        _session_id.set(session_id)
    if user_id is not None:
        _user_id.set(user_id)
    if caller is not None:
        _caller.set(caller)


def get_usage_session_id() -> Optional[str]:
    return _session_id.get()


def get_usage_user_id() -> Optional[str]:
    return _user_id.get()


def get_usage_caller() -> Optional[str]:
    return _caller.get()


def clear_usage_context() -> None:
    _session_id.set(None)
    _user_id.set(None)
    _caller.set(None)
