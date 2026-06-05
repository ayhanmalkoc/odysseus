import os

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database import Base, CrewMember
from routes import agent_routes


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    engine = create_engine(f"sqlite:///{tmp_path / 'agents.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    monkeypatch.setattr(agent_routes, "SessionLocal", TestingSession)
    app = FastAPI()
    app.include_router(agent_routes.setup_agent_routes())
    return TestClient(app), TestingSession


def test_agent_crud_archive_and_clone(tmp_path, monkeypatch):
    client, TestingSession = _client(tmp_path, monkeypatch)

    created = client.post("/api/agents", json={
        "name": "Researcher",
        "personality": "Find facts.",
        "model": "m1",
        "endpoint_url": "http://llm.local/v1",
        "enabled_tools": ["web_search", "web_search", "read_file"],
    })
    assert created.status_code == 200
    agent = created.json()["agent"]
    assert agent["name"] == "Researcher"
    assert agent["enabled_tools"] == ["web_search", "read_file"]

    listed = client.get("/api/agents")
    assert listed.status_code == 200
    assert [a["id"] for a in listed.json()["agents"]] == [agent["id"]]

    updated = client.patch(f"/api/agents/{agent['id']}", json={"name": "Senior Researcher", "is_active": True})
    assert updated.status_code == 200
    assert updated.json()["agent"]["name"] == "Senior Researcher"

    cloned = client.post(f"/api/agents/{agent['id']}/clone")
    assert cloned.status_code == 200
    assert cloned.json()["agent"]["name"] == "Senior Researcher Copy"

    deleted = client.delete(f"/api/agents/{agent['id']}")
    assert deleted.status_code == 200
    assert deleted.json() == {"success": True, "archived": True}
    assert all(a["id"] != agent["id"] for a in client.get("/api/agents").json()["agents"])
    assert any(a["id"] == agent["id"] for a in client.get("/api/agents?include_inactive=true").json()["agents"])

    db = TestingSession()
    try:
        row = db.query(CrewMember).filter(CrewMember.id == agent["id"]).first()
        assert row is not None
        assert row.is_active is False
    finally:
        db.close()


def test_default_assistant_cannot_be_archived(tmp_path, monkeypatch):
    client, TestingSession = _client(tmp_path, monkeypatch)
    db = TestingSession()
    try:
        db.add(CrewMember(id="default", owner="", name="Assistant", is_default_assistant=True, is_active=True))
        db.commit()
    finally:
        db.close()

    response = client.delete("/api/agents/default")
    assert response.status_code == 400
