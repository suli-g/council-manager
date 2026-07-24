"""
Active Team and Specialist Agent Registry.

Manages query lookups for registered specialist personas, vote weights, 
and system prompts, loading directly from SQLite or CSV tables.
"""

from pathlib import Path
from typing import List, Optional
from council_manager.db import db_manager, Team

class AgentRegistry:
    def get_teams(self, workspace_dir: str | Path) -> List[Team]:
        """Fetch all active teams registered in the project's SQLite database."""
        session = db_manager.get_session(workspace_dir)
        try:
            return session.query(Team).all()
        finally:
            session.close()

    def get_team(self, workspace_dir: str | Path, team_id: str) -> Optional[Team]:
        """Fetch a specific team's configuration by ID."""
        session = db_manager.get_session(workspace_dir)
        try:
            return session.query(Team).filter_by(id=team_id).first()
        finally:
            session.close()

agent_registry = AgentRegistry()
