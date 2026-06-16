import asyncio
import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from council_manager.db import db_manager, Team, Proposal
from council_manager.core.prompter import AgentPrompter
from council_manager.core.orchestrator import CouncilOrchestrator

@pytest.fixture(autouse=True)
def cleanup_connections():
    yield
    db_manager.close_all()

@pytest.mark.anyio
async def test_create_and_run_deliberation():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        
        # 1. Setup mock teams in SQLite database
        session = db_manager.get_session(workspace)
        t1 = Team(id="A", name="Team A", vote_weight=10, paradigm_specialty="Functional")
        t2 = Team(id="B", name="Team B", vote_weight=5, paradigm_specialty="OOP")
        session.add_all([t1, t2])
        session.commit()
        session.close()

        # 2. Mock AgentPrompter async generate_deliberation_async
        mock_prompter = MagicMock(spec=AgentPrompter)
        mock_prompter.generate_deliberation_async = AsyncMock()
        
        # Define mock returns for each team
        async def mock_delib(team_name, paradigm_specialty, title, description, options):
            if "Team A" in team_name:
                return "Functional rationale"
            return "OOP rationale"
        
        mock_prompter.generate_deliberation_async.side_effect = mock_delib

        orchestrator = CouncilOrchestrator(prompter=mock_prompter)

        # 3. Create Proposal
        proposal = orchestrator.create_proposal(
            workspace_dir=workspace,
            project_id="test_proj",
            proposal_id="DEC-101",
            topic="Data Layer",
            description="Use SQLite JSON1",
            options=["Alt 1", "Alt 2"]
        )

        assert proposal.status == "DELIBERATION_PENDING"
        assert proposal.id == "DEC-101"

        # Verify it was persisted in SQLite
        session = db_manager.get_session(workspace)
        db_prop = session.query(Proposal).filter_by(id="DEC-101").first()
        assert db_prop is not None
        assert db_prop.status == "DELIBERATION_PENDING"
        session.close()

        # 4. Run Deliberation (Async)
        updated_proposal = await orchestrator.run_deliberation(workspace, "DEC-101")

        assert updated_proposal.status == "VOTING_PENDING"
        assert len(updated_proposal.rationales) == 2
        
        rat_dict = {r["team_id"]: r["rationale"] for r in updated_proposal.rationales}
        assert rat_dict["A"] == "Functional rationale"
        assert rat_dict["B"] == "OOP rationale"

        # Verify prompter was called asynchronously for both teams
        assert mock_prompter.generate_deliberation_async.call_count == 2

        # Verify DB is updated
        session = db_manager.get_session(workspace)
        db_prop_final = session.query(Proposal).filter_by(id="DEC-101").first()
        assert db_prop_final.status == "VOTING_PENDING"
        assert len(db_prop_final.rationales) == 2
        session.close()

        # Release file locks
        db_manager.close_all()
