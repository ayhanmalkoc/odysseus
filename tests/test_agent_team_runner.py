from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database import Base, CrewMember, Session as DbSession
from src import agent_team_runner


class Presets:
    def get_group_presets(self):
        return [{
            "id": "team-1",
            "name": "Research Team",
            "lead_crew_member_id": "lead",
            "members": [{"crew_member_id": "worker", "role": "researcher", "order": 1, "enabled": True}],
            "topology": "lead_routed",
            "shared_instructions": "Be crisp.",
            "run_config": {"max_steps": 4},
        }]


async def fake_llm(url, model, messages, **kwargs):
    system = messages[0]["content"] if messages else ""
    if "delegation plan" in system.lower():
        return "Plan: worker researches facts."
    if "acting as researcher" in system:
        return "Worker output: key facts."
    return "Final answer synthesized."


def test_lead_routed_team_run_uses_lead_worker_and_metadata(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'team.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    monkeypatch.setattr(agent_team_runner, "SessionLocal", TestingSession)

    db = TestingSession()
    try:
        db.add(DbSession(id="s1", name="Team", endpoint_url="base-url", model="base-model", owner="", group_preset_id="team-1"))
        db.add(CrewMember(id="lead", owner="", name="Lead", personality="Coordinate.", model="lead-model", endpoint_url="lead-url", is_active=True))
        db.add(CrewMember(id="worker", owner="", name="Worker", personality="Research.", model="worker-model", endpoint_url="worker-url", is_active=True))
        db.commit()
    finally:
        db.close()

    import anyio

    async def _run():
        return await agent_team_runner.run_lead_routed_team(
            session_id="s1",
            user_message="Do work",
            base_messages=[{"role": "user", "content": "Do work"}],
            endpoint_url="base-url",
            model="base-model",
            headers={},
            temperature=0.2,
            max_tokens=500,
            owner="",
            preset_manager=Presets(),
            llm_call=fake_llm,
        )

    result = anyio.run(_run)
    assert result.response == "Final answer synthesized."
    assert result.metadata["team_run"] is True
    assert result.metadata["lead"]["name"] == "Lead"
    assert result.metadata["workers"][0]["name"] == "Worker"
    assert result.metadata["plan"] == "Plan: worker researches facts."
