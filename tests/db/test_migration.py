import csv
import tempfile
import pytest
from pathlib import Path
from council_manager.db import db_manager, Project, Team, Proposal, Decision, Alternative, AuditLog, AuditDecision
from council_manager.db.migration import import_csv_to_db, export_db_to_csv, initialize_new_project

@pytest.fixture(autouse=True)
def cleanup_connections():
    yield
    db_manager.close_all()

def test_migration_bidirectional():
    with tempfile.TemporaryDirectory() as src_dir, tempfile.TemporaryDirectory() as dest_dir:
        src_path = Path(src_dir)
        _dest_path = Path(dest_dir)

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

        # Write mock audit_decisions.csv
        with open(src_agents / "audit_decisions.csv", "w", encoding="utf-8", newline="") as f:
            f.write("audit_id;decision_id;status;re_audit_date;notes\n")
            f.write("AUDIT-001;DEC-001;FIXED;2026-05-15;Refactored code\n")

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

            audit_dec = session.query(AuditDecision).filter_by(audit_id="AUDIT-001", decision_id="DEC-001").first()
            assert audit_dec is not None
            assert audit_dec.status == "FIXED"
            assert audit_dec.notes == "Refactored code"

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
        assert (dest_agents / "audit_decisions.csv").exists()
        assert (dest_agents / "votes_manifest.csv").exists()
        assert (dest_agents / "votes" / "DEC-001.csv").exists()

        # Read exported audit_decisions.csv to verify contents and format
        with open(dest_agents / "audit_decisions.csv", "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["audit_id"] == "AUDIT-001"
            assert rows[0]["decision_id"] == "DEC-001"
            assert rows[0]["status"] == "FIXED"
            assert rows[0]["re_audit_date"] == "2026-05-15"
            assert rows[0]["notes"] == "Refactored code"

        # Read exported decisions.csv to verify contents and semi-colon format
        with open(dest_agents / "decisions.csv", "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["id"] == "DEC-001"
            assert rows[0]["decision"] == "Drop Django"
            
        # Clean up database handles explicitly before exiting
        db_manager.close_all()

def test_migration_missing_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        # 1. Verify that FileNotFoundError is raised if no .agents directory exists
        with pytest.raises(FileNotFoundError, match="No .agents/ directory found"):
            import_csv_to_db(workspace, "test_proj")
            
        # 2. Create an empty .agents directory and verify it imports 0 items gracefully
        agents = workspace / ".agents"
        agents.mkdir()
        import_csv_to_db(workspace, "test_proj")
        
        session = db_manager.get_session(workspace)
        teams = session.query(Team).all()
        assert len(teams) == 0
        session.close()
        db_manager.close_all()


def test_migration_legacy_votes_dynamic_voter():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        
        # Setup source folder structure with a legacy vote file lacking voter_id column
        agents = workspace / ".agents"
        agents.mkdir()
        votes_dir = agents / "votes"
        votes_dir.mkdir()
        
        with open(agents / "teams.csv", "w", encoding="utf-8", newline="") as f:
            f.write("team_id;team_name;count;paradigm_specialty\n")
            f.write("G;Contrarians;10;Devil's advocacy\n")
            
        with open(agents / "decisions.csv", "w", encoding="utf-8", newline="") as f:
            f.write("id;date;topic;decision;rationale\n")
            f.write("DEC-002;2026-06-01;Topic;Decision;Rationale\n")
            
        # Legacy votes file: no voter_id column, only team_id, vote, rationale
        with open(votes_dir / "DEC-002.csv", "w", encoding="utf-8", newline="") as f:
            f.write("team_id;vote;rationale\n")
            f.write("G;Option X;Contrarian view rationale\n")
            
        # Run import
        import_csv_to_db(workspace, "legacy_project")
        
        # Verify proposal and votes table was successfully populated and voter_id was resolved to V-G
        session = db_manager.get_session(workspace)
        try:
            prop = session.query(Proposal).filter_by(id="DEC-002").first()
            assert prop is not None
            assert len(prop.votes) == 1
            assert prop.votes[0]["voter_id"] == "V-G"
            assert prop.votes[0]["team_id"] == "G"
            assert prop.votes[0]["vote"] == "Option X"
        finally:
            session.close()
            db_manager.close_all()

def test_initialize_new_project():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        
        # Initialize
        initialize_new_project(workspace, "my_new_project")
        
        # Verify files were created
        assert (workspace / ".agents" / "teams.csv").exists()
        assert (workspace / ".agents" / "decisions.csv").exists()
        assert (workspace / ".agents" / "roadmap.csv").exists()
        
        # Verify DB was created and seeded
        assert db_manager.get_db_path(workspace).exists()
        
        session = db_manager.get_session(workspace)
        try:
            # Check default teams
            teams = session.query(Team).all()
            assert len(teams) == 7
            team_ids = {t.id for t in teams}
            assert "A" in team_ids
            assert "G" in team_ids
        finally:
            session.close()
            db_manager.close_all()

def test_initialize_new_project_with_custom_values():
    import tempfile
    from council_manager.db import Team, Decision
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        
        initialize_new_project(
            workspace, 
            "my_new_project", 
            project_name="Custom Name", 
            global_member_count=15, 
            project_description="This is a custom project description for testing."
        )
        
        # Verify custom member count in CSV
        teams_csv = workspace / ".agents" / "teams.csv"
        assert teams_csv.exists()
        with open(teams_csv, "r", encoding="utf-8") as f:
            content = f.read()
            assert ";15;" in content

        # Verify DEC-001 in decisions.csv
        dec_csv = workspace / ".agents" / "decisions.csv"
        assert dec_csv.exists()
        with open(dec_csv, "r", encoding="utf-8") as f:
            content = f.read()
            assert "DEC-001;" in content
            assert "Custom Name" in content
            assert "This is a custom project description for testing." in content
            
        # Verify DB was seeded correctly
        session = db_manager.get_session(workspace)
        try:
            teams = session.query(Team).all()
            assert len(teams) == 7
            for t in teams:
                assert t.vote_weight == 15
                
            dec = session.query(Decision).filter_by(id="DEC-001").first()
            assert dec is not None
            assert dec.topic == "Project Onboarding"
            assert dec.decision == "Onboard Project Custom Name"
            assert dec.rationale == "This is a custom project description for testing."
        finally:
            session.close()
            db_manager.close_all()


def test_initialize_new_project_custom_teams_and_skills():
    with tempfile.TemporaryDirectory() as tmp_dir:
        workspace = Path(tmp_dir)
        
        custom_teams = [
            {"id": "A", "name": "Pedagogy Specialists", "specialty": "Learning theories"},
            {"id": "B", "name": "Curriculum Setters", "specialty": "Syllabus design"},
            {"id": "C", "name": "Assessment Designers", "specialty": "Testing and rubrics"},
            {"id": "D", "name": "Instructional Tech", "specialty": "E-learning"},
            {"id": "E", "name": "Student Experience", "specialty": "Accessibility"},
            {"id": "F", "name": "Program Administrators", "specialty": "Resource allocation"},
            {"id": "G", "name": "Contrarians", "specialty": "Devil's Advocacy"}
        ]
        
        initialize_new_project(
            workspace,
            "custom_council_project",
            project_name="Custom Council Project",
            global_member_count=12,
            project_description="Testing custom council and skills generation.",
            custom_teams=custom_teams
        )
        
        # 1. Verify custom teams in CSV
        teams_csv = workspace / ".agents" / "teams.csv"
        assert teams_csv.exists()
        with open(teams_csv, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) == 8  # header + 7 teams
            assert "A;Pedagogy Specialists;12;Learning theories\n" in lines
            assert "G;Contrarians;12;Devil's Advocacy\n" in lines
            
        # 2. Verify project-council skill generation
        skill_md = workspace / ".agents" / "skills" / "project-council" / "SKILL.md"
        assert skill_md.exists()
        with open(skill_md, "r", encoding="utf-8") as f:
            content = f.read()
            assert "name: project-council" in content
            assert "- **Team A (Pedagogy Specialists)**: Learning theories" in content
            assert "- **Team G (Contrarians)**: Devil's Advocacy" in content
            assert "Official Tool Delegation (Critical)" in content
            assert "council-manager deliberate" in content

        # 3. Verify skills.json registration
        skills_json = workspace / ".agents" / "skills.json"
        assert skills_json.exists()
        import json
        with open(skills_json, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert "entries" in data
            paths = [entry["path"] for entry in data["entries"]]
            assert any("council-manager" in p for p in paths)
            assert any("project-council" in p for p in paths)

        # 4. Verify DB was seeded with custom teams
        session = db_manager.get_session(workspace)
        try:
            teams = session.query(Team).all()
            assert len(teams) == 7
            team_a = session.query(Team).filter_by(id="A").first()
            assert team_a is not None
            assert team_a.name == "Pedagogy Specialists"
            assert team_a.vote_weight == 12
            assert team_a.paradigm_specialty == "Learning theories"
        finally:
            session.close()
            db_manager.close_all()


class MockArgs:
    def __init__(self, path, fix_missing=False, project_id=None, name=None, description=None, member_count=None, council_template=None):
        self.path = str(path)
        self.fix_missing = fix_missing
        self.project_id = project_id
        self.name = name
        self.description = description
        self.member_count = member_count
        self.council_template = council_template


def test_cmd_init_project_fix_missing():
    from council_manager.cli import cmd_init_project
    with tempfile.TemporaryDirectory() as tmp_dir:
        workspace = Path(tmp_dir)
        
        initialize_new_project(
            workspace,
            "fix_missing_test",
            project_name="Fix Missing Test",
            global_member_count=5,
            project_description="Test project"
        )
        
        project_council_md = workspace / ".agents" / "skills" / "project-council" / "SKILL.md"
        skills_json = workspace / ".agents" / "skills.json"
        
        if project_council_md.exists():
            project_council_md.unlink()
        if skills_json.exists():
            skills_json.unlink()
            
        assert not project_council_md.exists()
        assert not skills_json.exists()
        
        args = MockArgs(path=workspace, fix_missing=True)
        cmd_init_project(args)
        
        assert project_council_md.exists()
        assert skills_json.exists()
        with open(project_council_md, "r", encoding="utf-8") as f:
            content = f.read()
            assert "Official Tool Delegation (Critical)" in content



