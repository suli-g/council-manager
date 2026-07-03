import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from council_manager.db import db_manager, Team, Proposal, Project
from council_manager.core.prompter import AgentPrompter, VoteResponse, DeliberationResponse
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
                return DeliberationResponse(stance="FOR", motivation="Functional rationale", suggestion="Use pipelines")
            return DeliberationResponse(stance="AGAINST", motivation="OOP rationale", suggestion="Use pure objects")
        
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

        # 4. Run Deliberation (Async) with progress tracking
        progress_events = []
        def test_on_progress(team_id, team_name, status, elapsed):
            progress_events.append((team_id, team_name, status))

        updated_proposal = await orchestrator.run_deliberation(workspace, "DEC-101", on_progress=test_on_progress)

        assert updated_proposal.status == "VOTING_PENDING"
        assert len(updated_proposal.rationales) == 2
        
        rat_dict = {r["team_id"]: r["rationale"] for r in updated_proposal.rationales}
        assert rat_dict["A"]["motivation"] == "Functional rationale"
        assert rat_dict["A"]["stance"] == "FOR"
        assert rat_dict["B"]["motivation"] == "OOP rationale"
        assert rat_dict["B"]["stance"] == "AGAINST"

        # Verify progress events were captured
        assert len(progress_events) == 4  # (started, completed) for both teams
        assert ("A", "Team A", "STARTED") in progress_events
        assert ("A", "Team A", "COMPLETED") in progress_events
        assert ("B", "Team B", "STARTED") in progress_events
        assert ("B", "Team B", "COMPLETED") in progress_events

        # Verify prompter was called asynchronously for both teams
        assert mock_prompter.generate_deliberation_async.call_count == 2

        # Release file locks before leaving temp directory context
        db_manager.close_all()

@pytest.mark.anyio
async def test_run_voting_consensus():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        
        # 1. Setup mock project and teams in SQLite database
        session = db_manager.get_session(workspace)
        
        proj = Project(id="test_proj", name="Test Project")
        session.add(proj)
        session.commit()

        # Total weight = 15. Team A weight = 11 (> 70% of 15). Team B weight = 4.
        t1 = Team(id="A", name="Team A", vote_weight=11, paradigm_specialty="Functional")
        t2 = Team(id="B", name="Team B", vote_weight=4, paradigm_specialty="OOP")
        session.add_all([t1, t2])
        
        # Pre-seed a proposal in VOTING_PENDING status
        prop = Proposal(
            id="DEC-202",
            project_id="test_proj",
            topic="Data Layer",
            description="...",
            options=["Alt 1", "Alt 2"],
            status="VOTING_PENDING",
            rationales=[{"team_id": "A", "rationale": "..."}, {"team_id": "B", "rationale": "..."}]
        )
        session.add(prop)
        session.commit()
        session.close()

        # 2. Mock AgentPrompter async generate_vote_async
        mock_prompter = MagicMock(spec=AgentPrompter)
        mock_prompter.generate_vote_async = AsyncMock()
        
        # In Cycle 1, Team A (weight 11) votes "Alt 1". That is >70% of 15. Consensus reached.
        async def mock_vote(team_name, paradigm_specialty, title, description, options, rationales_context):
            if "Team A" in team_name:
                return VoteResponse(vote="Alt 1", rationale="Functional rocks")
            return VoteResponse(vote="Alt 2", rationale="OOP rocks")
            
        mock_prompter.generate_vote_async.side_effect = mock_vote

        orchestrator = CouncilOrchestrator(prompter=mock_prompter)

        # 3. Run Voting (max_cycles=3)
        updated_proposal = await orchestrator.run_voting(workspace, "DEC-202", max_cycles=3)

        assert updated_proposal.status == "RATIFICATION_PENDING"
        assert len(updated_proposal.votes) == 2
        
        votes_dict = {v["team_id"]: v["vote"] for v in updated_proposal.votes}
        assert votes_dict["A"] == "Alt 1"
        assert votes_dict["B"] == "Alt 2"

        # Verify it exited after Cycle 1 (only 2 prompter calls total)
        assert mock_prompter.generate_vote_async.call_count == 2

        # Release file locks before leaving temp directory context
        db_manager.close_all()

