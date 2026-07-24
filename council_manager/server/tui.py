"""
Textual TUI Dashboard and User Interaction Interface.

Runs the terminal dashboard display, monitors background task execution events 
via WebSocket connections, and displays interactive modal popups for 
proposal deliberations and ratification flows.
"""

from pathlib import Path
from datetime import datetime
from typing import Generator, List, Dict, Any, Optional
import asyncio

from sqlalchemy.orm import Session
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, DataTable, Label, Button, TabbedContent, TabPane, Static, Input
from textual.coordinate import Coordinate
from textual.worker import Worker, WorkerState
from textual.screen import ModalScreen

from council_manager.db import db_manager, Proposal, Decision, Alternative, AuditLog, RoadmapTask, Project
from council_manager.config import settings
from council_manager.core.orchestrator import council_orchestrator
from council_manager.core.prompter import format_rationale
from textual.events import Event

class WorkerStateChanged(Event):
    def __init__(self, worker: Worker, state: WorkerState) -> None:
        super().__init__()
        self.worker = worker
        self.state = state

class ProposalCreateModal(ModalScreen[dict | None]):
    """Modal screen for creating a new proposal within the TUI."""
    
    def compose(self) -> ComposeResult:
        with Vertical(id="modal-container"):
            yield Label("[bold cyan]Create New Proposal[/bold cyan]", classes="modal-field")
            yield Label("Description:")
            yield Input(placeholder="Describe the proposal or issue...", id="input-desc", classes="modal-field")
            yield Label("Topic / Title (optional):")
            yield Input(placeholder="e.g. Database Architecture (leaves blank for auto-inception)", id="input-topic", classes="modal-field")
            yield Label("Options (semicolon-delimited, optional):")
            yield Input(placeholder="e.g. Option A; Option B; Option C (leaves blank for auto-inception)", id="input-options", classes="modal-field")
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", id="btn-cancel", variant="error")
                yield Button("Create", id="btn-create-submit", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-create-submit":
            desc = self.query_one("#input-desc", Input).value.strip()
            if not desc:
                self.notify("Description is required.", severity="error")
                return
            
            topic = self.query_one("#input-topic", Input).value.strip() or None
            opts_str = self.query_one("#input-options", Input).value.strip()
            options = [o.strip() for o in opts_str.split(";")] if opts_str else None
            # Filter out empty options
            if options:
                options = [o for o in options if o]
                if not options:
                    options = None
            
            self.dismiss({
                "description": desc,
                "topic": topic,
                "options": options
            })

class CouncilDashboardApp(App):
    """
    An interactive Terminal User Interface (TUI) dashboard for Council Manager.
    Visualizes proposals, agent rationales, voting records, ratified decisions,
    roadmap task completion progress, and audit history.
    """
    
    CSS = """
    Screen {
        background: #0f172a;
        color: #e2e8f0;
    }
    
    TabbedContent {
        height: 1fr;
    }
    
    DataTable {
        height: 1fr;
        border: solid #334155;
        background: #1e293b;
    }
    
    DataTable:focus {
        border: double #38bdf8;
    }
    
    .pane {
        padding: 1;
        border: solid #334155;
        background: #1e293b;
        height: 1fr;
    }
    
    .detail-title {
        text-style: bold;
        color: #38bdf8;
        margin-bottom: 1;
        background: #1e293b;
        padding-left: 1;
    }
    
    .button-bar {
        height: 3;
        margin-top: 1;
        background: #1e293b;
    }
    
    Button {
        margin-right: 1;
        min-width: 14;
    }
    
    #proposal-detail-scroll {
        width: 1fr;
        height: 1fr;
        background: #0f172a;
        border: solid #334155;
        padding: 1;
    }
    
    #roadmap-progress-label {
        background: #0f172a;
        padding: 1;
        color: #10b981;
        text-style: bold;
    }

    #proposals-list-pane {
        width: 40%;
        height: 1fr;
    }
    
    #proposal-detail-pane {
        width: 60%;
        height: 1fr;
    }

    #decisions-list-pane {
        width: 50%;
        height: 1fr;
    }

    #decision-detail-pane {
        width: 50%;
        height: 1fr;
    }

    ProposalCreateModal {
        align: center middle;
    }
    
    #modal-container {
        width: 60;
        height: auto;
        border: thick #38bdf8;
        background: #1e293b;
        padding: 1 2;
    }
    
    .modal-field {
        margin-bottom: 1;
    }
    
    .modal-buttons {
        margin-top: 1;
        height: 3;
        align: right middle;
    }
    
    .modal-buttons Button {
        margin-left: 1;
    }
    """
    
    BINDINGS = [
        ("r", "refresh", "Refresh Data"),
        ("n", "new_proposal", "New Proposal"),
        ("d", "deliberate", "Deliberate selected"),
        ("v", "vote", "Vote selected"),
        ("q", "quit", "Quit Dashboard"),
    ]
    
    def __init__(self, workspace: str | Path | None = None):
        super().__init__()
        self.workspace = Path(workspace or ".").resolve()
        self.selected_proposal_id = None
        self.selected_decision_id = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent():
            with TabPane("Proposals", id="proposals-tab"):
                with Horizontal():
                    with Vertical(id="proposals-list-pane"):
                        yield Label("Active Proposals", classes="detail-title")
                        yield DataTable(id="proposals-table")
                    with Vertical(id="proposal-detail-pane", classes="pane"):
                        yield Label("Proposal Details & Votes Tally", classes="detail-title")
                        with ScrollableContainer(id="proposal-detail-scroll"):
                            yield Static(id="proposal-detail-content")
                        with Horizontal(classes="button-bar"):
                            yield Button("New Proposal", id="btn-new-proposal")
                            yield Button("Deliberate", id="btn-deliberate", variant="primary")
                            yield Button("Vote Loop", id="btn-vote", variant="success")
                            yield Button("Refresh", id="btn-refresh")

            with TabPane("Ratified Decisions", id="decisions-tab"):
                with Horizontal():
                    with Vertical(id="decisions-list-pane"):
                        yield Label("Ratified Decisions Log", classes="detail-title")
                        yield DataTable(id="decisions-table")
                    with Vertical(id="decision-detail-pane", classes="pane"):
                        yield Label("Alternatives Evaluated", classes="detail-title")
                        with ScrollableContainer():
                            yield Static(id="alternatives-content")
            with TabPane("Roadmap Tasks", id="roadmap-tab"):
                with Vertical():
                    yield Label("Project Roadmap Progress", id="roadmap-progress-label")
                    yield DataTable(id="roadmap-table")
            with TabPane("Compliance Audits", id="audits-tab"):
                yield DataTable(id="audits-table")
        yield Footer()

    def on_mount(self) -> None:
        # Set up table columns and options
        p_table = self.query_one("#proposals-table", DataTable)
        p_table.cursor_type = "row"
        p_table.add_columns("ID", "Topic", "Status")
        
        d_table = self.query_one("#decisions-table", DataTable)
        d_table.cursor_type = "row"
        d_table.add_columns("ID", "Date", "Topic", "Decision")
        
        r_table = self.query_one("#roadmap-table", DataTable)
        r_table.cursor_type = "row"
        r_table.add_columns("Phase", "Task ID", "Task Name", "Status")
        
        a_table = self.query_one("#audits-table", DataTable)
        a_table.cursor_type = "row"
        a_table.add_columns("Timestamp", "ID", "Team", "Score", "Summary")
        
        self.refresh_all()

    def refresh_all(self) -> None:
        self.load_proposals()
        self.load_decisions()
        self.load_roadmap()
        self.load_audits()
        self.notify("Dashboard data reloaded.", title="System Update", severity="info")

    def load_proposals(self) -> None:
        table = self.query_one("#proposals-table", DataTable)
        table.clear()
        
        session = db_manager.get_session(self.workspace)
        try:
            proposals = session.query(Proposal).order_by(Proposal.created_at.desc()).all()
            for p in proposals:
                table.add_row(p.id, p.topic or "(AI Inception Pending)", p.status, key=p.id)
            
            # Select the first proposal if none is selected
            if proposals:
                if not self.selected_proposal_id or self.selected_proposal_id not in [p.id for p in proposals]:
                    self.selected_proposal_id = proposals[0].id
                self.show_proposal_detail(self.selected_proposal_id)
            else:
                self.query_one("#proposal-detail-content", Static).update("No proposals found in database.")
        finally:
            session.close()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        table_id = event.data_table.id
        row_key = event.row_key.value
        
        if table_id == "proposals-table":
            self.selected_proposal_id = row_key
            self.show_proposal_detail(row_key)
        elif table_id == "decisions-table":
            self.selected_decision_id = row_key
            self.show_decision_alternatives(row_key)

    def show_proposal_detail(self, proposal_id: str) -> None:
        content = self.query_one("#proposal-detail-content", Static)
        
        session = db_manager.get_session(self.workspace)
        try:
            prop = session.query(Proposal).filter_by(id=proposal_id).first()
            if not prop:
                content.update(f"Proposal '{proposal_id}' not found.")
                return
                
            text = f"[bold cyan]ID:[/bold cyan] {prop.id}\n"
            text += f"[bold cyan]Project:[/bold cyan] {prop.project_id}\n"
            text += f"[bold cyan]Topic:[/bold cyan] {prop.topic or 'AI Topic Generation Pending'}\n"
            text += f"[bold cyan]Status:[/bold cyan] [bold green]{prop.status}[/bold green]\n"
            text += f"[bold cyan]Description:[/bold cyan] {prop.description}\n\n"
            
            text += "[bold yellow]═══════ Options ═══════[/bold yellow]\n"
            for opt in prop.options or []:
                text += f" • {opt}\n"
            text += "\n"
            
            # Show Votes count/distribution if they exist
            if prop.votes:
                text += "[bold yellow]═══════ Consensus Votes ═══════[/bold yellow]\n"
                tally = {}
                for v in prop.votes:
                    vote_val = v.get("vote", "Unknown")
                    tally[vote_val] = tally.get(vote_val, 0) + 1
                    
                for opt, count in tally.items():
                    text += f" • [green]{opt}[/green]: {count} votes\n"
                text += "\n"
                
            # Show team rationales collected
            if prop.rationales:
                text += "[bold yellow]═══════ Deliberation Reports ═══════[/bold yellow]\n"
                text += "### PROPOSAL\n"
                text += f"{prop.description}\n\n"
                text += "### Stances:\n\n"
                for rat in prop.rationales:
                    team = rat.get("team_id", "Unknown")
                    formatted = format_rationale(rat.get("rationale", ""))
                    text += f"Team: {team}\n{formatted}\n"
                    text += "────────────────────────────────────────────────\n"
            else:
                text += "[italic #94a3b8]No team deliberation justifications collected yet.[/italic #94a3b8]\n"
                
            content.update(text)
        finally:
            session.close()

    def load_decisions(self) -> None:
        table = self.query_one("#decisions-table", DataTable)
        table.clear()
        
        session = db_manager.get_session(self.workspace)
        try:
            decisions = session.query(Decision).order_by(Decision.date.desc(), Decision.id.desc()).all()
            for d in decisions:
                table.add_row(d.id, d.date.strftime("%Y-%m-%d"), d.topic, d.decision, key=d.id)
                
            if decisions:
                if not self.selected_decision_id or self.selected_decision_id not in [d.id for d in decisions]:
                    self.selected_decision_id = decisions[0].id
                self.show_decision_alternatives(self.selected_decision_id)
            else:
                self.query_one("#alternatives-content", Static).update("No ratified decisions found.")
        finally:
            session.close()

    def show_decision_alternatives(self, decision_id: str) -> None:
        content = self.query_one("#alternatives-content", Static)
        
        session = db_manager.get_session(self.workspace)
        try:
            dec = session.query(Decision).filter_by(id=decision_id).first()
            if not dec:
                content.update("No decision details found.")
                return
                
            text = f"[bold cyan]Decision:[/bold cyan] {dec.decision}\n"
            text += f"[bold cyan]Rationale:[/bold cyan] {dec.rationale}\n\n"
            
            alts = session.query(Alternative).filter_by(decision_id=decision_id).all()
            if alts:
                text += "[bold yellow]═══════ Alternatives Evaluated ═══════[/bold yellow]\n\n"
                for a in alts:
                    text += f"[bold green]{a.option}[/bold green]\n"
                    text += f"  [bold cyan]Pros:[/bold cyan] {a.pros}\n"
                    text += f"  [bold red]Cons:[/bold red] {a.cons}\n"
                    text += "────────────────────────────────────────────────\n"
            else:
                text += "[italic #94a3b8]No alternative comparisons documented.[/italic #94a3b8]"
                
            content.update(text)
        finally:
            session.close()

    def load_roadmap(self) -> None:
        table = self.query_one("#roadmap-table", DataTable)
        table.clear()
        
        session = db_manager.get_session(self.workspace)
        try:
            tasks = session.query(RoadmapTask).order_by(RoadmapTask.phase, RoadmapTask.id).all()
            
            done_count = sum(1 for t in tasks if t.status == "DONE")
            total_count = len(tasks)
            pct = int((done_count / total_count * 100)) if total_count > 0 else 0
            
            progress_bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            self.query_one("#roadmap-progress-label", Label).update(
                f"Project Roadmap Progress: {done_count}/{total_count} Completed ({pct}%) | [{progress_bar}]"
            )
            
            for t in tasks:
                status_colored = f"[bold green]{t.status}[/bold green]" if t.status == "DONE" else f"[bold yellow]{t.status}[/bold yellow]"
                table.add_row(str(t.phase), t.id, t.task, status_colored)
        finally:
            session.close()

    def load_audits(self) -> None:
        table = self.query_one("#audits-table", DataTable)
        table.clear()
        
        session = db_manager.get_session(self.workspace)
        try:
            audits = session.query(AuditLog).order_by(AuditLog.timestamp.desc()).all()
            for a in audits:
                score_str = f"{int(a.alignment_score)}%"
                score_colored = f"[green]{score_str}[/green]" if a.alignment_score >= 90 else f"[yellow]{score_str}[/yellow]"
                table.add_row(
                    a.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    a.id,
                    a.auditor_team,
                    score_colored,
                    a.summary
                )
        finally:
            session.close()

    # --- Actions / Handlers ---
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btn-refresh":
            self.refresh_all()
        elif button_id == "btn-new-proposal":
            self.action_new_proposal()
        elif button_id == "btn-deliberate":
            self.action_deliberate()
        elif button_id == "btn-vote":
            self.action_vote()

    def action_refresh(self) -> None:
        self.refresh_all()

    def toggle_buttons(self, enabled: bool) -> None:
        try:
            target = self.screen_stack[0] if self.screen_stack else self.screen
        except Exception:
            return
        for btn_id in ["#btn-new-proposal", "#btn-deliberate", "#btn-vote", "#btn-refresh"]:
            try:
                target.query_one(btn_id, Button).disabled = not enabled
            except Exception:
                pass

    def action_new_proposal(self) -> None:
        self.show_new_proposal_modal()

    def show_new_proposal_modal(self) -> None:
        def on_modal_dismiss(data: dict | None) -> None:
            if data is not None:
                self.notify("Creating proposal in background...", title="Processing")
                self.toggle_buttons(False)
                self.run_worker(self.do_create_proposal(data), exclusive=True)

        self.push_screen(ProposalCreateModal(), on_modal_dismiss)

    async def do_create_proposal(self, data: dict) -> None:
        loop = asyncio.get_running_loop()
        
        # Determine the project ID from the DB if available, otherwise fallback
        session = db_manager.get_session(self.workspace)
        project_id = "council_manager"
        try:
            proj = session.query(Project).first()
            if proj:
                project_id = proj.id
        finally:
            session.close()

        def _run():
            return council_orchestrator.create_proposal(
                workspace_dir=self.workspace,
                project_id=project_id,
                description=data["description"],
                topic=data.get("topic"),
                options=data.get("options")
            )
            
        await loop.run_in_executor(None, _run)

    def action_deliberate(self) -> None:
        if not self.selected_proposal_id:
            self.notify("No proposal selected.", severity="warning")
            return
            
        self.notify(f"Starting Deliberation for {self.selected_proposal_id} in background...", title="Processing")
        self.toggle_buttons(False)
        self.run_worker(self.do_deliberate(self.selected_proposal_id), exclusive=True)

    async def do_deliberate(self, proposal_id: str) -> None:
        def tui_progress(team_id: str, team_name: str, status: str, elapsed: float):
            if status == "COMPLETED":
                self.notify(
                    f"Team {team_id} ({team_name}) completed in {elapsed:.2f}s.",
                    title="Deliberation Progress",
                    severity="information",
                    timeout=5.0
                )
        await council_orchestrator.run_deliberation(self.workspace, proposal_id, on_progress=tui_progress)

    def action_vote(self) -> None:
        if not self.selected_proposal_id:
            self.notify("No proposal selected.", severity="warning")
            return
            
        self.notify(f"Starting Consensus Voting Loop for {self.selected_proposal_id} in background...", title="Processing")
        self.toggle_buttons(False)
        self.run_worker(self.do_vote(self.selected_proposal_id), exclusive=True)

    async def do_vote(self, proposal_id: str) -> None:
        await council_orchestrator.run_voting(self.workspace, proposal_id, max_cycles=5)

    def on_worker_state_changed(self, event: WorkerStateChanged) -> None:
        """Called when a background worker changes its execution state."""
        worker = event.worker
        if event.state == WorkerState.SUCCESS:
            self.notify("Process execution completed successfully!", severity="info", title="Success")
            self.toggle_buttons(True)
            self.refresh_all()
        elif event.state == WorkerState.ERROR:
            self.notify(f"Process failed: {worker.error}", severity="error", title="Error")
            self.toggle_buttons(True)
            self.refresh_all()

                

