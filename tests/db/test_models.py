import pytest
from pathlib import Path
import tempfile
from sqlalchemy.exc import IntegrityError
from council_manager.db import db_manager, Project, Team, Proposal, Decision, Alternative, AuditLog, AuditDecision, RoadmapTask

def test_models_crud():
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_workspace = Path(tmpdir)
        session = db_manager.get_session(temp_workspace)

        # 1. Project CRUD
        proj = Project(id="cm", name="Council Manager")
        session.add(proj)
        session.commit()

        db_proj = session.query(Project).filter_by(id="cm").first()
        assert db_proj is not None
        assert db_proj.name == "Council Manager"

        # 2. Team CRUD
        team = Team(id="A", name="Functional Specialists", vote_weight=10, paradigm_specialty="Functional")
        session.add(team)
        session.commit()

        db_team = session.query(Team).filter_by(id="A").first()
        assert db_team is not None
        assert db_team.name == "Functional Specialists"

        # 3. Proposal CRUD with JSON columns
        proposal = Proposal(
            id="prop1",
            project_id="cm",
            topic="Architecture",
            description="Let's build it",
            options=["Alt 1", "Alt 2"],
            rationales=[{"team_id": "A", "rationale": "Very functional"}],
            votes=[{"team_id": "A", "vote": "Alt 1"}]
        )
        session.add(proposal)
        session.commit()

        db_prop = session.query(Proposal).filter_by(id="prop1").first()
        assert db_prop is not None
        assert db_prop.options == ["Alt 1", "Alt 2"]
        assert db_prop.rationales[0]["team_id"] == "A"
        assert db_prop.votes[0]["vote"] == "Alt 1"

        # 4. Decision and Alternatives CRUD
        decision = Decision(
            id="DEC-100",
            project_id="cm",
            topic="Architecture",
            decision="Unified SQLite",
            rationale="Simplicity and transactions"
        )
        session.add(decision)
        session.commit()

        alt = Alternative(
            id="ALT-100",
            decision_id="DEC-100",
            option="Mongo",
            pros="None",
            cons="Leakage"
        )
        session.add(alt)
        session.commit()

        db_dec = session.query(Decision).filter_by(id="DEC-100").first()
        assert db_dec is not None
        assert db_dec.alternatives[0].option == "Mongo"

        # 5. Audit Log CRUD
        audit = AuditLog(
            id="AUDIT-100",
            project_id="cm",
            summary="Initial review",
            alignment_score=95.0,
            auditor_team="F"
        )
        session.add(audit)
        session.commit()

        db_audit = session.query(AuditLog).filter_by(id="AUDIT-100").first()
        assert db_audit is not None
        assert db_audit.alignment_score == 95.0

        # 5b. RoadmapTask CRUD
        task = RoadmapTask(
            id="P1-01",
            project_id="cm",
            phase=1,
            task="DB Init",
            status="DONE",
            notes="Completed"
        )
        session.add(task)
        session.commit()

        db_task = session.query(RoadmapTask).filter_by(id="P1-01").first()
        assert db_task is not None
        assert db_task.task == "DB Init"
        assert db_task.status == "DONE"

        # 5c. AuditDecision CRUD
        audit_dec = AuditDecision(
            audit_id="AUDIT-100",
            decision_id="DEC-100",
            project_id="cm",
            status="RESOLVED",
            notes="No issues remaining"
        )
        session.add(audit_dec)
        session.commit()

        db_audit_dec = session.query(AuditDecision).filter_by(audit_id="AUDIT-100", decision_id="DEC-100").first()
        assert db_audit_dec is not None
        assert db_audit_dec.status == "RESOLVED"
        assert db_audit_dec.notes == "No issues remaining"


        # 6. Foreign Key Constraint Enforcement
        invalid_proposal = Proposal(
            id="prop2",
            project_id="non-existent-project",
            topic="Fail Topic",
            description="Should fail constraint",
            options=[]
        )
        session.add(invalid_proposal)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.close()
        
        # Release connection handles before leaving TemporaryDirectory context
        db_manager.close_all()
