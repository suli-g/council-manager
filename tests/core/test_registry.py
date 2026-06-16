import tempfile
from pathlib import Path
from council_manager.db import db_manager, Team
from council_manager.core.registry import agent_registry

def test_registry_get_teams():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        session = db_manager.get_session(workspace)
        
        # Insert mock teams
        t1 = Team(id="A", name="Team A", vote_weight=10, paradigm_specialty="Functional")
        t2 = Team(id="B", name="Team B", vote_weight=5, paradigm_specialty="OOP")
        session.add_all([t1, t2])
        session.commit()
        session.close()

        # Retrieve via registry
        teams = agent_registry.get_teams(workspace)
        assert len(teams) == 2
        
        team_ids = {t.id for t in teams}
        assert "A" in team_ids
        assert "B" in team_ids

        # Fetch specific team
        team_a = agent_registry.get_team(workspace, "A")
        assert team_a is not None
        assert team_a.paradigm_specialty == "Functional"

        db_manager.close_all()

def test_registry_empty_database():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        # Verify get_teams returns empty list without error
        teams = agent_registry.get_teams(workspace)
        assert teams == []
        db_manager.close_all()

def test_registry_missing_team():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        # Verify get_team returns None for non-existent team
        team = agent_registry.get_team(workspace, "NON_EXISTENT")
        assert team is None
        db_manager.close_all()

