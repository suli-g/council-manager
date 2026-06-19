import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from council_manager.db import db_manager, Proposal, Project, Decision, Alternative, AuditLog, RoadmapTask, BackgroundTask
from council_manager.config import settings
from council_manager.server.main import app, get_db, verify_api_key

# We use standard synchronous test executions to avoid event loop issues with TestClient
@pytest.fixture
def workspace_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

@pytest.fixture
def test_db_session(workspace_dir):
    # Retrieve dynamic workspace DB session
    session = db_manager.get_session(workspace_dir)
    
    # Seed mock project & proposal
    proj = Project(id="council_manager", name="Council Manager")
    prop = Proposal(
        id="DEC-088",
        project_id="council_manager",
        topic="API Setup",
        description="Verify FastAPI server integration",
        options=["FastAPI", "Flask"],
        status="DELIBERATION_PENDING"
    )
    dec = Decision(
        id="DEC-001",
        project_id="council_manager",
        topic="Architecture",
        decision="Unified SQLite",
        rationale="Simple transactional database storage"
    )
    alt = Alternative(
        id="ALT-001",
        decision_id="DEC-001",
        option="Postgres",
        pros="Highly scalable",
        cons="Docker overhead"
    )
    task = RoadmapTask(
        id="P3-01a",
        project_id="council_manager",
        phase=3,
        task="FastAPI Server Setup",
        status="TODO"
    )
    audit = AuditLog(
        id="AUDIT-001",
        project_id="council_manager",
        summary="Initial API check",
        alignment_score=100.0,
        auditor_team="F"
    )
    
    session.add_all([proj, prop, dec, alt, task, audit])
    session.commit()
    session.close()
    
    yield workspace_dir
    db_manager.close_all()

def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_optional_workspace_fallback(test_db_session):
    # If header is missing, it should fallback to settings.workspace_dir.
    with patch.object(settings, "workspace_dir", test_db_session):
        client = TestClient(app)
        response = client.get("/proposals")
        assert response.status_code == 200
        props = response.json()
        assert len(props) == 1
        assert props[0]["id"] == "DEC-088"

def test_project_id_routing_slug(test_db_session):
    # Test logical slug resolution matching default 'council_manager' ID
    with patch.object(settings, "workspace_dir", test_db_session):
        client = TestClient(app)
        response = client.get("/proposals", headers={"X-Project-ID": "council_manager"})
        assert response.status_code == 200
        assert len(response.json()) == 1

def test_project_id_routing_custom_mapping(test_db_session):
    # Test logical slug resolution via custom workspace_mappings dict
    custom_mappings = {"my_custom_project": str(test_db_session)}
    with patch.object(settings, "workspace_mappings", custom_mappings):
        client = TestClient(app)
        response = client.get("/proposals", headers={"X-Project-ID": "my_custom_project"})
        assert response.status_code == 200
        assert response.json()[0]["id"] == "DEC-088"

def test_invalid_project_id_routing():
    client = TestClient(app)
    response = client.get("/proposals", headers={"X-Project-ID": "invalid_project_slug_xyz"})
    assert response.status_code == 400
    assert "Could not resolve workspace identifier" in response.json()["detail"]

def test_invalid_workspace_path():
    client = TestClient(app)
    response = client.get("/proposals", headers={"X-Workspace-Path": "B:/non_existent_folder_xyz"})
    assert response.status_code == 400
    assert "Could not resolve workspace identifier" in response.json()["detail"]

def test_get_proposals(test_db_session):
    client = TestClient(app)
    response = client.get(
        "/proposals",
        headers={"X-Workspace-Path": str(test_db_session)}
    )
    assert response.status_code == 200
    props = response.json()
    assert len(props) == 1
    assert props[0]["id"] == "DEC-088"
    assert props[0]["topic"] == "API Setup"

def test_get_proposal_by_id(test_db_session):
    client = TestClient(app)
    response = client.get(
        "/proposals/DEC-088",
        headers={"X-Workspace-Path": str(test_db_session)}
    )
    assert response.status_code == 200
    assert response.json()["id"] == "DEC-088"

    # Test not found
    response_nf = client.get(
        "/proposals/DEC-NONEXIST",
        headers={"X-Workspace-Path": str(test_db_session)}
    )
    assert response_nf.status_code == 404

def test_get_decisions(test_db_session):
    client = TestClient(app)
    response = client.get(
        "/decisions",
        headers={"X-Workspace-Path": str(test_db_session)}
    )
    assert response.status_code == 200
    decs = response.json()
    assert len(decs) == 1
    assert decs[0]["id"] == "DEC-001"
    assert len(decs[0]["alternatives"]) == 1
    assert decs[0]["alternatives"][0]["option"] == "Postgres"

