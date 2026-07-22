import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from council_manager.core.git_compliance import check_commit_compliance
from council_manager.db import db_manager
from council_manager.db.models import Project, Decision

def test_git_compliance_check_empty_db(tmp_path):
    # Setup test DB
    db_manager.database_dir = tmp_path
    db_manager.db_file = "test_governance.db"
    
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    
    # Create project in DB
    session = db_manager.get_session(workspace)
    try:
        project = Project(id="test_project", name="Test Project")
        session.add(project)
        session.commit()
    finally:
        session.close()

    # If python source code files are staged, but there are no ratified decisions, compliance should fail
    with patch("council_manager.core.git_compliance.get_staged_files") as mock_staged:
        mock_staged.return_value = ["council_manager/cli.py"]
        compliance_passed = check_commit_compliance(workspace)
        assert compliance_passed is False

def test_git_compliance_check_compliant_db(tmp_path):
    # Setup test DB
    db_manager.database_dir = tmp_path
    db_manager.db_file = "test_governance.db"
    
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    
    # Create project and decision in DB
    session = db_manager.get_session(workspace)
    try:
        project = Project(id="test_project", name="Test Project")
        session.add(project)
        decision = Decision(id="DEC-001", project_id="test_project", topic="Test Topic", decision="Implement features", rationale="Because")
        session.add(decision)
        session.commit()
    finally:
        session.close()

    # If code changes are staged, and ratified decisions are present, compliance should pass
    with patch("council_manager.core.git_compliance.get_staged_files") as mock_staged:
        mock_staged.return_value = ["council_manager/cli.py"]
        compliance_passed = check_commit_compliance(workspace)
        assert compliance_passed is True
        
    db_manager.close_all()
