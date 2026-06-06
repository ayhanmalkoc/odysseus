from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.preset_routes import setup_preset_routes


class FakePresetManager:
    def get_user_templates(self):
        return []


def _client(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    app = FastAPI()
    app.include_router(setup_preset_routes(FakePresetManager()))
    return TestClient(app)


def test_legacy_group_preset_routes_are_removed(monkeypatch):
    client = _client(monkeypatch)
    assert client.get("/api/presets/groups").status_code == 410
    assert client.post("/api/presets/groups", json={"groups": []}).status_code == 410
    assert client.get("/api/presets/groups/team-a").status_code == 410
    assert client.patch("/api/presets/groups/team-a", json={"name": "x", "lead_crew_member_id": "lead", "members": []}).status_code == 410
    assert client.delete("/api/presets/groups/team-a").status_code == 410
