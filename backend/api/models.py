"""
API request/response models.

According to app_definition.md Section 12, API models should be defined here.
"""
from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Chat request model."""
    message: str
    session_id: str


class ChatResponse(BaseModel):
    """Chat response model (for non-streaming endpoints)."""
    message: str
    session_id: str
