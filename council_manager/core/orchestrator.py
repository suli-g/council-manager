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

    async def run_voting(
        self,
        workspace_dir: str | Path,
        proposal_id: str,
        max_cycles: int = 5
    ) -> Proposal:
        """Run Phase 2 (Voting): Conduct up to 5 cycles of blind weighted voting with feedback."""
        workspace_path = Path(workspace_dir).resolve()
        
        # 1. Fetch proposal details
        session = db_manager.get_session(workspace_path)
        try:
            proposal = session.query(Proposal).filter_by(id=proposal_id).first()
            if not proposal:
                raise ValueError(f"Proposal '{proposal_id}' not found.")
            topic = proposal.topic
            desc = proposal.description
            opts = proposal.options
            delib_rationales = proposal.rationales
        finally:
            session.close()

        # 2. Get registered teams
        teams = agent_registry.get_teams(workspace_path)
        if not teams:
            raise ValueError(f"No active teams registered in database at {workspace_path}")

        # Map team IDs to weights
        team_weight_map = {t.id: t.vote_weight for t in teams}
        total_active_weight = sum(team_weight_map.values())

        # Initialize debate context with Phase 1 deliberations
        rationales_context = "Deliberation Justifications:\n" + "\n".join(
            f"- {r['team_id']}: {r['rationale']}" for r in delib_rationales
        )

        final_votes = []
        final_status = "RATIFICATION_PENDING"
        prev_votes = []

        # 3. 5-Cycle Voting Loop
        for cycle in range(1, max_cycles + 1):
            if cycle > 1:
                # Compile previous cycle tallies and rationales into context
                tally = {}
                for v in prev_votes:
                    w = team_weight_map.get(v["team_id"], 10)
                    tally[v["vote"]] = tally.get(v["vote"], 0) + w
                
                tally_str = ", ".join(f"'{opt}': {wt} weight ({int(wt/total_active_weight*100)}%)" for opt, wt in tally.items())
                rationales_str = "\n".join(f"- {v['team_id']}: {v['rationale']}" for v in prev_votes)
                
                rationales_context = (
                    f"--- DEBATE CONTEXT (Cycle {cycle - 1} Results) ---\n"
                    f"Previous anonymous vote distribution: {tally_str}\n"
                    f"Previous rationales:\n{rationales_str}\n"
                    f"Reflect on opposing points of view and consider compromise."
                )

            # Query all team agents concurrently
            async def query_team_vote(team):
                res = await self.prompter.generate_vote_async(
                    team_name=team.name,
                    paradigm_specialty=team.paradigm_specialty,
                    title=topic,
                    description=desc,
                    options=opts,
                    rationales_context=rationales_context
                )
                return {
                    "voter_id": f"V-{team.id}",
                    "team_id": team.id,
                    "vote": res.vote,
                    "rationale": res.rationale,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

            tasks = [query_team_vote(t) for t in teams]
            cycle_votes = await asyncio.gather(*tasks)
            prev_votes = cycle_votes

            # Tally votes for this cycle
            tally = {}
            for v in cycle_votes:
                w = team_weight_map.get(v["team_id"], 10)
                tally[v["vote"]] = tally.get(v["vote"], 0) + w

            # Check for consensus (>70% weight)
            consensus_reached = False
            for opt, wt in tally.items():
                if wt >= 0.7 * total_active_weight:
                    final_votes = cycle_votes
                    consensus_reached = True
                    break

            if consensus_reached:
                break
        else:
            # Fallback if no consensus met after max_cycles: choose highest weighted option
            tally = {}
            for v in prev_votes:
                w = team_weight_map.get(v["team_id"], 10)
                tally[v["vote"]] = tally.get(v["vote"], 0) + w
            
            # Select majority winner
            majority_choice = max(tally, key=tally.get)
            final_votes = prev_votes

        # 4. Commit final votes and update proposal status
        session = db_manager.get_session(workspace_path)
        try:
            proposal = session.query(Proposal).filter_by(id=proposal_id).first()
            proposal.votes = final_votes
            proposal.status = final_status
            session.commit()
            session.refresh(proposal)
            return proposal
        finally:
            session.close()

council_orchestrator = CouncilOrchestrator()

