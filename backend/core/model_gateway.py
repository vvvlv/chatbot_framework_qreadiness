"""
Model gateway abstraction for LLM calls.

All LLM calls go through LiteLLM. When LITELLM_BASE_URL and LITELLM_API_KEY are set,
requests are routed to the shared LiteLLM proxy (OpenAI-compatible API).
Otherwise, direct provider keys are used (local development).
"""
import os
from typing import Any, Dict, List, Optional

import litellm
from dotenv import load_dotenv

from core.usage_context import get_usage_caller, get_usage_session_id, get_usage_user_id

load_dotenv()
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "true"


class ModelGateway:
    """LiteLLM-based model gateway."""

    def __init__(
        self,
        default_model: str = "claude-haiku-4-5",
        usage_tracker: Optional[Any] = None,
    ) -> None:
        self.default_model = default_model
        self._usage_tracker = usage_tracker
        self._bootstrap_provider_env()

    def _bootstrap_provider_env(self) -> None:
        if os.getenv("MISTRAL_API_KEY") and not os.getenv("mistral_api_key"):
            os.environ["mistral_api_key"] = os.environ["MISTRAL_API_KEY"]

    @staticmethod
    def uses_litellm_proxy() -> bool:
        return bool(
            os.getenv("LITELLM_BASE_URL", "").strip()
            and os.getenv("LITELLM_API_KEY", "").strip()
        )

    @staticmethod
    def litellm_api_base() -> str:
        base = os.environ["LITELLM_BASE_URL"].strip().rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        return base

    def _has_api_key(self) -> bool:
        if self.uses_litellm_proxy():
            return True
        possible_keys = [
            "LITELLM_API_KEY",
            "MISTRAL_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "AZURE_OPENAI_API_KEY",
            "GROQ_API_KEY",
            "COHERE_API_KEY",
        ]
        return any(os.getenv(k) for k in possible_keys)

    def _resolve_model(self, model: Optional[str]) -> str:
        if model:
            return model
        return (
            os.getenv("LITELLM_DEFAULT_MODEL", "").strip()
            or os.getenv("LLM_MODEL", "").strip()
            or self.default_model
        )

    def _completion_kwargs(self) -> Dict[str, Any]:
        if not self.uses_litellm_proxy():
            return {}
        return {
            "api_base": self.litellm_api_base(),
            "api_key": os.environ["LITELLM_API_KEY"],
        }

    async def _record_usage(
        self,
        *,
        response: Any,
        model: str,
        usage_caller: Optional[str] = None,
    ) -> None:
        if self._usage_tracker is None:
            return
        try:
            await self._usage_tracker.log_completion(
                response=response,
                model=model,
                session_id=get_usage_session_id(),
                user_id=get_usage_user_id(),
                caller=usage_caller or get_usage_caller() or "model_gateway",
            )
        except Exception as exc:
            print(f"[ModelGateway] Usage tracking failed: {exc}")

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        usage_caller: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        if not self._has_api_key():
            return (
                "LLM is not configured; using a generic narrative. "
                "Set LITELLM_BASE_URL + LITELLM_API_KEY (proxy) or a provider API key in .env."
            )
        chosen_model = self._resolve_model(model)
        completion_kwargs = {**self._completion_kwargs(), **kwargs}
        try:
            resp = await litellm.acompletion(
                model=chosen_model,
                messages=messages,
                **completion_kwargs,
            )
            await self._record_usage(
                response=resp, model=chosen_model, usage_caller=usage_caller
            )
            return resp["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[ModelGateway] Error: {e}")
            return (
                "LLM call failed; using a generic narrative instead. "
                "Check LiteLLM proxy configuration if you want richer text here."
            )
