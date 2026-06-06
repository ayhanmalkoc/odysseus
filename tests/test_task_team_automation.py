import anyio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database import Base, ChatMessage, ScheduledTask, Session as DbSession
from routes import task_routes
from src import agent_team_runner
from src.task_scheduler import TaskScheduler


class FakePresetManager:
    def get_group_presets(self):
        return [{"id": "team-1", "name": "Team", "lead_crew_member_id": "lead", "members": [], "topology": "lead_routed"}]


class FakeSessionManager:
    def __init__(self):
        self.sessions = {}

    def _db_to_session(self, sess):
        return sess

    def get_session(self, sid):
        return self.sessions[sid]


def _setup_db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'tasks.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    monkeypatch.setattr(task_routes, "SessionLocal", TestingSession)
    return TestingSession


def test_task_api_persists_group_preset_id(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    TestingSession = _setup_db(tmp_path, monkeypatch)
    scheduler = TaskScheduler(FakeSessionManager(), preset_manager=FakePresetManager())
    app = FastAPI()
    app.include_router(task_routes.setup_task_routes(scheduler))
    client = TestClient(app)

    created = client.post("/api/tasks", json={
        "name": "Team task",
        "prompt": "Do team work",
        "task_type": "llm",
        "schedule": "once",
        "scheduled_date": "2099-01-01T00:00:00Z",
        "target_type": "team",
            "target_id": "team-1",
    })
    assert created.status_code == 200
    assert created.json()["target_type"] == "team"
    assert created.json()["target_id"] == "team-1"
    task_id = created.json()["id"]

    updated = client.put(f"/api/tasks/{task_id}", json={"target_type": "team", "target_id": "team-2"})
    assert updated.status_code == 200
    assert updated.json()["target_type"] == "team"
    assert updated.json()["target_id"] == "team-2"

    db = TestingSession()
    try:
        row = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
        assert row.target_type == "team"
        assert row.target_id == "team-2"
    finally:
        db.close()


def test_scheduler_team_task_uses_team_runner_and_delivers_metadata(tmp_path, monkeypatch):
    TestingSession = _setup_db(tmp_path, monkeypatch)
    monkeypatch.setattr(agent_team_runner, "SessionLocal", TestingSession)

    async def fake_runner(**kwargs):
        return agent_team_runner.TeamRunResult(
            response="Team final",
            metadata={"team_run": True, "team_id": "team-1", "plan": "Plan", "workers": []},
        )

    monkeypatch.setattr(agent_team_runner, "run_lead_routed_team", fake_runner)
    scheduler = TaskScheduler(FakeSessionManager(), preset_manager=FakePresetManager())
    db = TestingSession()
    try:
        task = ScheduledTask(id="task-1", owner="", name="Team task", prompt="Do team work", task_type="llm", endpoint_url="base-url", model="base-model", group_preset_id="team-1", output_target="session")
        db.add(task)
        db.commit()
        result = anyio.run(scheduler._execute_llm_task, task, db)
        assert result == "Team final"
        scheduler._deliver_task_result_sync = None
        anyio.run(scheduler._deliver_task_result, task, result, db, "base-model")
        session = db.query(DbSession).filter(DbSession.id == task.session_id).first()
        assert session.group_preset_id == "team-1"
        assistant = db.query(ChatMessage).filter(ChatMessage.session_id == task.session_id, ChatMessage.role == "assistant").first()
        assert assistant is not None
        assert "team_run" in (assistant.meta_data or "")
    finally:
        db.close()
