from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database import Base, Session as DbSession
from routes import session_routes


class FakeSession:
    def __init__(self, session_id, name, endpoint_url, model, rag, owner):
        self.id = session_id
        self.name = name
        self.endpoint_url = endpoint_url
        self.model = model
        self.rag = rag
        self.owner = owner
        self.headers = {}


class FakeSessionManager:
    def __init__(self):
        self.sessions = {}

    def create_session(self, session_id, name, endpoint_url, model, rag, owner):
        sess = FakeSession(session_id, name, endpoint_url, model, rag, owner)
        self.sessions[session_id] = sess
        db = session_routes.SessionLocal()
        try:
            db.add(DbSession(id=session_id, name=name, endpoint_url=endpoint_url, model=model, rag=rag, owner=owner))
            db.commit()
        finally:
            db.close()
        return sess

    def get_session(self, sid):
        return self.sessions[sid]


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    engine = create_engine(f"sqlite:///{tmp_path / 'sessions.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    monkeypatch.setattr(session_routes, "SessionLocal", TestingSession)
    app = FastAPI()
    app.include_router(session_routes.setup_session_routes(FakeSessionManager(), {"REQUEST_TIMEOUT": 1}))
    return TestClient(app), TestingSession


def test_create_session_persists_target_binding(tmp_path, monkeypatch):
    client, TestingSession = _client(tmp_path, monkeypatch)
    response = client.post("/api/session", data={
        "name": "Team chat",
        "endpoint_url": "http://example.test/v1/chat/completions",
        "model": "test-model",
        "skip_validation": "true",
        "target_type": "team",
        "target_id": "team-1",
    })
    assert response.status_code == 200
    sid = response.json()["id"]
    db = TestingSession()
    try:
        row = db.query(DbSession).filter(DbSession.id == sid).first()
        assert row.target_type == "team"
        assert row.target_id == "team-1"
        assert row.mode == "team"
    finally:
        db.close()
