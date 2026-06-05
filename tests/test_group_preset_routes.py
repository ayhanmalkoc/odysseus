from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.preset_routes import setup_preset_routes


class FakePresetManager:
    def __init__(self):
        self.presets = {"group_presets": []}

    def get_group_presets(self):
        return list(self.presets.get("group_presets", []))

    def save_group_presets(self, groups):
        self.presets["group_presets"] = list(groups)
        return True

    def get_user_templates(self):
        return []


def _client(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    app = FastAPI()
    manager = FakePresetManager()
    app.include_router(setup_preset_routes(manager))
    return TestClient(app), manager


def test_group_preset_crud_validates_schema(monkeypatch):
    client, manager = _client(monkeypatch)
    payload = {
        "name": "Research Team",
        "lead_crew_member_id": "lead-1",
        "members": [
            {"crew_member_id": "worker-1", "role": "researcher", "order": 1},
            {"crew_member_id": "worker-1", "role": "duplicate", "order": 2},
        ],
        "topology": "lead_routed",
        "run_config": {"max_steps": 6, "parallel": False, "show_activity": True},
    }
    created = client.post("/api/presets/groups", json=payload)
    assert created.status_code == 200
    group = created.json()["group"]
    assert group["id"].startswith("group-")
    assert group["members"] == [{"crew_member_id": "worker-1", "role": "researcher", "order": 1, "enabled": True}]

    fetched = client.get(f"/api/presets/groups/{group['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["group"]["name"] == "Research Team"

    updated_payload = {**payload, "id": "ignored", "name": "Review Team", "topology": "sequential_pipeline"}
    updated = client.patch(f"/api/presets/groups/{group['id']}", json=updated_payload)
    assert updated.status_code == 200
    assert updated.json()["group"]["id"] == group["id"]
    assert updated.json()["group"]["topology"] == "sequential_pipeline"

    invalid = client.post("/api/presets/groups", json={**payload, "topology": "graph"})
    assert invalid.status_code == 422

    deleted = client.delete(f"/api/presets/groups/{group['id']}")
    assert deleted.status_code == 200
    assert manager.get_group_presets() == []


def test_legacy_replace_all_groups(monkeypatch):
    client, manager = _client(monkeypatch)
    response = client.post("/api/presets/groups", json={"groups": [{
        "id": "team-a",
        "name": "Team A",
        "lead_crew_member_id": "lead",
        "members": [],
    }]})
    assert response.status_code == 200
    assert manager.get_group_presets()[0]["id"] == "team-a"
