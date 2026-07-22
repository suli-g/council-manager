import csv
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict
from council_manager.db import db_manager
from council_manager.db.models import Project, Team, Proposal, Decision, Alternative, AuditLog, AuditDecision, RoadmapTask

def safe_parse_date(date_str: str) -> date:
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except Exception:
        return datetime.now().date()

def safe_parse_nullable_date(date_str: str) -> date | None:
    if not date_str or not date_str.strip():
        return None
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except Exception:
        return None

def safe_parse_datetime(dt_str: str) -> datetime:
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(dt_str.strip(), fmt)
        except Exception:
            continue
    return datetime.now()

def safe_parse_score(score_str: str) -> float:
    try:
        cleaned = score_str.replace("%", "").strip()
        return float(cleaned)
    except Exception:
        return 100.0

def import_csv_to_db(workspace_dir: str | Path, project_id: str):
    """Import all CSV governance logs from .agents/ into the SQLite database."""
    workspace_path = Path(workspace_dir).resolve()
    agents_dir = workspace_path / ".agents"
    
    if not agents_dir.exists():
        raise FileNotFoundError(f"No .agents/ directory found in {workspace_path}")

    session = db_manager.get_session(workspace_path)
    try:
        # 1. Ensure Project exists
        project = session.query(Project).filter_by(id=project_id).first()
        if not project:
            project = Project(id=project_id, name=project_id.replace("_", " ").title())
            session.add(project)
            session.commit()

        # 2. Import Teams
        teams_csv = agents_dir / "teams.csv"
        if teams_csv.exists():
            with open(teams_csv, mode="r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    team_id = row["team_id"].strip()
                    team = session.query(Team).filter_by(id=team_id).first()
                    if not team:
                        team = Team(
                            id=team_id,
                            name=row["team_name"].strip(),
                            vote_weight=int(row["count"].strip()),
                            paradigm_specialty=row["paradigm_specialty"].strip(),
                        )
                        session.add(team)
            session.commit()

        # 3. Import Decisions
        decisions_csv = agents_dir / "decisions.csv"
        decisions_list = []
        if decisions_csv.exists():
            with open(decisions_csv, mode="r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    dec_id = row["id"].strip()
                    decisions_list.append(dec_id)
                    decision = session.query(Decision).filter_by(id=dec_id).first()
                    if not decision:
                        decision = Decision(
                            id=dec_id,
                            project_id=project_id,
                            date=safe_parse_date(row["date"]),
                            topic=row["topic"].strip(),
                            decision=row["decision"].strip(),
                            rationale=row["rationale"].strip(),
                        )
                        session.add(decision)
            session.commit()

        # 4. Import Alternatives
        alts_csv = agents_dir / "alternatives.csv"
        if alts_csv.exists():
            with open(alts_csv, mode="r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    alt_id = row["id"].strip()
                    alternative = session.query(Alternative).filter_by(id=alt_id).first()
                    if not alternative:
                        alternative = Alternative(
                            id=alt_id,
                            decision_id=row["decision_id"].strip(),
                            option=row["option"].strip(),
                            pros=row["pros"].strip(),
                            cons=row["cons"].strip(),
                        )
                        session.add(alternative)
            session.commit()

        # 5. Import Audits
        audits_csv = agents_dir / "audits.csv"
        if audits_csv.exists():
            session.query(AuditLog).filter_by(project_id=project_id).delete()
            with open(audits_csv, mode="r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    audit_id = row["audit_id"].strip()
                    audit = AuditLog(
                        id=audit_id,
                        project_id=project_id,
                        timestamp=safe_parse_datetime(row["timestamp"]),
                        summary=row["summary"].strip(),
                        alignment_score=safe_parse_score(row["alignment_score"]),
                        auditor_team=row["auditor_team"].strip(),
                    )
                    session.add(audit)
            session.commit()

        # 5b. Import Audit Decisions
        audit_decs_csv = agents_dir / "audit_decisions.csv"
        if audit_decs_csv.exists():
            session.query(AuditDecision).filter_by(project_id=project_id).delete()
            with open(audit_decs_csv, mode="r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    audit_id = row["audit_id"].strip()
                    dec_id = row["decision_id"].strip()
                    audit_dec = AuditDecision(
                        audit_id=audit_id,
                        decision_id=dec_id,
                        project_id=project_id,
                        status=row["status"].strip(),
                        re_audit_date=safe_parse_nullable_date(row["re_audit_date"]),
                        notes=row["notes"].strip() if "notes" in row else None
                    )
                    session.add(audit_dec)
            session.commit()


        # 6. Parse and Build Proposals & Votes from individual votes CSVs
        for dec_id in decisions_list:
            votes_csv = agents_dir / "votes" / f"{dec_id}.csv"
            if votes_csv.exists():
                options_set = set()
                # Find options from alternatives
                alts = session.query(Alternative).filter_by(decision_id=dec_id).all()
                for a in alts:
                    options_set.add(a.option)
                
                # Add the ratified choice
                dec = session.query(Decision).filter_by(id=dec_id).first()
                if dec:
                    options_set.add(dec.decision)

                rationales = []
                votes = []
                
                with open(votes_csv, mode="r", encoding="utf-8", newline="") as f:
                    reader = csv.DictReader(f, delimiter=";")
                    for row in reader:
                        team_id = row.get("team_id", "").strip()
                        voter_id = row.get("voter_id", "").strip()
                        if not voter_id:
                            voter_id = f"V-{team_id}"
                        vote = row.get("vote", "").strip()
                        rationale = row.get("rationale", "").strip()

                        options_set.add(vote)
                        votes.append({
                            "voter_id": voter_id,
                            "team_id": team_id,
                            "vote": vote,
                            "timestamp": datetime.now().isoformat()
                        })
                        if rationale:
                            rationales.append({
                                "team_id": team_id,
                                "rationale": rationale,
                                "timestamp": datetime.now().isoformat()
                            })


                proposal = session.query(Proposal).filter_by(id=dec_id).first()
                if not proposal:
                    proposal = Proposal(
                        id=dec_id,
                        project_id=project_id,
                        topic=dec.topic if dec else "Imported Topic",
                        description=dec.decision if dec else "Imported Description",
                        options=list(options_set),
                        status="RATIFIED",
                        rationales=rationales,
                        votes=votes
                    )
                    session.add(proposal)
        session.commit()


        # 7. Parse and Build Roadmap Tasks
        roadmap_csv = agents_dir / "roadmap.csv"
        if roadmap_csv.exists():
            session.query(RoadmapTask).filter_by(project_id=project_id).delete()
            with open(roadmap_csv, mode="r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    task_id = row.get("id", "").strip()
                    if not task_id:
                        continue
                    phase_val = int(row.get("phase", "1").strip())
                    task_name = row.get("task", "").strip()
                    status_val = row.get("status", "TODO").strip()
                    notes_val = row.get("notes", "").strip()

                    roadmap_task = RoadmapTask(
                        id=task_id,
                        project_id=project_id,
                        phase=phase_val,
                        task=task_name,
                        status=status_val,
                        notes=notes_val
                    )
                    session.add(roadmap_task)
            session.commit()


    finally:
        session.close()


def export_db_to_csv(workspace_dir: str | Path, project_id: str):
    """Export SQLite tables back to flat CSV files in .agents/ workspace."""
    workspace_path = Path(workspace_dir).resolve()
    agents_dir = workspace_path / ".agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    votes_dir = agents_dir / "votes"
    votes_dir.mkdir(parents=True, exist_ok=True)

    session = db_manager.get_session(workspace_path)
    try:
        # 1. Export Teams
        teams = session.query(Team).all()
        teams_csv = agents_dir / "teams.csv"
        with open(teams_csv, mode="w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["team_id", "team_name", "count", "paradigm_specialty"])
            for t in teams:
                writer.writerow([t.id, t.name, t.vote_weight, t.paradigm_specialty])

        # 2. Export Decisions
        decisions = session.query(Decision).filter_by(project_id=project_id).all()
        decisions_csv = agents_dir / "decisions.csv"
        with open(decisions_csv, mode="w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["id", "date", "topic", "decision", "rationale"])
            for d in decisions:
                writer.writerow([d.id, d.date.strftime("%Y-%m-%d"), d.topic, d.decision, d.rationale])

        # 3. Export Alternatives
        alts_csv = agents_dir / "alternatives.csv"
        with open(alts_csv, mode="w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["id", "decision_id", "option", "pros", "cons"])
            for d in decisions:
                for alt in d.alternatives:
                    writer.writerow([alt.id, alt.decision_id, alt.option, alt.pros, alt.cons])

        # 4. Export Audits
        audits = session.query(AuditLog).filter_by(project_id=project_id).all()
        audits_csv = agents_dir / "audits.csv"
        with open(audits_csv, mode="w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["timestamp", "audit_id", "summary", "alignment_score", "auditor_team"])
            for a in audits:
                writer.writerow([
                    a.timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
                    a.id,
                    a.summary,
                    f"{int(a.alignment_score)}%",
                    a.auditor_team
                ])

        # 4b. Export Audit Decisions
        audit_decs = session.query(AuditDecision).filter_by(project_id=project_id).order_by(AuditDecision.audit_id, AuditDecision.decision_id).all()
        if audit_decs:
            audit_decs_csv = agents_dir / "audit_decisions.csv"
            with open(audit_decs_csv, mode="w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(["audit_id", "decision_id", "status", "re_audit_date", "notes"])
                for ad in audit_decs:
                    re_audit_date_str = ad.re_audit_date.strftime("%Y-%m-%d") if ad.re_audit_date else ""
                    writer.writerow([
                        ad.audit_id,
                        ad.decision_id,
                        ad.status,
                        re_audit_date_str,
                        ad.notes or ""
                    ])

        # 5. Export Votes and Manifest
        proposals = session.query(Proposal).filter_by(project_id=project_id).all()
        manifest_csv = agents_dir / "votes_manifest.csv"
        
        manifest_entries = []
        for p in proposals:
            if not p.votes:
                continue
            
            # Write individual vote file
            vote_file = votes_dir / f"{p.id}.csv"
            with open(vote_file, mode="w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(["voter_id", "team_id", "vote"])
                
                for v in p.votes:
                    voter_id = v.get("voter_id", f"V-{v.get('team_id')}")
                    team_id = v.get("team_id", "")
                    vote_val = v.get("vote", "")
                    writer.writerow([voter_id, team_id, vote_val])
            
            # Format timestamp for manifest
            manifest_ts = p.created_at.strftime("%Y-%m-%dT%H:%M:%S")
            manifest_entries.append([p.id, p.topic, f"docs/.agents/votes/{p.id}.csv", manifest_ts])

        # Write manifest
        with open(manifest_csv, mode="w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["decision_id", "topic", "file_path", "timestamp"])
            for entry in sorted(manifest_entries, key=lambda x: x[0]):
                writer.writerow(entry)

        # 6. Export Roadmap Tasks
        roadmap_tasks = session.query(RoadmapTask).filter_by(project_id=project_id).order_by(RoadmapTask.phase, RoadmapTask.id).all()
        if roadmap_tasks:
            roadmap_csv = agents_dir / "roadmap.csv"
            with open(roadmap_csv, mode="w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(["phase", "id", "task", "status", "notes"])
                for task in roadmap_tasks:
                    writer.writerow([task.phase, task.id, task.task, task.status, task.notes or ""])

    finally:
        session.close()


DEFAULT_AGENTS_MD = """# Project Governance & Workflow

This file provides the meta-framework for how AI agents and LLMs must operate within this repository. It prioritizes dynamic configuration over hard-coded rules to ensure the project can scale its governance and team structure.

## Dynamic Source-of-Truth (CLI Encapsulation — CRITICAL)

**IMPORTANT: You MUST NOT manually navigate, list, or read files inside `.agents/` directly** (e.g., do not use `ListDir`, `Read`, or similar tools on `roadmap.csv`, `teams.csv`, `decisions.csv`, `alternatives.csv`, or the `votes/` folder). All governance data is managed through a SQLite database and must be accessed exclusively via the official `council-manager` CLI commands:

*   **To check the roadmap:** `uv run council-manager show-roadmap`
*   **To check registered teams:** `uv run council-manager show-teams`
*   **To check ratified decisions:** `uv run council-manager show-decisions`
*   **To check audit logs:** `uv run council-manager show-audits`
*   **To create a proposal:** `uv run council-manager proposal-create "..." -w <workspace>`
*   **To run deliberation:** `uv run council-manager deliberate -w <workspace>`
*   **To run voting:** `uv run council-manager vote -w <workspace>`
*   **To update roadmap tasks:** `uv run council-manager roadmap-update -w <workspace>` (add/update versioned tasks)
*   **To gather token-optimized context:** `uv run council-manager get-context -w <workspace>` (get compacted workspace context)
*   **To request an external audit:** `uv run council-manager audit-request -w <workspace>` (creates audit_request.md)
*   **To import external audit findings:** `uv run council-manager audit-report-import -w <workspace>` (imports audit_report.md)

Direct file reads bypass the SQLite database cache and ORM schema boundaries, leading to stale or out-of-sync state.

**Format Standard:** All CSV files in this repository use semi-colons (`;`) as delimiters.

## Multi-Team, Multi-Tier Governance
The project operates under a decentralized, paradigm-weighted governance model.

1.  **Perspective Gathering:** Before any significant change, identify which teams are affected. Use `uv run council-manager show-teams` to see the current team roster.
2.  **Tiered Evaluation:** 
    *   Any request starting with **PROPOSAL:** triggers a formal **interactive** vote.
    *   Every proposal must include at least **two alternatives** (including the Contrarian view).
    *   **Human Oversight:** Votes must NEVER be simulated or handled autonomously by an agent. The agent must present the alternatives and team perspectives to the human user for explicit validation and selection. Human overseer decisions should only be documented in the vote record if they contradict all team-proposed options.
    *   Any request starting with **QUERY:** triggers a lightweight, non-voting team deliberation flow. The agent will concurrently query all active teams for their immediate rationales and perspectives on how the queried item affects the project, presenting them to the user. This does not involve any voting or formal ratification, and query results are not written to the static decisions or alternatives CSV files to prevent documentation rot.
3.  **Conflict Resolution:** If paradigms disagree, the decision is resolved through the multi-team voting system. The **Contrarians (Team G)** provide critical friction to prevent groupthink.

## Mandatory AI Workflow
Any AI agent (including yourself) must follow these procedural mandates:

### 0. Mandatory Deliberation
*   **The PROPOSAL: Halt:** When a message starts with **PROPOSAL:**, you MUST NOT execute any state-changing tools (e.g., `write_file`, `replace`, `run_shell_command`) until a formal interactive vote has been conducted and documented in `votes_manifest.csv`.
*   **Interactive Decision Making:** You must use the `ask_question` tool to present paradigm perspectives to the user. You are forbidden from simulating the final outcome of a vote without real-time human interaction.
*   **Tool Delegation (Critical):** Do NOT simulate deliberations or voting outcomes yourself. You MUST run all deliberations and votes via `uv run council-manager deliberate` and `uv run council-manager vote`.

### 1. Research & Alignment
*   Run `uv run council-manager get-context` (or individual queries like `show-decisions` and `show-roadmap`) to check project state and existing constraints. Use `get-context` to retrieve token-optimized context blocks instead of loading raw tables.
*   Do NOT read `decisions.csv`, `roadmap.csv`, or any other `.agents/` file directly.

### 2. Execution & Documentation
*   **Ratification:** After a strategy is agreed upon, update `decisions.csv` and `alternatives.csv` to reflect the new state (these CSVs are the append-only log; the SQLite DB is the canonical live state).
*   **Roadmap Maintenance:** Use `uv run council-manager roadmap-update` to add or update versioned roadmap tasks. Do NOT edit `roadmap.csv` directly \u2014 the command syncs both SQLite and CSV automatically.
*   **Scalability:** Do not hard-code team counts, tier counts, or specific paradigm names. Use `uv run council-manager show-teams` to read team structure dynamically.

### 3. Sub-Agent/Teammate Integration
*   When spawning sub-agents or collaborating with other LLMs, ensure they are first directed to this file and the workspace skill at `.agents/skills/council-manager/SKILL.md`.
*   Sub-agents must read both this file AND the skill before taking any action.

## Protocol Breach & Alignment
If an agent (AI or human) deviates from these principles (e.g., by reading CSV files directly or executing changes without a vote):
1.  **Immediate Halt:** Stop all current execution.
2.  **Audit & Rollback:** Analyze the deviation and revert any unsanctioned changes if necessary.
3.  **Formal Re-Alignment:** Re-document the current state and return to the proper deliberation phase for the original proposal.
"""

DEFAULT_SKILL_MD = """---
name: council-manager
description: Follows the multi-team, multi-tier governance model for this project. Use when the user submits a PROPOSAL: or QUERY: or when performing any development work in this workspace.
---

# Council Manager Governance Skill

You are operating in a workspace governed by the `council_manager` system. You must strictly adhere to the following rules:

## 1. Dynamic Source-of-Truth (Strict Encapsulation)
The data structures for governance are stored inside the `.agents/` folder.
*CRITICAL WORKFLOW RULE*: You are FORBIDDEN from manually listing `.agents/` directory contents (e.g., via `ListDir`), and you MUST NOT manually read/parse the CSV files directly (such as `roadmap.csv` or `teams.csv`) to answer questions about the roadmap, registered teams, or current status.
Instead, you MUST run the official CLI tools:
*   To check the roadmap status: Run `uv run council-manager show-roadmap` (or `council-manager show-roadmap`).
*   To check registered teams: Run `uv run council-manager show-teams` (or `council-manager show-teams`).
*   To submit/incept proposals: Run `uv run council-manager create-proposal` (or `council-manager create-proposal`).
Manual file navigation bypasses SQLite database cache synchronization and ORM schema boundaries, leading to out-of-sync states.
All CSV files in this repository use semi-colons (`;`) as delimiters.

## 2. Multi-Team, Multi-Tier Governance
The project operates under a decentralized, paradigm-weighted governance model.
1.  **Perspective Gathering:** Before any significant change, identify which teams in `teams.csv` are affected by or have expertise in the domain.
2.  **Tiered Evaluation:** 
    *   Any request starting with **PROPOSAL:** triggers a formal **interactive** vote.
    *   Every proposal must include at least **two alternatives** (including the Contrarian view).
    *   **Human Oversight:** Votes must NEVER be simulated or handled autonomously by an agent. The agent must present the alternatives and team perspectives to the human user for explicit validation and selection. Human overseer decisions should only be documented in the vote record if they contradict all team-proposed options.
    *   Any request starting with **QUERY:** triggers a lightweight, non-voting team deliberation flow. The agent will concurrently query all active teams for their immediate rationales and perspectives on how the queried item affects the project, presenting them to the user. This does not involve any voting or formal ratification, and query results are not written to the static decisions or alternatives CSV files to prevent documentation rot.
3.  **Conflict Resolution:** If paradigms disagree, the decision is resolved through the multi-team voting system defined by the current weights in `teams.csv`. The **Contrarians (Team G)** provide critical friction to prevent groupthink.

## 3. Mandatory AI Workflow
Any AI agent (including yourself) must follow these procedural mandates:

### 0. Mandatory Deliberation
*   **The PROPOSAL: Halt:** When a message starts with **PROPOSAL:**, you MUST NOT execute any state-changing tools (e.g., `write_to_file`, `replace_file_content`, `run_command`) until a formal interactive vote has been conducted and documented in `votes_manifest.csv`.
*   **Interactive Decision Making:** You must use the `ask_question` tool to present paradigm perspectives to the user. You are forbidden from simulating the final outcome of a vote without real-time human interaction.
*   **Tool Delegation (Critical):** Do NOT simulate deliberations or voting outcomes yourself within your model context. You MUST run all deliberations and votes by executing the official CLI commands `uv run council-manager deliberate` and `uv run council-manager vote`. This ensures the deliberations use the correct council-specific LLM configuration (such as Ollama or local settings) defined for the project, even if you are running on a different model (like Gemini).

### 1. Research & Alignment
*   Search `decisions.csv` for any existing rulings that constrain your task.
*   Consult `alternatives.csv` to avoid re-proposing previously rejected strategies.
*   Review `roadmap.csv` to ensure your work aligns with the current phase's priorities.

### 2. Execution & Documentation
*   **Ratification:** After a strategy is agreed upon, you must update `decisions.csv` and `alternatives.csv` to reflect the new state.
*   **Roadmap Maintenance:** Update the status of tasks in `roadmap.csv` (and `README.md` if applicable) as you progress.
*   **Scalability:** Do not hard-code team counts, tier counts, or specific paradigm names into the codebase or memory files. Reference `teams.csv` dynamically.

### 3. Sub-Agent/Teammate Integration
*   When spawning sub-agents or collaborating with other LLMs, ensure they are first directed to this file.
*   The `.agents/` directory is the "nervous system" of the project; any teammate must be able to autonomously read its state to orient themselves without human intervention.

## 4. Protocol Breach & Alignment
If an agent (AI or human) deviates from these principles (e.g., by executing changes without a vote):
1.  **Immediate Halt:** Stop all current execution.
2.  **Audit & Rollback:** Analyze the deviation and revert any unsanctioned changes if necessary.
3.  **Formal Re-Alignment:** Re-document the current state and return to the proper deliberation phase for the original proposal.
"""


def initialize_new_project(
    workspace_dir: str | Path,
    project_id: str,
    project_name: str | None = None,
    global_member_count: int = 10,
    project_description: str | None = None,
    custom_teams: List[Dict[str, str]] | None = None
):
    """Initialize a new project directory with default settings, empty templates, and custom team counts."""
    workspace_path = Path(workspace_dir).resolve()
    agents_dir = workspace_path / ".agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    
    votes_dir = agents_dir / "votes"
    votes_dir.mkdir(parents=True, exist_ok=True)
    
    # Write default or custom teams.csv with custom global member count
    teams_csv = agents_dir / "teams.csv"
    if not teams_csv.exists():
        with open(teams_csv, "w", encoding="utf-8", newline="") as f:
            f.write("team_id;team_name;count;paradigm_specialty\n")
            if custom_teams:
                for t in custom_teams:
                    spec = t.get("specialty") or t.get("paradigm_specialty") or ""
                    f.write(f"{t['id']};{t['name']};{global_member_count};{spec}\n")
            else:
                f.write(f"A;Functional Specialists;{global_member_count};Functional Programming (Immutability, Pure Functions, Pipelines)\n")
                f.write(f"B;OOP Specialists;{global_member_count};Object-Oriented Programming (Encapsulation, Polymorphism, Design Patterns)\n")
                f.write(f"C;Imperative Specialists;{global_member_count};Imperative Programming (Explicit State, Procedural logic, Performance)\n")
                f.write(f"D;Declarative Specialists;{global_member_count};Declarative Programming (Logic engines, Config-driven, DSLs)\n")
                f.write(f"E;Dynamic Specialists;{global_member_count};Dynamic Programming (Reflection, Metaprogramming, Rapid Prototyping)\n")
                f.write(f"F;Auditors/Project Managers;{global_member_count};Project Oversight (Requirement Tracking, Quality Assurance, Strategic Alignment)\n")
                f.write(f"G;Contrarians;{global_member_count};Devil's Advocacy (Beginner/Senior Tech Mix, Design Focus, Non-Tech Perspectives)\n")

    # Write other template CSVs if they do not exist
    templates = {
        "decisions.csv": "id;date;topic;decision;rationale\n",
        "alternatives.csv": "id;decision_id;option;pros;cons\n",
        "audits.csv": "timestamp;audit_id;summary;alignment_score;auditor_team\n",
        "votes_manifest.csv": "decision_id;topic;file_path;timestamp\n",
        "roadmap.csv": "phase;id;task;status;notes\n"
    }
    for filename, headers in templates.items():
        filepath = agents_dir / filename
        if not filepath.exists():
            with open(filepath, "w", encoding="utf-8", newline="") as f:
                f.write(headers)

    # If project_description is provided, record it as DEC-001 (Immediate Onboarding Ratification)
    if project_description:
        decisions_csv = agents_dir / "decisions.csv"
        has_dec_001 = False
        if decisions_csv.exists():
            with open(decisions_csv, "r", encoding="utf-8") as f:
                content = f.read()
                if "DEC-001" in content:
                    has_dec_001 = True
        
        if not has_dec_001:
            today_str = date.today().strftime("%Y-%m-%d")
            clean_desc = project_description.replace("\n", " ").replace(";", " ")
            with open(decisions_csv, "a", encoding="utf-8", newline="") as f:
                f.write(f"DEC-001;{today_str};Project Onboarding;Onboard Project {project_name or project_id};{clean_desc}\n")
            
            # Write corresponding vote manifest and vote file
            votes_manifest = agents_dir / "votes_manifest.csv"
            with open(votes_manifest, "a", encoding="utf-8", newline="") as f:
                f.write(f"DEC-001;Project Onboarding;docs/.agents/votes/DEC-001.csv;{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}\n")
            
            dec_001_vote = votes_dir / "DEC-001.csv"
            with open(dec_001_vote, "w", encoding="utf-8", newline="") as f:
                f.write("voter_id;team_id;vote\n")
                f.write("V-008;User;Onboard Project\n")

    # Write default AGENTS.md in the workspace root
    agents_md = workspace_path / "AGENTS.md"
    if not agents_md.exists():
        with open(agents_md, "w", encoding="utf-8", newline="") as f:
            f.write(DEFAULT_AGENTS_MD)

    # Write Workspace Skill in .agents/skills/council-manager/SKILL.md
    skills_dir = agents_dir / "skills"
    skill_dir = skills_dir / "council-manager"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        with open(skill_md, "w", encoding="utf-8", newline="") as f:
            f.write(DEFAULT_SKILL_MD)

    # Write Project Council Persona Skill in .agents/skills/project-council/SKILL.md
    project_council_dir = skills_dir.parent / "skills" / "project-council"
    project_council_dir.mkdir(parents=True, exist_ok=True)
    project_council_md = project_council_dir / "SKILL.md"
    
    # Read the teams from teams.csv to make sure they are accurate
    teams_list = []
    if teams_csv.exists():
        with open(teams_csv, "r", encoding="utf-8") as f:
            lines = f.readlines()
            for line in lines[1:]:
                parts = line.strip().split(";")
                if len(parts) >= 4:
                    teams_list.append(f"- **Team {parts[0]} ({parts[1]})**: {parts[3]}")
    if not teams_list:
        teams_list = [
            "- **Team A (Functional Specialists)**: Functional Programming (Immutability, Pure Functions, Pipelines)",
            "- **Team B (OOP Specialists)**: Object-Oriented Programming (Encapsulation, Polymorphism, Design Patterns)",
            "- **Team C (Imperative Specialists)**: Imperative Programming (Explicit State, Procedural logic, Performance)",
            "- **Team D (Declarative Specialists)**: Declarative Programming (Logic engines, Config-driven, DSLs)",
            "- **Team E (Dynamic Specialists)**: Dynamic Programming (Reflection, Metaprogramming, Rapid Prototyping)",
            "- **Team F (Auditors/Project Managers)**: Project Oversight (Requirement Tracking, Quality Assurance, Strategic Alignment)",
            "- **Team G (Contrarians)**: Devil's Advocacy (Beginner/Senior Tech Mix, Design Focus, Non-Tech Perspectives)"
        ]
    team_details_str = "\n".join(teams_list)
    
    project_council_content = f"""---
name: project-council
description: "Defines the project-specific council personas and specialties for deliberations and voting."
---

# Project Council Persona Skill

This workspace is governed by a project-specific council. When you are asked to run deliberations or voting, or when you interact with this project, you must adopt these specific team personas.

## Council Teams and Specialties

Here are the active teams for this project:
{team_details_str}

## Instructions for Collaborating Agents

1. **Official Tool Delegation (Critical)**:
   * Do NOT write or simulate deliberations or voting results yourself within your model context. You MUST delegate all deliberations and voting loops to the `council-manager` CLI tools (e.g., `uv run council-manager deliberate` and `uv run council-manager vote`). This ensures they are processed through the official SQLite backend and using the project's configured council LLM provider (e.g., Ollama, local endpoints), even if you are operating on a different model (e.g. Gemini).
   * Do NOT manually navigate, list, or read files inside `.agents/` (such as `roadmap.csv`, `teams.csv`, `decisions.csv`, or the `votes/` folder) to inspect the roadmap or status. You MUST execute the official CLI commands (e.g., `uv run council-manager show-roadmap` or `uv run council-manager show-teams`). Direct file reads bypass the database constraints and cache synchronization layer.
2. **Deliberations**: When the official `council-manager` tool runs deliberations, the system will prompt the underlying LLM to adopt the specialties listed above.
3. **Voting**: When the official `council-manager` tool runs voting, each team will evaluate proposals from the lens of their specific paradigm and domain.
4. **Impersonation**: Respect the distinct perspectives of each team. Do not merge their identities or dilute their specialties.
"""
    with open(project_council_md, "w", encoding="utf-8", newline="") as f:
        f.write(project_council_content)

    # Write/Update skills.json
    skills_json = agents_dir / "skills.json"
    import json
    council_manager_path = str(skill_dir.as_posix())
    project_council_path = str(project_council_dir.as_posix())
    config_data = {
        "entries": [
            { "path": council_manager_path },
            { "path": project_council_path }
        ]
    }
    with open(skills_json, "w", encoding="utf-8", newline="") as f:
        json.dump(config_data, f, indent=2)

    # Run the import to seed the SQLite database file
    import_csv_to_db(workspace_path, project_id)


