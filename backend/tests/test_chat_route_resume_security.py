from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import chat as chat_routes


class FakeState:
    def __init__(self, suspended=True, pending_prompt_id=None):
        self.next = ("resume",) if suspended else ()
        self.values = {}
        if pending_prompt_id:
            self.values["pending_prompt_id"] = pending_prompt_id


class FakeGraph:
    async def aget_state(self, _config):
        return FakeState(suspended=True, pending_prompt_id="prompt-1")


def _build_app():
    app = FastAPI()
    app.include_router(chat_routes.router)
    app.state.graph = FakeGraph()
    return app


def test_rejects_stale_prompt_id_on_resume():
    app = _build_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/chat",
            json={
                "message": "resume content",
                "session_id": "123e4567-e89b-12d3-a456-426614174000",
                "prompt_id": "wrong-prompt",
            },
        )
    assert response.status_code == 409


def test_accepts_matching_prompt_id_on_resume(monkeypatch):
    async def fake_stream_graph_events(_graph, _input, _config, interaction_logger=None):
        yield 'data: {"type":"session_state","payload":{},"meta":{"session_id":"x"}}\n\n'

    monkeypatch.setattr(chat_routes, "stream_graph_events", fake_stream_graph_events)

    app = _build_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/chat",
            json={
                "message": "resume content",
                "session_id": "123e4567-e89b-12d3-a456-426614174000",
                "prompt_id": "prompt-1",
            },
        )
    assert response.status_code == 200

