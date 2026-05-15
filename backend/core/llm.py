"""
LLM gateway wrapper.

All LLM calls go through this wrapper for consistent configuration.
"""
import os
from typing import Any, Dict, List, Optional

from core.model_gateway import ModelGateway
from core.usage_tracker import UsageTracker

_model_gateway: Optional[ModelGateway] = None


def configure_model_gateway(usage_tracker: Optional[UsageTracker] = None) -> ModelGateway:
    """Create or replace the global ModelGateway (optionally with usage tracking)."""
    global _model_gateway
    default_model = (
        os.getenv("LITELLM_DEFAULT_MODEL", "").strip()
        or os.getenv("LLM_MODEL", "").strip()
        or "claude-haiku-4-5"
    )
    _model_gateway = ModelGateway(
        default_model=default_model,
        usage_tracker=usage_tracker,
    )
    return _model_gateway


def get_model_gateway() -> ModelGateway:
    """Get or create the global ModelGateway instance."""
    global _model_gateway
    if _model_gateway is None:
        return configure_model_gateway()
    return _model_gateway


async def llm(messages: List[Dict[str, str]], stream: bool = False, **kwargs: Any) -> str:
    """Call LLM via ModelGateway (LiteLLM)."""
    gateway = get_model_gateway()
    return await gateway.chat(messages=messages, **kwargs)

