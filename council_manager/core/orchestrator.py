"""
Consensus Deliberation and Voting Workflow Orchestrator.

Manages the lifecycle of a proposal from inception, through multi-team 
async deliberation, consensus voting loops, and final ratification.
"""

import asyncio
from datetime import datetime, timezone, date
from pathlib import Path
from typing import List, Optional, Callable
from council_manager.config import settings
from council_manager.db import db_manager, Proposal, Project, Decision, Alternative, RoadmapTask
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
        description: str,
        proposal_id: Optional[str] = None,
        topic: Optional[str] = None,
        options: Optional[List[str]] = None
    ) -> Proposal:
        """Create and persist a new proposal in the project's SQLite database."""
        workspace_path = Path(workspace_dir).resolve()
        
        if settings.debug:
            print(f"[DEBUG] orchestrator: Creating/updating proposal. project_id={project_id}, proposal_id={proposal_id}, topic={topic}")

        # 1. Generate proposal_id if not provided
        if not proposal_id:
            session = db_manager.get_session(workspace_path)
            try:
                count = session.query(Proposal).count()
                proposal_id = f"DEC-{count + 1:03d}"
                while session.query(Proposal).filter_by(id=proposal_id).first():
                    count += 1
                    proposal_id = f"DEC-{count + 1:03d}"
            finally:
                session.close()

        # 2. Extract topic and options via Gemini if either is omitted
        if not topic or not options:
            if settings.debug:
                print("[DEBUG] orchestrator: Topic or options omitted. Querying AI proposal inception generator...")
            try:
                self.prompter.probe_connectivity()
                inception = self.prompter.generate_proposal_inception(description)
                if not topic:
                    topic = inception.topic
                if not options:
                    options = inception.options
            except Exception as e:
                if settings.debug:
                    print(f"[DEBUG] orchestrator: Proposal inception extraction failed ({e}). Using heuristics/default fallback.")
                # Safe fallback if GenAI fails (e.g. offline during tests)
                if not topic:
                    topic = description[:30].strip() + "..."
                if not options:
                    options = ["Adopt Proposal", "Keep Status Quo"]

        if settings.debug:
            print(f"[DEBUG] orchestrator: Saving proposal '{proposal_id}' to SQLite database at: {workspace_path}")
        session = db_manager.get_session(workspace_path)
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
            if settings.debug:
                print(f"[DEBUG] orchestrator: Proposal '{proposal_id}' saved successfully. Status: {proposal.status}")
            return proposal
        finally:
            session.close()


    async def run_deliberation(
        self,
        workspace_dir: str | Path,
        proposal_id: str,
        on_progress: Optional[Callable[[str, str, str, float], None]] = None
    ) -> Proposal:
        """Run Phase 1 (Deliberation): Collect agent rationales concurrently and save to database."""
        if settings.debug:
            print(f"[DEBUG] orchestrator: Starting Phase 1 Deliberation for proposal '{proposal_id}'")
        await self.prompter.probe_connectivity_async()
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

        if settings.debug:
            print(f"[DEBUG] orchestrator: Loaded {len(teams)} teams for deliberation: {[t.id for t in teams]}")

        # 3. Formulate and run concurrent prompter tasks
        async def query_team_deliberation(team):
            start_time = asyncio.get_event_loop().time()
            if on_progress:
                try:
                    on_progress(team.id, team.name, "STARTED", 0.0)
                except Exception:
                    pass
            if settings.debug:
                print(f"[DEBUG] orchestrator: Requesting deliberation from Team '{team.id}' ({team.name})")
            delib_res = await self.prompter.generate_deliberation_async(
                team_name=team.name,
                paradigm_specialty=team.paradigm_specialty,
                title=topic,
                description=desc,
                options=opts
            )
            end_time = asyncio.get_event_loop().time()
            elapsed = end_time - start_time
            if on_progress:
                try:
                    on_progress(team.id, team.name, "COMPLETED", elapsed)
                except Exception:
                    pass
            if settings.debug:
                print(f"[DEBUG] orchestrator: Received deliberation rationale from Team '{team.id}' in {elapsed:.2f}s")
            return {
                "team_id": team.id,
                "rationale": {
                    "stance": delib_res.stance,
                    "motivation": delib_res.motivation,
                    "suggestion": delib_res.suggestion
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        tasks = [query_team_deliberation(t) for t in teams]
        if settings.debug:
            print("[DEBUG] orchestrator: Spawning concurrent team deliberation queries...")
        collected_rationales = await asyncio.gather(*tasks)

        # 4. Commit rationales and transition status to VOTING_PENDING
        session = db_manager.get_session(workspace_path)
        try:
            proposal = session.query(Proposal).filter_by(id=proposal_id).first()
            proposal.rationales = collected_rationales
            proposal.status = "VOTING_PENDING"
            session.commit()
            session.refresh(proposal)
            if settings.debug:
                print(f"[DEBUG] orchestrator: Deliberation complete. Status updated to '{proposal.status}'")
            return proposal
        finally:
            session.close()

    async def run_voting(
        self,
        workspace_dir: str | Path,
        proposal_id: str,
        max_cycles: int = 5,
        on_cycle_complete: Optional[Callable[[int, int, dict, bool], None]] = None
    ) -> Proposal:
        """Run Phase 2 (Voting): Conduct up to 5 cycles of blind weighted voting with feedback."""
        if settings.debug:
            print(f"[DEBUG] orchestrator: Starting Phase 2 Voting Loop for proposal '{proposal_id}'. max_cycles={max_cycles}")
        await self.prompter.probe_connectivity_async()
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

        if settings.debug:
            print(f"[DEBUG] orchestrator: Loaded {len(teams)} voting teams. Total active weight: {total_active_weight}")

        # Initialize debate context with Phase 1 deliberations (truncated to prevent context window overflow)
        rationales_context = "Deliberation Justifications:\n" + "\n".join(
            f"- {r['team_id']}: {r['rationale'][:400] + '...' if len(r['rationale']) > 400 else r['rationale']}" for r in delib_rationales
        )

        final_votes = []
        final_status = "RATIFICATION_PENDING"
        prev_votes = []

        # 3. 5-Cycle Voting Loop
        for cycle in range(1, max_cycles + 1):
            if settings.debug:
                print(f"[DEBUG] orchestrator: --- Cycle {cycle} ---")
            if cycle > 1:
                # Compile previous cycle tallies and rationales into context
                tally = {}
                for v in prev_votes:
                    w = team_weight_map.get(v["team_id"], 10)
                    tally[v["vote"]] = tally.get(v["vote"], 0) + w
                
                tally_str = ", ".join(f"'{opt}': {wt} weight ({int(wt/total_active_weight*100)}%)" for opt, wt in tally.items())
                rationales_str = "\n".join(f"- {v['team_id']}: {v['rationale']}" for v in prev_votes)
                
                if settings.debug:
                    print(f"[DEBUG] orchestrator: Tally from Cycle {cycle - 1}: {tally_str}")

                rationales_context = (
                    f"--- DEBATE CONTEXT (Cycle {cycle - 1} Results) ---\n"
                    f"Previous anonymous vote distribution: {tally_str}\n"
                    f"Previous rationales:\n{rationales_str}\n"
                    f"Reflect on opposing points of view and consider compromise."
                )

            # Query all team agents concurrently
            async def query_team_vote(team):
                if settings.debug:
                    print(f"[DEBUG] orchestrator: Requesting vote from Team '{team.id}' ({team.name})")
                res = await self.prompter.generate_vote_async(
                    team_name=team.name,
                    paradigm_specialty=team.paradigm_specialty,
                    title=topic,
                    description=desc,
                    options=opts,
                    rationales_context=rationales_context
                )
                if settings.debug:
                    print(f"[DEBUG] orchestrator: Team '{team.id}' voted: '{res.vote}'")
                return {
                    "voter_id": f"V-{team.id}",
                    "team_id": team.id,
                    "vote": res.vote,
                    "rationale": res.rationale,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

            tasks = [query_team_vote(t) for t in teams]
            if settings.debug:
                print(f"[DEBUG] orchestrator: Spawning concurrent team vote queries for Cycle {cycle}...")
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
                pct = int(wt / total_active_weight * 100)
                if settings.debug:
                    print(f"[DEBUG] orchestrator: Tally option '{opt}': {wt} weight ({pct}%)")
                if wt >= 0.7 * total_active_weight:
                    final_votes = cycle_votes
                    consensus_reached = True
                    if settings.debug:
                        print(f"[DEBUG] orchestrator: Consensus REACHED (>70% threshold) on option '{opt}'!")
                    break

            if on_cycle_complete:
                try:
                    on_cycle_complete(cycle, max_cycles, tally, consensus_reached)
                except Exception:
                    pass

            if consensus_reached:
                break
            else:
                if settings.debug:
                    print(f"[DEBUG] orchestrator: Consensus NOT reached in Cycle {cycle} (threshold 70%).")
        else:
            # Fallback if no consensus met after max_cycles: choose highest weighted option
            tally = {}
            for v in prev_votes:
                w = team_weight_map.get(v["team_id"], 10)
                tally[v["vote"]] = tally.get(v["vote"], 0) + w
            
            # Select majority winner
            _majority_choice = max(tally, key=tally.get)
            if settings.debug:
                print(f"[DEBUG] orchestrator: Max cycles reached without consensus. Defaulting to majority option: '{_majority_choice}'")
            final_votes = prev_votes

        # 4. Commit final votes and update proposal status
        if settings.debug:
            print(f"[DEBUG] orchestrator: Committing voting results to database. Status: {final_status}")
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

    def ratify_proposal(
        self,
        workspace_dir: str | Path,
        proposal_id: str,
        decision_option: str,
        roadmap_task_id: Optional[str] = None,
        human_ratified: bool = False,
        verification_token: Optional[str] = None
    ) -> None:
        """Ratify a proposal, record decision and alternatives, update roadmap, and export to CSV."""
        from council_manager.core.gatekeeper import gatekeeper
        gatekeeper.verify_ratification_authority(
            proposal_id=proposal_id,
            human_ratified=human_ratified,
            verification_token=verification_token
        )

        workspace_path = Path(workspace_dir).resolve()
        session = db_manager.get_session(workspace_path)
        try:
            proposal = session.query(Proposal).filter_by(id=proposal_id).first()
            if not proposal:
                raise ValueError(f"Proposal '{proposal_id}' not found.")
            
            # Verify option exists
            if decision_option not in proposal.options:
                raise ValueError(f"Option '{decision_option}' not found in proposal options: {proposal.options}")
                
            # 1. Update proposal status
            proposal.status = "RATIFIED"
            
            # 2. Record Decision
            existing_dec = session.query(Decision).filter_by(id=proposal.id).first()
            if existing_dec:
                session.delete(existing_dec)
            
            new_decision = Decision(
                id=proposal.id,
                project_id=proposal.project_id,
                date=date.today(),
                topic=proposal.topic,
                decision=decision_option,
                rationale=proposal.description
            )
            session.add(new_decision)
            
            # 3. Record Alternatives (other options)
            session.query(Alternative).filter_by(decision_id=proposal.id).delete()
            
            alt_count = 1
            for opt in proposal.options:
                if opt != decision_option:
                    # e.g., if ID is DEC-083, alt ID is ALT-0831, ALT-0832, etc.
                    clean_id = "".join(filter(str.isdigit, proposal.id))
                    alt_id = f"ALT-{clean_id}{alt_count}"
                    new_alt = Alternative(
                        id=alt_id,
                        decision_id=proposal.id,
                        option=opt,
                        pros="Identified during voting cycle",
                        cons="Non-consensus choice"
                    )
                    session.add(new_alt)
                    alt_count += 1
                    
            # 4. Update Roadmap Task if requested
            if roadmap_task_id:
                task = session.query(RoadmapTask).filter_by(id=roadmap_task_id, project_id=proposal.project_id).first()
                if not task:
                    raise ValueError(f"Roadmap task '{roadmap_task_id}' not found for project '{proposal.project_id}'")
                task.status = "DONE"
                
            session.commit()
            
            # 5. Export back to CSVs to ensure synchronization
            from council_manager.db.migration import export_db_to_csv
            export_db_to_csv(workspace_path, proposal.project_id)
            
        finally:
            session.close()


council_orchestrator = CouncilOrchestrator()

