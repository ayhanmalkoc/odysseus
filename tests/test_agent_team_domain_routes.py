from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database import Base, CrewMember, AgentTeam, AgentRun, AgentRunStep
from routes import agent_routes, agent_persona_routes, agent_role_routes, agent_team_routes, agent_run_routes


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    engine = create_engine(f"sqlite:///{tmp_path / 'agent_team_domain.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    for module in (agent_routes, agent_persona_routes, agent_role_routes, agent_team_routes, agent_run_routes):
        monkeypatch.setattr(module, "SessionLocal", TestingSession)
    app = FastAPI()
    app.include_router(agent_routes.setup_agent_routes())
    app.include_router(agent_persona_routes.setup_agent_persona_routes())
    app.include_router(agent_role_routes.setup_agent_role_routes())
    app.include_router(agent_team_routes.setup_agent_team_routes())
    app.include_router(agent_run_routes.setup_agent_run_routes())
    return TestClient(app), TestingSession


def test_agent_persona_role_team_crud(tmp_path, monkeypatch):
    client, TestingSession = _client(tmp_path, monkeypatch)

    persona = client.post("/api/agent-personas", json={"name": "Architect", "system_prompt": "Think structurally."})
    assert persona.status_code == 200
    assert persona.json()["persona"]["name"] == "Architect"

    role = client.post("/api/agent-roles", json={"name": "planner", "description": "Plans work"})
    assert role.status_code == 200
    assert role.json()["role"]["name"] == "planner"

    lead = client.post("/api/agents", json={"name": "Lead", "personality": "Lead the team."}).json()["agent"]
    worker = client.post("/api/agents", json={"name": "Worker", "personality": "Execute."}).json()["agent"]

    created = client.post("/api/agent-teams", json={
        "name": "Build Team",
        "description": "Ships features",
        "leader_agent_id": lead["id"],
        "topology": "lead_routed",
        "members": [{"agent_id": worker["id"], "role": "planner", "sort_order": 1}],
        "run_policy": {"max_steps": 4},
    })
    assert created.status_code == 200
    team = created.json()["team"]
    assert team["leader"]["name"] == "Lead"
    assert team["members"][0]["agent"]["name"] == "Worker"

    patched = client.patch(f"/api/agent-teams/{team['id']}", json={"name": "Build Team 2", "members": []})
    assert patched.status_code == 200
    assert patched.json()["team"]["members"] == []

    cloned = client.post(f"/api/agent-teams/{team['id']}/clone")
    assert cloned.status_code == 200
    assert cloned.json()["team"]["name"] == "Build Team 2 Copy"

    archived = client.delete(f"/api/agent-teams/{team['id']}")
    assert archived.status_code == 200
    assert client.get("/api/agent-teams").json()["teams"][0]["id"] != team["id"]

    db = TestingSession()
    try:
        row = db.query(AgentTeam).filter(AgentTeam.id == team["id"]).first()
        assert row.is_active is False
    finally:
        db.close()


def test_agent_run_routes_return_timeline(tmp_path, monkeypatch):
    client, TestingSession = _client(tmp_path, monkeypatch)
    db = TestingSession()
    try:
        run = AgentRun(id="run-1", owner="", session_id=None, target_type="team", target_id="team-1", status="completed", input="q", output="a")
        db.add(run)
        db.add(AgentRunStep(id="step-1", run_id="run-1", sort_order=1, step_type="leader_plan", title="Plan", content="Do it"))
        db.commit()
    finally:
        db.close()

    listed = client.get("/api/agent-runs?target_id=team-1")
    assert listed.status_code == 200
    assert listed.json()["runs"][0]["id"] == "run-1"

    detail = client.get("/api/agent-runs/run-1")
    assert detail.status_code == 200
    assert detail.json()["run"]["steps"][0]["step_type"] == "leader_plan"
