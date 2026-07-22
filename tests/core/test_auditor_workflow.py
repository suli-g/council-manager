import pytest
from pathlib import Path
import os
from unittest.mock import MagicMock
from council_manager.cli import cmd_audit_request, cmd_audit_report_import
from council_manager.db import db_manager
from council_manager.db.models import Project, AuditLog

def test_audit_request_generation(tmp_path):
    # Setup test workspace
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    
    # Run request generator
    args = MagicMock()
    args.workspace = str(workspace)
    cmd_audit_request(args)
    
    # Assert request file is created and has instructions
    req_file = workspace / ".agents" / "audit_request.md"
    assert req_file.exists()
    
    content = req_file.read_text(encoding="utf-8")
    assert "# External Audit Request" in content
    assert "## Instructions for the Auditor LLM" in content
    assert "Alignment Score" in content

def test_audit_report_import(tmp_path):
    # Setup database directory
    db_manager.database_dir = tmp_path
    db_manager.db_file = "test_governance.db"
    
    # Setup workspace
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
        
    # Write a mock audit report matching regex patterns
    report_content = (
        "### Audit Report\n"
        "- **Audit ID**: AUDIT-032\n"
        "- **Auditor**: External\n"
        "- **Alignment Score**: 95%\n"
        "- **Summary**: Code changes are compliant with architecture standards.\n\n"
        "#### Detailed Findings\n"
        "Detailed review passed without errors."
    )
    
    agents_dir = workspace / ".agents"
    agents_dir.mkdir()
    report_file = agents_dir / "audit_report.md"
    report_file.write_text(report_content, encoding="utf-8")
    
    # Run import
    args = MagicMock()
    args.workspace = str(workspace)
    args.report_path = str(report_file)
    cmd_audit_report_import(args)
    
    # Verify DB entry
    session = db_manager.get_session(workspace)
    try:
        audit = session.query(AuditLog).filter_by(id="AUDIT-032").first()
        assert audit is not None
        assert audit.alignment_score == 95.0
        assert audit.summary == "Code changes are compliant with architecture standards."
        assert audit.auditor_team == "External"
    finally:
        session.close()
        db_manager.close_all()
        
    # Verify CSV synced
    csv_file = agents_dir / "audits.csv"
    assert csv_file.exists()
    csv_content = csv_file.read_text(encoding="utf-8")
    assert "AUDIT-032" in csv_content
    assert "95%" in csv_content
    assert "compliant with architecture standards" in csv_content
