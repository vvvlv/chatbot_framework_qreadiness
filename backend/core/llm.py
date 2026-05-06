"""
LLM gateway wrapper.

All LLM calls go through this wrapper for consistent configuration.
"""
import os
from typing import Any, Dict, List, Optional

from core.model_gateway import ModelGateway

_model_gateway: Optional[ModelGateway] = None


def get_model_gateway() -> ModelGateway:
    """Get or create the global ModelGateway instance."""
    global _model_gateway
    if _model_gateway is None:
        default_model = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
        _model_gateway = ModelGateway(default_model=default_model)
    return _model_gateway


async def llm(messages: List[Dict[str, str]], stream: bool = False, **kwargs: Any) -> str:
    """Call LLM via ModelGateway (LiteLLM)."""
    gateway = get_model_gateway()
    return await gateway.chat(messages=messages, **kwargs)

