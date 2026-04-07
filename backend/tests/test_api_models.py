from pydantic import ValidationError

from api.models import ChatRequest


def test_chat_request_requires_uuid_session_id():
    try:
        ChatRequest(message="hello", session_id="not-a-uuid")
        assert False, "Expected validation error for invalid UUID"
    except ValidationError:
        assert True


def test_chat_request_trims_and_rejects_empty_message():
    try:
        ChatRequest(message="   ", session_id="123e4567-e89b-12d3-a456-426614174000")
        assert False, "Expected validation error for empty message"
    except ValidationError:
        assert True