@pytest.mark.anyio
async def test_run_voting_fallback():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        
        session = db_manager.get_session(workspace)
        
        proj = Project(id="test_proj", name="Test Project")
        session.add(proj)
        session.commit()

        # Total weight = 20. Neither team is > 70% (14 weight).
        t1 = Team(id="A", name="Team A", vote_weight=10, paradigm_specialty="Functional")
        t2 = Team(id="B", name="Team B", vote_weight=10, paradigm_specialty="OOP")
        session.add_all([t1, t2])
        
        prop = Proposal(
            id="DEC-303",
            project_id="test_proj",
            topic="Data Layer",
            description="...",
            options=["Alt 1", "Alt 2"],
            status="VOTING_PENDING",
            rationales=[{"team_id": "A", "rationale": "..."}, {"team_id": "B", "rationale": "..."}]
        )
        session.add(prop)
        session.commit()
        session.close()

        # Mock prompter. They keep voting differently, no consensus will be met.
        mock_prompter = MagicMock(spec=AgentPrompter)
        mock_prompter.generate_vote_async = AsyncMock()
        
        async def mock_vote(team_name, paradigm_specialty, title, description, options, rationales_context):
            if "Team A" in team_name:
                return VoteResponse(vote="Alt 1", rationale="Functional")
            return VoteResponse(vote="Alt 2", rationale="OOP")
            
        mock_prompter.generate_vote_async.side_effect = mock_vote

        orchestrator = CouncilOrchestrator(prompter=mock_prompter)

        # Run voting with max_cycles = 2
        updated_proposal = await orchestrator.run_voting(workspace, "DEC-303", max_cycles=2)

        assert updated_proposal.status == "RATIFICATION_PENDING"
        assert len(updated_proposal.votes) == 2
        
        # Verify it went through both cycles (2 cycles * 2 teams = 4 prompter calls)
        assert mock_prompter.generate_vote_async.call_count == 4

        # Release file locks before leaving temp directory context
        db_manager.close_all()

