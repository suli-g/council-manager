import pytest
import tempfile
import argparse
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from council_manager.db import db_manager, Proposal, BackgroundTask, Project, Team
from council_manager.cli import (
    cmd_deliberate,
    cmd_vote,
    cmd_run_task_worker,
    cmd_task_status,
    cmd_task_logs,
)
from council_manager.core.orchestrator import CouncilOrchestrator

@pytest.fixture(autouse=True)
def cleanup():
    yield
    db_manager.close_all()

def test_background_task_creation():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        session = db_manager.get_session(workspace)
        
        # Setup project & proposal
        p = Project(id="council_manager", name="Council Manager")
        prop = Proposal(
            id="DEC-099",
            project_id="council_manager",
            topic="Test Topic",
            description="Test Desc",
            options=["Opt A", "Opt B"],
            status="DELIBERATION_PENDING"
        )
        session.add_all([p, prop])
        session.commit()
        session.close()

        # Mock spawn subprocess
        with patch("council_manager.cli.spawn_background_task") as mock_spawn:
            args = argparse.Namespace(
                workspace=str(workspace),
                proposal_id="DEC-099",
                async_mode=True
            )
            cmd_deliberate(args)
            
            # Verify task is created in SQLite
            session = db_manager.get_session(workspace)
            task = session.query(BackgroundTask).filter_by(proposal_id="DEC-099").first()
            assert task is not None
            assert task.status == "PENDING"
            assert task.task_type == "DELIBERATION"
            
            mock_spawn.assert_called_once_with(workspace, task.id)
            session.close()

def test_task_worker_execution():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        session = db_manager.get_session(workspace)
        
        # Setup project, proposal, and background task
        proj = Project(id="council_manager", name="Council Manager")
        prop = Proposal(
            id="DEC-100",
            project_id="council_manager",
            topic="Test Topic 2",
            description="Test Desc 2",
            options=["Opt A", "Opt B"],
            status="DELIBERATION_PENDING"
        )
        t = Team(id="A", name="Team A", vote_weight=10, paradigm_specialty="Functional")
        task = BackgroundTask(
            id="TASK-001",
            project_id="council_manager",
            task_type="DELIBERATION",
            proposal_id="DEC-100",
            status="PENDING"
        )
        session.add_all([proj, prop, t, task])
        session.commit()
        session.close()
        
        # Mock orchestrator deliberation run
        with patch("council_manager.cli.council_orchestrator.run_deliberation", new_callable=AsyncMock) as mock_delib, \
             patch("council_manager.cli.export_db_to_csv") as mock_export:
             
            args = argparse.Namespace(
                workspace=str(workspace),
                task_id="TASK-001"
            )
            cmd_run_task_worker(args)
            
            mock_delib.assert_called_once_with(workspace, "DEC-100")
            mock_export.assert_called_once_with(workspace, "council_manager")
            
            # Verify task is completed
            session = db_manager.get_session(workspace)
            completed_task = session.query(BackgroundTask).filter_by(id="TASK-001").first()
            assert completed_task.status == "COMPLETED"
            session.close()

def test_task_status_command(capsys):
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        session = db_manager.get_session(workspace)
        
        proj = Project(id="council_manager", name="Council Manager")
        prop = Proposal(
            id="DEC-100",
            project_id="council_manager",
            topic="Test Topic 2",
            description="Test Desc 2",
            options=["Opt A", "Opt B"],
            status="DELIBERATION_PENDING"
        )
        task = BackgroundTask(
            id="TASK-005",
            project_id="council_manager",
            task_type="VOTING",
            proposal_id="DEC-100",
            status="RUNNING"
        )
        session.add_all([proj, prop, task])
        session.commit()
        session.close()
        
        args = argparse.Namespace(
            workspace=str(workspace),
            task_id="TASK-005"
        )
        cmd_task_status(args)
        
        captured = capsys.readouterr()
        assert "TASK-005" in captured.out
        assert "VOTING" in captured.out
        assert "RUNNING" in captured.out

def test_task_logs_command(capsys):
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        log_dir = workspace / ".agents" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "TASK-009.log"
        
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("Log line 1\nLog line 2\n")
            
        args = argparse.Namespace(
            workspace=str(workspace),
            task_id="TASK-009",
            tail=False
        )
        cmd_task_logs(args)
        
        captured = capsys.readouterr()
        assert "Log line 1" in captured.out
        assert "Log line 2" in captured.out
