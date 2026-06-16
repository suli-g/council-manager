import os
import tempfile
from pathlib import Path
from sqlalchemy import text
from council_manager.db import db_manager, Project

def test_project_isolation():
    with tempfile.TemporaryDirectory() as dir1, tempfile.TemporaryDirectory() as dir2:
        path1 = Path(dir1)
        path2 = Path(dir2)

        # Connect to db in first workspace
        session1 = db_manager.get_session(path1)
        
        # Verify db file is created
        db_file1 = db_manager.get_db_path(path1)
        assert db_file1.exists()

        # Insert a project in workspace 1
        p1 = Project(id="project1", name="Project 1")
        session1.add(p1)
        session1.commit()
        session1.close()

        # Connect to db in second workspace
        session2 = db_manager.get_session(path2)
        db_file2 = db_manager.get_db_path(path2)
        assert db_file2.exists()

        # Verify project1 does NOT exist in workspace 2 (isolation check)
        p_check = session2.query(Project).filter_by(id="project1").first()
        assert p_check is None
        session2.close()

        # Release all connection file locks before exiting the TemporaryDirectory contexts
        db_manager.close_all()

def test_sqlite_wal_mode():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        session = db_manager.get_session(path)
        
        # Execute raw query to verify journal_mode is WAL
        result = session.execute(text("PRAGMA journal_mode")).scalar()
        assert result.lower() == "wal"
        session.close()

        # Release connection file locks
        db_manager.close_all()
