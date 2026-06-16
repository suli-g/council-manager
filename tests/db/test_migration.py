import os
import csv
import tempfile
import pytest
from pathlib import Path
from council_manager.db import db_manager, Project, Team, Proposal, Decision, Alternative, AuditLog
from council_manager.db.migration import import_csv_to_db, export_db_to_csv

@pytest.fixture(autouse=True)
def cleanup_connections():
    yield
    db_manager.close_all()

def test_migration_bidirectional():
    with tempfile.TemporaryDirectory() as src_dir, tempfile.TemporaryDirectory() as dest_dir:
        src_path = Path(src_dir)
        dest_path = Path(dest_dir)

        # 1. Setup mock .agents/ folder structure in source directory
        src_agents = src_path / ".agents"
        src_agents.mkdir()
        src_votes = src_agents / "votes"
        src_votes.mkdir()

        # Write mock teams.csv
        with open(src_agents / "teams.csv", "w", encoding="utf-8", newline="") as f:
            f.write("team_id;team_name;count;paradigm_specialty\n")
            f.write("A;Functional Specialists;10;Functional Programming\n")

        # Write mock decisions.csv
        with open(src_agents / "decisions.csv", "w", encoding="utf-8", newline="") as f:
            f.write("id;date;topic;decision;rationale\n")
            f.write("DEC-001;2026-05-01;Framework Selection;Drop Django;Lightweight approach\n")

        # Write mock alternatives.csv
        with open(src_agents / "alternatives.csv", "w", encoding="utf-8", newline="") as f:
            f.write("id;decision_id;option;pros;cons\n")
            f.write("ALT-001;DEC-001;Django;Built-in admin;High overhead\n")

        # Write mock audits.csv
        with open(src_agents / "audits.csv", "w", encoding="utf-8", newline="") as f:
            f.write("timestamp;audit_id;summary;alignment_score;auditor_team\n")
            f.write("2026-05-07T14:30:00;AUDIT-001;Alignment assessment;60%;F\n")

        # Write mock vote file
        with open(src_votes / "DEC-001.csv", "w", encoding="utf-8", newline="") as f:
            f.write("voter_id;team_id;vote;rationale\n")
            f.write("V-001;A;Drop Django;Functional is cleaner\n")

        # 2. Run Import
        import_csv_to_db(src_path, "test_project")

        # 3. Query DB to verify import succeeded
        session = db_manager.get_session(src_path)
        try:
            proj = session.query(Project).filter_by(id="test_project").first()
            assert proj is not None
            assert proj.name == "Test Project"

            team = session.query(Team).filter_by(id="A").first()
            assert team is not None
            assert team.vote_weight == 10

            dec = session.query(Decision).filter_by(id="DEC-001").first()
            assert dec is not None
            assert dec.decision == "Drop Django"

            alt = session.query(Alternative).filter_by(id="ALT-001").first()
            assert alt is not None
            assert alt.cons == "High overhead"

            audit = session.query(AuditLog).filter_by(id="AUDIT-001").first()
            assert audit is not None
            assert audit.alignment_score == 60.0

            prop = session.query(Proposal).filter_by(id="DEC-001").first()
            assert prop is not None
            assert prop.status == "RATIFIED"
            assert prop.votes[0]["vote"] == "Drop Django"
            assert prop.rationales[0]["rationale"] == "Functional is cleaner"

        finally:
            session.close()

        # 4. Run Export to dest_dir
        export_db_to_csv(src_path, "test_project")
        
        # Verify exported files exist and are correct in source directory
        dest_agents = src_agents
        assert (dest_agents / "teams.csv").exists()
        assert (dest_agents / "decisions.csv").exists()
        assert (dest_agents / "alternatives.csv").exists()
        assert (dest_agents / "audits.csv").exists()
        assert (dest_agents / "votes_manifest.csv").exists()
        assert (dest_agents / "votes" / "DEC-001.csv").exists()

        # Read exported decisions.csv to verify contents and semi-colon format
        with open(dest_agents / "decisions.csv", "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["id"] == "DEC-001"
            assert rows[0]["decision"] == "Drop Django"
            
        # Clean up database handles explicitly before exiting
        db_manager.close_all()