@pytest.mark.anyio
async def test_run_voting_midway_consensus():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        session = db_manager.get_session(workspace)
        
        proj = Project(id="test_proj", name="Test Project")
        session.add(proj)
        session.commit()

        # Total weight = 20. Team A weight = 15 (>70%). Team B weight = 5.
        t1 = Team(id="A", name="Team A", vote_weight=15, paradigm_specialty="Functional")
        t2 = Team(id="B", name="Team B", vote_weight=5, paradigm_specialty="OOP")
        session.add_all([t1, t2])
        
        prop = Proposal(
            id="DEC-404",
            project_id="test_proj",
            topic="Consensus Topic",
            description="...",
            options=["Alt 1", "Alt 2"],
            status="VOTING_PENDING",
            rationales=[{"team_id": "A", "rationale": "..."}, {"team_id": "B", "rationale": "..."}]
        )
        session.add(prop)
        session.commit()
        session.close()

        mock_prompter = MagicMock(spec=AgentPrompter)
        mock_prompter.generate_vote_async = AsyncMock()

        # In Cycle 1: Team A votes "Alt 1", Team B votes "Alt 2" -> No consensus (15/20 = 75%? Wait, 15 is 75% so consensus is reached in Cycle 1!).
        # Let's make it so Team A votes "Alt 1" (10 weight) and Team B votes "Alt 2" (10 weight) -> No consensus.
        # Wait, let's change weights: Team A (10 weight), Team B (10 weight). Total 20. Consensus requires 14 (70%).
        # Cycle 1: Team A votes "Alt 1", Team B votes "Alt 2" -> 10 vs 10 (no consensus).
        # Cycle 2: Both vote "Alt 1" -> 20 vs 0 (consensus reached!).
        
        # Adjust weights to 10 each in DB
        session = db_manager.get_session(workspace)
        ta = session.query(Team).filter_by(id="A").first()
        tb = session.query(Team).filter_by(id="B").first()
        ta.vote_weight = 10
        tb.vote_weight = 10
        session.commit()
        session.close()

        cycle_count = 0
        async def mock_vote(team_name, paradigm_specialty, title, description, options, rationales_context):
            nonlocal cycle_count
            # Every 2 calls represents 1 cycle (2 teams)
            current_cycle = (cycle_count // 2) + 1
            cycle_count += 1
            if current_cycle == 1:
                if "Team A" in team_name:
                    return VoteResponse(vote="Alt 1", rationale="Cycle 1 Functional")
                return VoteResponse(vote="Alt 2", rationale="Cycle 1 OOP")
            else:
                return VoteResponse(vote="Alt 1", rationale="Compromised on Alt 1")

        mock_prompter.generate_vote_async.side_effect = mock_vote

        orchestrator = CouncilOrchestrator(prompter=mock_prompter)
        
        # Run voting with max_cycles = 5
        updated_proposal = await orchestrator.run_voting(workspace, "DEC-404", max_cycles=5)
        
        assert updated_proposal.status == "RATIFICATION_PENDING"
        # Consensus reached in Cycle 2, so call_count should be exactly 4 (2 cycles * 2 teams)
        assert mock_prompter.generate_vote_async.call_count == 4
        
        db_manager.close_all()

@pytest.mark.anyio
async def test_run_deliberation_missing_proposal():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        orchestrator = CouncilOrchestrator()
        with pytest.raises(ValueError, match="Proposal 'INVALID' not found"):
            await orchestrator.run_deliberation(workspace, "INVALID")
        db_manager.close_all()

@pytest.mark.anyio
async def test_run_voting_missing_proposal():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        orchestrator = CouncilOrchestrator()
        with pytest.raises(ValueError, match="Proposal 'INVALID' not found"):
            await orchestrator.run_voting(workspace, "INVALID")
        db_manager.close_all()

@pytest.mark.anyio
async def test_run_deliberation_no_teams():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        session = db_manager.get_session(workspace)
        proj = Project(id="test_proj", name="Test Project")
        session.add(proj)
        prop = Proposal(
            id="DEC-505",
            project_id="test_proj",
            topic="No Teams",
            description="...",
            options=["Alt 1"],
            status="DELIBERATION_PENDING"
        )
        session.add(prop)
        session.commit()
        session.close()

        orchestrator = CouncilOrchestrator()
        with pytest.raises(ValueError, match="No active teams registered"):
            await orchestrator.run_deliberation(workspace, "DEC-505")
        db_manager.close_all()

@pytest.mark.anyio
async def test_run_voting_no_teams():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        session = db_manager.get_session(workspace)
        proj = Project(id="test_proj", name="Test Project")
        session.add(proj)
        prop = Proposal(
            id="DEC-606",
            project_id="test_proj",
            topic="No Teams",
            description="...",
            options=["Alt 1"],
            status="VOTING_PENDING",
            rationales=[]
        )
        session.add(prop)
        session.commit()
        session.close()

        orchestrator = CouncilOrchestrator()
        with pytest.raises(ValueError, match="No active teams registered"):
            await orchestrator.run_voting(workspace, "DEC-606")
        db_manager.close_all()


def test_create_proposal_auto_inception():
    from council_manager.core.prompter import InceptionResponse
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        try:
            # Setup mock project in database
            session = db_manager.get_session(workspace)
            proj = Project(id="test_proj", name="Test Project")
            session.add(proj)
            session.commit()
            session.close()

            # Mock prompter generate_proposal_inception
            mock_prompter = MagicMock(spec=AgentPrompter)
            mock_prompter.generate_proposal_inception.return_value = InceptionResponse(
                topic="Auto Topic",
                options=["Alt A", "Alt B"]
            )

            orchestrator = CouncilOrchestrator(prompter=mock_prompter)

            # Create proposal with omitted ID, topic, and options
            proposal = orchestrator.create_proposal(
                workspace_dir=workspace,
                project_id="test_proj",
                description="Testing auto inception logic."
            )

            # Verify proposal_id was generated as DEC-001 (since it's the first proposal)
            assert proposal.id == "DEC-001"
            assert proposal.topic == "Auto Topic"
            assert proposal.options == ["Alt A", "Alt B"]
        finally:
            # Release database locks
            db_manager.close_all()

def test_create_proposal_auto_inception_fallback():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        try:
            # Setup mock project in database
            session = db_manager.get_session(workspace)
            proj = Project(id="test_proj", name="Test Project")
            session.add(proj)
            session.commit()
            session.close()

            # Mock prompter to raise exception to trigger fallback
            mock_prompter = MagicMock(spec=AgentPrompter)
            mock_prompter.generate_proposal_inception.side_effect = Exception("API Error")

            orchestrator = CouncilOrchestrator(prompter=mock_prompter)

            # Create proposal with omitted ID, topic, and options
            proposal = orchestrator.create_proposal(
                workspace_dir=workspace,
                project_id="test_proj",
                description="Testing auto inception fallback logic."
            )

            # Verify fallback topic and options are set correctly
            assert proposal.id == "DEC-001"
            assert proposal.topic == "Testing auto inception fallbac..."
            assert proposal.options == ["Adopt Proposal", "Keep Status Quo"]
        finally:
            # Release database locks
            db_manager.close_all()

