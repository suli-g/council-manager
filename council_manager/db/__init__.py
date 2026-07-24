"""
Database Connection and ORM Access Package.

Exposes the global DatabaseManager and SQLite database model schemas 
for active workspace storage.
"""

from council_manager.db.session import db_manager, DatabaseManager
from council_manager.db.models import (
    Project,
    Team,
    Proposal,
    Decision,
    Alternative,
    AuditLog,
    AuditDecision,
    RoadmapTask,
    BackgroundTask,
)
from council_manager.db.migration import (
    initialize_new_project,
    import_csv_to_db,
    export_db_to_csv,
)

__all__ = [
    "db_manager",
    "DatabaseManager",
    "Project",
    "Team",
    "Proposal",
    "Decision",
    "Alternative",
    "AuditLog",
    "AuditDecision",
    "RoadmapTask",
    "BackgroundTask",
    "initialize_new_project",
    "import_csv_to_db",
    "export_db_to_csv",
]