def test_get_roadmap(test_db_session):
    client = TestClient(app)
    response = client.get(
        "/roadmap",
        headers={"X-Workspace-Path": str(test_db_session)}
    )
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 1
    assert tasks[0]["id"] == "P3-01a"

def test_get_audits(test_db_session):
    client = TestClient(app)
    response = client.get(
        "/audits",
        headers={"X-Workspace-Path": str(test_db_session)}
    )
    assert response.status_code == 200
    auds = response.json()
    assert len(auds) == 1
    assert auds[0]["id"] == "AUDIT-001"

def test_api_key_verification(test_db_session):
    # Force set council_api_key in config settings
    settings.council_api_key = "secure_token_123"
    
    client = TestClient(app)
    
    # 1. Test missing API key
    response = client.get(
        "/proposals",
        headers={"X-Workspace-Path": str(test_db_session)}
    )
    assert response.status_code == 401
    
    # 2. Test invalid API key
    response_invalid = client.get(
        "/proposals",
        headers={
            "X-Workspace-Path": str(test_db_session),
            "X-API-Key": "wrong_token"
        }
    )
    assert response_invalid.status_code == 401
    
    # 3. Test correct API key
    response_ok = client.get(
        "/proposals",
        headers={
            "X-Workspace-Path": str(test_db_session),
            "X-API-Key": "secure_token_123"
        }
    )
    assert response_ok.status_code == 200
    
    # Reset config setting
    settings.council_api_key = None

def test_post_proposal(test_db_session):
    client = TestClient(app)
    
    def mock_create_impl(workspace_dir, project_id, description, topic=None, options=None):
        session = db_manager.get_session(workspace_dir)
        prop = Proposal(
            id="DEC-089",
            project_id=project_id,
            topic=topic or "API Setup",
            description=description,
            options=options or ["FastAPI", "Flask"],
            status="DELIBERATION_PENDING"
        )
        session.add(prop)
        session.commit()
        # Keep attached to return
        return session.query(Proposal).filter_by(id="DEC-089").first()
    
    with patch("council_manager.core.orchestrator.council_orchestrator.create_proposal", side_effect=mock_create_impl):
        response = client.post(
            "/proposals",
            json={
                "project_id": "council_manager",
                "description": "Verify FastAPI server integration",
                "topic": "API Setup",
                "options": ["FastAPI", "Flask"]
            },
            headers={"X-Workspace-Path": str(test_db_session)}
        )
        assert response.status_code == 201
        assert response.json()["id"] == "DEC-089"

def test_deliberate_proposal_endpoint(test_db_session):
    client = TestClient(app)
    
    with patch("council_manager.cli.generate_task_id") as mock_id, \
         patch("council_manager.cli.spawn_background_task") as mock_spawn:
        
        mock_id.return_value = "TASK-999"
        
        response = client.post(
            "/proposals/DEC-088/deliberate?async_mode=true",
            headers={"X-Workspace-Path": str(test_db_session)}
        )
        assert response.status_code == 200
        assert response.json()["task_id"] == "TASK-999"
        assert response.json()["status"] == "PENDING"
        mock_spawn.assert_called_once_with(test_db_session, "TASK-999")

def test_vote_proposal_endpoint(test_db_session):
    client = TestClient(app)
    
    with patch("council_manager.cli.generate_task_id") as mock_id, \
         patch("council_manager.cli.spawn_background_task") as mock_spawn:
        
        mock_id.return_value = "TASK-888"
        
        response = client.post(
            "/proposals/DEC-088/vote?async_mode=true&max_cycles=3",
            headers={"X-Workspace-Path": str(test_db_session)}
        )
        assert response.status_code == 200
        assert response.json()["task_id"] == "TASK-888"
        assert response.json()["status"] == "PENDING"
        mock_spawn.assert_called_once_with(test_db_session, "TASK-888", max_cycles=3)

def test_get_task_status_endpoint(test_db_session):
    session = db_manager.get_session(test_db_session)
    t = BackgroundTask(
        id="TASK-999",
        project_id="council_manager",
        task_type="DELIBERATION",
        proposal_id="DEC-088",
        status="PENDING"
    )
    session.add(t)
    session.commit()
    session.close()

    client = TestClient(app)
    response = client.get(
        "/tasks/TASK-999/status",
        headers={"X-Workspace-Path": str(test_db_session)}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "PENDING"

def test_get_task_logs_endpoint(test_db_session):
    log_dir = test_db_session / ".agents" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "TASK-999.log"
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("Server log content")

    client = TestClient(app)
    response = client.get(
        "/tasks/TASK-999/logs",
        headers={"X-Workspace-Path": str(test_db_session)}
    )
    assert response.status_code == 200
    assert response.json()["logs"] == "Server log content"

