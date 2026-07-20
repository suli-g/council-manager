import pytest
from pathlib import Path
from council_manager.core.context_pipeline import ContextPipeline, TeamsFilter, DecisionsFilter, RoadmapFilter
from council_manager.db import db_manager
from council_manager.db.models import Project, Team, Decision, RoadmapTask

def test_context_pipeline_execution(tmp_path):
    # Setup temporary database
    db_manager.database_dir = tmp_path
    db_manager.db_file = "test_governance.db"
    
    # Initialize workspace resources
    workspace = tmp_path / "test_workspace"
    workspace.mkdir()
    
    session = db_manager.get_session(workspace)
    try:
        # Create Project
        project = Project(id="test_project", name="Test Project")
        session.add(project)
        
        # Add a Team
        team = Team(id="A", name="Functional Specialists", paradigm_specialty="Functional")
        session.add(team)
        
        # Add a Decision
        decision = Decision(id="DEC-001", project_id="test_project", topic="Test Topic", decision="Use Python", rationale="Pure choice")
        session.add(decision)
        
        # Add a Roadmap Task
        task = RoadmapTask(id="P1-01", project_id="test_project", phase=1, task="Init db", status="DONE")
        session.add(task)
        
        session.commit()
    finally:
        session.close()
        
    # Execute Pipeline
    pipeline = ContextPipeline([TeamsFilter(), DecisionsFilter(limit=1), RoadmapFilter()])
    output = pipeline.execute(workspace)
    
    # Validate Outputs
    assert "### Active Specialist Teams" in output
    assert "- Team A (Functional Specialists): Functional" in output
    assert "### Recent Ratified Decisions" in output
    assert "- **DEC-001**: Test Topic (Decision: Use Python)" in output
    assert "### Roadmap Status Summary" in output
    assert "Overall Progress: 100% (1/1 tasks completed)" in output
    
    # Clean up db manager
    db_manager.close_all()
