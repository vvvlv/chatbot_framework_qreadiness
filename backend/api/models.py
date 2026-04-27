"""API request/response models."""
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """Chat request model."""

    message: str = Field(min_length=1, max_length=4000)
    session_id: UUID
    prompt_id: Optional[str] = Field(default=None, max_length=128)
    selected_chatbot: Optional[str] = Field(default=None, max_length=64)
    context_message: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message cannot be empty")
        return normalized


class ChatResponse(BaseModel):
    """Chat response model (for non-streaming endpoints)."""

    message: str
    session_id: UUID
