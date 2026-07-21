"""
Unit tests for Runtime Tool Pre-Execution Gatekeeper Middleware (P6-02a, v0.9.2).
"""

import os
import pytest
from council_manager.core.gatekeeper import GatekeeperMiddleware, GatekeeperViolationError
from council_manager.core.orchestrator import council_orchestrator
from council_manager.db.models import Proposal


def test_gatekeeper_blocks_unauthorized_ratification():
    middleware = GatekeeperMiddleware(strict_mode=True)
    with pytest.raises(GatekeeperViolationError, match=r"\[GATEKEEPER BLOCKED\]"):
        middleware.verify_ratification_authority("DEC-100", human_ratified=False, verification_token=None)


def test_gatekeeper_allows_human_ratification():
    middleware = GatekeeperMiddleware(strict_mode=True)
    assert middleware.verify_ratification_authority("DEC-100", human_ratified=True) is True


def test_gatekeeper_allows_valid_token():
    middleware = GatekeeperMiddleware(strict_mode=True)
    assert middleware.verify_ratification_authority("DEC-100", human_ratified=False, verification_token="TOKEN-RATIFIED-12345") is True


def test_gatekeeper_environment_bypass(monkeypatch):
    monkeypatch.setenv("COUNCIL_GATEKEEPER_BYPASS", "1")
    middleware = GatekeeperMiddleware(strict_mode=True)
    assert middleware.verify_ratification_authority("DEC-100", human_ratified=False) is True


def test_orchestrator_ratify_proposal_gatekeeper_interception(tmp_path):
    # Setup temporary workspace and test proposal
    from council_manager.db import db_manager
    from council_manager.db.models import Project, Proposal
    session = db_manager.get_session(tmp_path)
    try:
        project = Project(id="test_proj", name="Test Project")
        session.add(project)
        p = Proposal(
            id="DEC-TEST-999",
            project_id="test_proj",
            topic="Test Gatekeeper",
            description="Testing gatekeeper interception",
            status="VOTING_PENDING",
            options=["Option A", "Option B"]
        )
        session.add(p)
        session.commit()
    finally:
        session.close()

    # Attempt autonomous ratification without human_ratified=True
    with pytest.raises(GatekeeperViolationError):
        council_orchestrator.ratify_proposal(
            workspace_dir=tmp_path,
            proposal_id="DEC-TEST-999",
            decision_option="Option A",
            human_ratified=False
        )

    # Ratification with human_ratified=True succeeds
    council_orchestrator.ratify_proposal(
        workspace_dir=tmp_path,
        proposal_id="DEC-TEST-999",
        decision_option="Option A",
        human_ratified=True
    )

    session = db_manager.get_session(tmp_path)
    try:
        p_updated = session.query(Proposal).filter_by(id="DEC-TEST-999").first()
        assert p_updated.status == "RATIFIED"
    finally:
        session.close()
