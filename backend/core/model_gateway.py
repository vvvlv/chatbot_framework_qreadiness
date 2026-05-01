"""
Model gateway abstraction for LLM calls.

All LLM calls go through LiteLLM via this gateway.
"""
import os
from typing import Any, Dict, List, Optional

import litellm
from dotenv import load_dotenv

load_dotenv()
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "true"


class ModelGateway:
    """LiteLLM-based model gateway."""

    def __init__(self, default_model: str = "mistral/mistral-small-latest") -> None:
        self.default_model = default_model
        self._bootstrap_provider_env()

    def _bootstrap_provider_env(self) -> None:
        # Mirror upper-case keys to provider specific ones when needed
        if os.getenv("MISTRAL_API_KEY") and not os.getenv("mistral_api_key"):
            os.environ["mistral_api_key"] = os.environ["MISTRAL_API_KEY"]

    def _has_api_key(self) -> bool:
        possible_keys = [
            "MISTRAL_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "AZURE_OPENAI_API_KEY",
            "GROQ_API_KEY",
            "COHERE_API_KEY",
        ]
        return any(os.getenv(k) for k in possible_keys)

    def _resolve_model(self, model: Optional[str]) -> str:
        return model or os.getenv("LLM_MODEL", self.default_model)

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        if not self._has_api_key():
            return (
                "LLM is not configured; using a generic narrative. "
                "Set an appropriate API key in your .env (e.g., MISTRAL_API_KEY) "
                "to enable model-generated text."
            )
        chosen_model = self._resolve_model(model)
        try:
            resp = await litellm.acompletion(model=chosen_model, messages=messages, **kwargs)
            return resp["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[ModelGateway] Error: {e}")
            return (
                "LLM call failed; using a generic narrative instead. "
                "Check LiteLLM configuration if you want richer text here."
            )