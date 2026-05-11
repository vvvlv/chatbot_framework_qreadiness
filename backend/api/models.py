"""API request/response models."""
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """Chat request model."""

    message: str = Field(min_length=1, max_length=4000)
    session_id: UUID
    prompt_id: Optional[str] = Field(default=None, max_length=128)

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
    # TODO : add error field ?


class Feedback(BaseModel):
    user_id: UUID
    timestamp: int
    title: str
    output: str

# TODO : define other models ? What models ?
#       - a base model for unspecific requests ?
#       - request for tools (eg RAG tool) ?
#       - request for deleting message list
#       - or for creating a new conversation