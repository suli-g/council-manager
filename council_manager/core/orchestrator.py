import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from council_manager.db import db_manager, Proposal, Project
from council_manager.core.registry import agent_registry
from council_manager.core.prompter import AgentPrompter

class CouncilOrchestrator:
    def __init__(self, prompter: Optional[AgentPrompter] = None):
        self._prompter = prompter or AgentPrompter()

    @property
    def prompter(self) -> AgentPrompter:
        return self._prompter

    def create_proposal(
        self,
        workspace_dir: str | Path,
        project_id: str,
        proposal_id: str,
        topic: str,
        description: str,
        options: List[str]
    ) -> Proposal:
        """Create and persist a new proposal in the project's SQLite database."""
        session = db_manager.get_session(workspace_dir)
        try:
            # Ensure Project context exists
            project = session.query(Project).filter_by(id=project_id).first()
            if not project:
                project = Project(id=project_id, name=project_id.replace("_", " ").title())
                session.add(project)
                session.commit()

            proposal = session.query(Proposal).filter_by(id=proposal_id).first()
            if proposal:
                # Update existing
                proposal.topic = topic
                proposal.description = description
                proposal.options = options
                proposal.status = "DELIBERATION_PENDING"
            else:
                proposal = Proposal(
                    id=proposal_id,
                    project_id=project_id,
                    topic=topic,
                    description=description,
                    options=options,
                    status="DELIBERATION_PENDING"
                )
                session.add(proposal)
            session.commit()
            
            # Refresh to detach clean instance
            session.refresh(proposal)
            return proposal
        finally:
            session.close()

    async def run_deliberation(
        self,
        workspace_dir: str | Path,
        proposal_id: str
    ) -> Proposal:
        """Run Phase 1 (Deliberation): Collect agent rationales concurrently and save to database."""
        workspace_path = Path(workspace_dir).resolve()
        
        # 1. Fetch proposal and update status to DELIBERATION
        session = db_manager.get_session(workspace_path)
        try:
            proposal = session.query(Proposal).filter_by(id=proposal_id).first()
            if not proposal:
                raise ValueError(f"Proposal '{proposal_id}' not found in database.")
            
            proposal.status = "DELIBERATION"
            session.commit()
            
            # Extract basic info
            topic = proposal.topic
            desc = proposal.description
            opts = proposal.options
        finally:
            session.close()

        # 2. Load active teams from registry
        teams = agent_registry.get_teams(workspace_path)
        if not teams:
            raise ValueError(f"No active teams registered in the project database at {workspace_path}")

        # 3. Formulate and run concurrent prompter tasks
        async def query_team_deliberation(team):
            rationale_text = await self.prompter.generate_deliberation_async(
                team_name=team.name,
                paradigm_specialty=team.paradigm_specialty,
                title=topic,
                description=desc,
                options=opts
            )
            return {
                "team_id": team.id,
                "rationale": rationale_text,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        tasks = [query_team_deliberation(t) for t in teams]
        collected_rationales = await asyncio.gather(*tasks)

        # 4. Commit rationales and transition status to VOTING_PENDING
        session = db_manager.get_session(workspace_path)
        try:
            proposal = session.query(Proposal).filter_by(id=proposal_id).first()
            proposal.rationales = collected_rationales
            proposal.status = "VOTING_PENDING"
            session.commit()
            session.refresh(proposal)
            return proposal
        finally:
            session.close()

council_orchestrator = CouncilOrchestrator()
