import argparse
import asyncio
import os
import sys
from pathlib import Path
from council_manager.config import settings
from council_manager.db import db_manager, Proposal, Team, Decision, AuditLog, RoadmapTask, BackgroundTask, initialize_new_project, import_csv_to_db, export_db_to_csv
from council_manager.core.orchestrator import council_orchestrator
from council_manager.core.prompter import format_rationale, AgentPrompter

COUNCIL_TEMPLATES = {
    "software": [
        {"id": "A", "name": "Functional Specialists", "specialty": "Functional Programming (Immutability, Pure Functions, Pipelines)"},
        {"id": "B", "name": "OOP Specialists", "specialty": "Object-Oriented Programming (Encapsulation, Polymorphism, Design Patterns)"},
        {"id": "C", "name": "Imperative Specialists", "specialty": "Imperative Programming (Explicit State, Procedural logic, Performance)"},
        {"id": "D", "name": "Declarative Specialists", "specialty": "Declarative Programming (Logic engines, Config-driven, DSLs)"},
        {"id": "E", "name": "Dynamic Specialists", "specialty": "Dynamic Programming (Reflection, Metaprogramming, Rapid Prototyping)"},
        {"id": "F", "name": "Auditors/Project Managers", "specialty": "Project Oversight (Requirement Tracking, Quality Assurance, Strategic Alignment)"},
        {"id": "G", "name": "Contrarians", "specialty": "Devil's Advocacy (Beginner/Senior Tech Mix, Design Focus, Non-Tech Perspectives)"}
    ],
    "education": [
        {"id": "A", "name": "Pedagogy Specialists", "specialty": "Learning theories, student needs, educational psychology"},
        {"id": "B", "name": "Curriculum Setters", "specialty": "Subject matter experts, syllabus design, sequencing of topics"},
        {"id": "C", "name": "Assessment Designers", "specialty": "Testing, grading rubrics, evaluations, feedback loops"},
        {"id": "D", "name": "Instructional Technology Specialists", "specialty": "E-learning, digital tools, educational software integration"},
        {"id": "E", "name": "Student Experience Designers", "specialty": "Engagement, accessibility, student feedback, inclusion"},
        {"id": "F", "name": "Program Administrators", "specialty": "Resource allocation, scheduling, compliance, quality assurance"},
        {"id": "G", "name": "Contrarians", "specialty": "Devil's Advocacy (Student/Parent Mix, Design Focus, Alternative Perspectives)"}
    ],
    "marketing": [
        {"id": "A", "name": "Brand Strategists", "specialty": "Brand identity, positioning, market research, brand guidelines"},
        {"id": "B", "name": "Copywriters & Content Creators", "specialty": "Messaging, creative writing, storytelling, copy editing"},
        {"id": "C", "name": "Media Buyers & Analysts", "specialty": "Ad spend, ROI, channel selection, analytics, performance tracking"},
        {"id": "D", "name": "SEO & Growth Engineers", "specialty": "Conversion rate, traffic, search optimization, technical marketing"},
        {"id": "E", "name": "Public Relations Specialists", "specialty": "Press, community engagement, influencer relations, outreach"},
        {"id": "F", "name": "Campaign Managers", "specialty": "Timelines, budget tracking, execution, quality control"},
        {"id": "G", "name": "Contrarians", "specialty": "Devil's Advocacy (Target Audience representatives, consumer feedback, non-traditional ideas)"}
    ],
    "general": [
        {"id": "A", "name": "Strategy & Finance", "specialty": "Planning, budgeting, ROI, resource allocation, financial modeling"},
        {"id": "B", "name": "Operations & Execution", "specialty": "Process efficiency, delivery, supply chain, execution"},
        {"id": "C", "name": "Customer Experience", "specialty": "User feedback, support, retention, customer success"},
        {"id": "D", "name": "Compliance & Legal", "specialty": "Regulatory compliance, risk management, contracts, legal oversight"},
        {"id": "E", "name": "Human Resources & Talent", "specialty": "Team culture, staffing, training, organizational development"},
        {"id": "F", "name": "Operations Managers", "specialty": "Project oversight, requirement tracking, quality assurance, strategic alignment"},
        {"id": "G", "name": "Contrarians", "specialty": "Devil's Advocacy (External disruptors, alternative business models, risk-taking perspectives)"}
    ]
}

# ANSI escape codes for terminal aesthetics
COLOR_GREEN = "\033[92m"
COLOR_CYAN = "\033[96m"
COLOR_YELLOW = "\033[93m"
COLOR_RED = "\033[91m"
COLOR_BOLD = "\033[1m"
COLOR_RESET = "\033[0m"

def log_success(msg: str):
    try:
        print(f"{COLOR_GREEN}{COLOR_BOLD}✔ SUCCESS:{COLOR_RESET} {msg}")
    except UnicodeEncodeError:
        print(f"{COLOR_GREEN}{COLOR_BOLD}[SUCCESS]{COLOR_RESET} {msg}")

def log_info(msg: str):
    try:
        print(f"{COLOR_CYAN}{COLOR_BOLD}ℹ INFO:{COLOR_RESET} {msg}")
    except UnicodeEncodeError:
        print(f"{COLOR_CYAN}{COLOR_BOLD}[INFO]{COLOR_RESET} {msg}")

def log_warn(msg: str):
    try:
        print(f"{COLOR_YELLOW}{COLOR_BOLD}⚠ WARNING:{COLOR_RESET} {msg}")
    except UnicodeEncodeError:
        print(f"{COLOR_YELLOW}{COLOR_BOLD}[WARNING]{COLOR_RESET} {msg}")

def log_error(msg: str):
    try:
        print(f"{COLOR_RED}{COLOR_BOLD}✘ ERROR:{COLOR_RESET} {msg}", file=sys.stderr)
    except UnicodeEncodeError:
        print(f"{COLOR_RED}{COLOR_BOLD}[ERROR]{COLOR_RESET} {msg}", file=sys.stderr)

def verify_workspace_onboarded(workspace: Path) -> None:
    # Skip verification during unit/integration tests to support mock environments
    if "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"):
        return
    agents_dir = workspace / ".agents"
    teams_csv = agents_dir / "teams.csv"
    if not agents_dir.exists() or not teams_csv.exists():
        log_error(
            f"The directory at '{workspace}' has not been onboarded as a Council Manager workspace yet.\n"
            f"Please run the onboarding wizard to initialize it:\n\n"
            f"  uv run council-manager init-project --path \"{workspace}\"\n"
        )
        sys.exit(1)

def get_workspace_path(path_arg: str | None, verify: bool = True) -> Path:
    if path_arg:
        p = Path(path_arg).resolve()
    else:
        p = Path(os.getcwd()).resolve()
    if verify:
        verify_workspace_onboarded(p)
    return p

def get_proposal_id(args, workspace: Path) -> str:
    if getattr(args, "proposal_id", None):
        return args.proposal_id
    
    # Otherwise, query the latest proposal ID
    session = db_manager.get_session(workspace)
    try:
        latest = session.query(Proposal).order_by(Proposal.created_at.desc()).first()
        if not latest:
            log_error("No proposals found in database. Please specify --proposal-id or create one first.")
            sys.exit(1)
        log_info(f"No --proposal-id specified. Defaulting to the latest proposal: '{latest.id}'")
        return latest.id
    except Exception as e:
        log_error(f"Failed to query latest proposal: {e}")
        sys.exit(1)
    finally:
        session.close()
        db_manager.close_all()

def generate_task_id(session, project_id: str) -> str:
    count = session.query(BackgroundTask).filter_by(project_id=project_id).count()
    while True:
        task_id = f"TASK-{count + 1:03d}"
        if not session.query(BackgroundTask).filter_by(id=task_id).first():
            return task_id
        count += 1

def spawn_background_task(workspace_path: Path, task_id: str, max_cycles: int | None = None):
    import subprocess
    import sys
    log_dir = workspace_path / ".agents" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{task_id}.log"
    
    cmd = [
        sys.executable,
        "-m", "council_manager.cli",
        "run-task-worker",
        task_id,
        "--workspace", str(workspace_path)
    ]
    if max_cycles is not None:
        cmd.extend(["--max-cycles", str(max_cycles)])
        
    log_out = open(log_file, "w", encoding="utf-8")
    
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x00000008 | 0x08000000
    else:
        kwargs["start_new_session"] = True
        
    subprocess.Popen(
        cmd,
        stdout=log_out,
        stderr=log_out,
        close_fds=True,
        **kwargs
    )
    log_out.close()

def cmd_init_project(args):
    path_str = args.path or os.getcwd()
    target_path = Path(path_str).resolve()
    
    # Check if project is already initialized
    agents_dir = target_path / ".agents"
    teams_csv = agents_dir / "teams.csv"
    project_exists = agents_dir.exists() and teams_csv.exists()
    
    if project_exists:
        if not getattr(args, "fix_missing", False):
            log_error(
                f"Project in '{target_path}' is already initialized.\n"
                f"To restore or fix missing default files (like AGENTS.md or SKILL.md) without re-onboarding, run:\n\n"
                f"  uv run council-manager init-project --path \"{target_path}\" --fix-missing\n"
            )
            sys.exit(1)
        
        # Implement the --fix-missing logic
        log_info(f"Fixing missing default files in already initialized project at: {target_path}")
        
        from council_manager.db.migration import DEFAULT_AGENTS_MD, DEFAULT_SKILL_MD
        
        fixed_any = False
        
        # Fix AGENTS.md
        agents_md = target_path / "AGENTS.md"
        if not agents_md.exists():
            try:
                with open(agents_md, "w", encoding="utf-8", newline="") as f:
                    f.write(DEFAULT_AGENTS_MD)
                log_success("Created missing AGENTS.md file in project root.")
                fixed_any = True
            except Exception as e:
                log_error(f"Failed to create AGENTS.md: {e}")
                sys.exit(1)
        
        # Fix SKILL.md
        skill_dir = agents_dir / "skills" / "council-manager"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            try:
                with open(skill_md, "w", encoding="utf-8", newline="") as f:
                    f.write(DEFAULT_SKILL_MD)
                log_success("Created missing SKILL.md file in .agents/skills/council-manager/.")
                fixed_any = True
            except Exception as e:
                log_error(f"Failed to create SKILL.md: {e}")
                sys.exit(1)

        # Fix project-council SKILL.md and skills.json
        project_council_dir = agents_dir / "skills" / "project-council"
        project_council_md = project_council_dir / "SKILL.md"
        skills_json = agents_dir / "skills.json"
        
        if not project_council_md.exists() or not skills_json.exists():
            project_council_dir.mkdir(parents=True, exist_ok=True)
            try:
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

1. **Official Tool Delegation (Critical)**: Do NOT write or simulate deliberations or voting results yourself within your model context. You MUST delegate all deliberations and voting loops to the `council-manager` CLI tools (e.g., `uv run council-manager deliberate` and `uv run council-manager vote`). This ensures they are processed through the official SQLite backend and using the project's configured council LLM provider (e.g., Ollama, local endpoints), even if you are operating on a different model (e.g. Gemini).
2. **Deliberations**: When the official `council-manager` tool runs deliberations, the system will prompt the underlying LLM to adopt the specialties listed above.
3. **Voting**: When the official `council-manager` tool runs voting, each team will evaluate proposals from the lens of their specific paradigm and domain.
4. **Impersonation**: Respect the distinct perspectives of each team. Do not merge their identities or dilute their specialties.
"""
                with open(project_council_md, "w", encoding="utf-8", newline="") as f:
                    f.write(project_council_content)
                log_success("Created missing project-council/SKILL.md file.")
                fixed_any = True
                
                # Write/Update skills.json
                import json
                config_data = {
                    "entries": [
                        { "path": str(skill_dir.as_posix()) },
                        { "path": str(project_council_dir.as_posix()) }
                    ]
                }
                with open(skills_json, "w", encoding="utf-8", newline="") as f:
                    json.dump(config_data, f, indent=2)
                log_success("Created missing skills.json registration file.")
                fixed_any = True
            except Exception as e:
                log_error(f"Failed to restore project-council skill: {e}")
                sys.exit(1)
                
        if not fixed_any:
            log_info("All default governance files (AGENTS.md, SKILL.md) are already present.")
        else:
            log_success("Governance files fixed successfully.")
        return

    # If project does not exist but --fix-missing was passed, raise an error
    if getattr(args, "fix_missing", False):
        log_error(f"No initialized project found at '{target_path}'. Cannot fix missing files. Please run without '--fix-missing' to initialize a new project.")
        sys.exit(1)

    # 1. Determine if we are in interactive mode
    # If any of the main inputs (path, project-id, description) are missing and stdin is a tty, we can run interactively.
    interactive = False
    if not args.path or not args.project_id or not getattr(args, "description", None):
        interactive = sys.stdin.isatty()

    project_id = args.project_id
    project_name = getattr(args, "name", None)
    description = getattr(args, "description", None)
    member_count = getattr(args, "member_count", None)


    if interactive:
        print("\n=== Council Manager Onboarding Wizard ===\n")
        
        # Prompt for Path
        if not path_str:
            default_path = os.getcwd()
            path_str = input(f"Enter target project directory [default: {default_path}]: ").strip() or default_path
        
        # Prompt for Project ID
        if not project_id:
            resolved_path = Path(path_str).resolve()
            default_id = resolved_path.name.lower().replace(" ", "_").replace("-", "_")
            project_id = input(f"Enter project ID / slug [default: {default_id}]: ").strip() or default_id
            
        # Prompt for Project Name
        if not project_name:
            default_name = project_id.replace("_", " ").title()
            project_name = input(f"Enter project name [default: {default_name}]: ").strip() or default_name

        # Prompt for Description
        if not description:
            print("\nEnter a description of the project and its core goals/problems.")
            print("This will be used to initialize the council and can be used by the AI to infer the optimal council size.")
            description = input("Project Description: ").strip()
            while not description:
                description = input("Description cannot be empty. Project Description: ").strip()

        # Prompt for Member Count (with AI inference option!)
        if not member_count:
            print("\nGovernance Council Team Member Count:")
            print("Under our rules, all 7 active paradigm teams (A-G) will receive the same global member count.")
            print("Would you like the AI to infer the optimal count based on the project description? (y/n)")
            choice = input("[default: y]: ").strip().lower() or "y"
            if choice == "y":
                log_info("Querying AI to infer optimal team member count...")
                try:
                    prompter = AgentPrompter()
                    inference = prompter.infer_global_member_count(description)
                    inferred_val = inference.global_member_count
                    rationale = inference.rationale
                    log_success(f"AI Suggestion: {inferred_val} members per team.")
                    print(f"Rationale: {rationale}")
                    confirm = input(f"Apply this suggestion? (y/n) [default: y]: ").strip().lower() or "y"
                    if confirm == "y":
                        member_count = inferred_val
                except Exception as e:
                    log_error(f"AI inference failed ({e}). Falling back to manual entry.")
            
            if not member_count:
                while True:
                    mc_str = input("Enter global member count (integer between 5 and 50) [default: 10]: ").strip() or "10"
                    try:
                        val = int(mc_str)
                        if 5 <= val <= 50:
                            member_count = val
                            break
                        else:
                            print("Please enter an integer between 5 and 50.")
                    except ValueError:
                        print("Invalid integer.")

        # Prompt for Council Persona
        inferred_teams = None
        council_template = getattr(args, "council_template", None)
        if council_template:
            inferred_teams = COUNCIL_TEMPLATES[council_template]
            log_success(f"Using specified council template: {council_template.upper()}")

        if not inferred_teams and description:
            print("\nGovernance Council Persona Selection:")
            print("Would you like the AI to infer and customize the 7 council teams based on the project description? (y/n)")
            choice_council = input("[default: y]: ").strip().lower() or "y"
            if choice_council == "y":
                log_info("Querying AI to infer optimal council teams...")
                try:
                    prompter = AgentPrompter()
                    council_inference = prompter.infer_project_council(description)
                    inferred_teams = []
                    for t in council_inference.teams:
                        inferred_teams.append({
                            "id": t.id,
                            "name": t.name,
                            "specialty": t.paradigm_specialty
                        })
                    log_success(f"AI inferred council template: {council_inference.selected_template.upper()}")
                    print("\nInferred Council Teams:")
                    for t in inferred_teams:
                        print(f"  Team {t['id']}: {t['name']} — {t['specialty']}")
                    confirm_council = input(f"\nApply these council teams? (y/n) [default: y]: ").strip().lower() or "y"
                    if confirm_council != "y":
                        inferred_teams = None
                except Exception as e:
                    log_error(f"AI council inference failed ({e}). Falling back to manual template selection.")
            
            if not inferred_teams:
                print("\nSelect a pre-defined council template:")
                print("1. Software Engineering (Functional, OOP, Imperative, Declarative, Dynamic Specialists)")
                print("2. Education / Pedagogy (Pedagogy, Curriculum, Assessment, Instructional Tech, Student Experience Specialists)")
                print("3. Marketing & Branding (Brand, Copywriting, Media Buying, SEO/Growth, PR Specialists)")
                print("4. General Business (Strategy/Finance, Operations, Customer Experience, Compliance, HR)")
                while True:
                    template_choice = input("Enter selection [1-4] [default: 1]: ").strip() or "1"
                    if template_choice == "1":
                        inferred_teams = COUNCIL_TEMPLATES["software"]
                        break
                    elif template_choice == "2":
                        inferred_teams = COUNCIL_TEMPLATES["education"]
                        break
                    elif template_choice == "3":
                        inferred_teams = COUNCIL_TEMPLATES["marketing"]
                        break
                    elif template_choice == "4":
                        inferred_teams = COUNCIL_TEMPLATES["general"]
                        break
                    else:
                        print("Invalid selection.")
        elif not inferred_teams:
            inferred_teams = COUNCIL_TEMPLATES["software"]
    else:
        # Non-interactive fallback defaults
        if not path_str:
            path_str = os.getcwd()
        if not project_id:
            project_id = "new_project"
        if not project_name:
            project_name = project_id.replace("_", " ").title()
        if not member_count:
            member_count = 10
        
        council_template = getattr(args, "council_template", None) or "software"
        inferred_teams = COUNCIL_TEMPLATES[council_template]

    target_path = Path(path_str).resolve()
    log_info(f"Initializing and onboarding project '{project_name}' in: {target_path}")
    log_info(f"Global team count set to: {member_count} members per group.")
    
    try:
        initialize_new_project(
            workspace_dir=target_path,
            project_id=project_id,
            project_name=project_name,
            global_member_count=member_count,
            project_description=description,
            custom_teams=inferred_teams
        )
        log_success("Project onboarded successfully.")
        if description:
            log_success("Initial description ratified and saved as DEC-001.")
    except Exception as e:
        log_error(f"Failed to onboard project: {e}")
        sys.exit(1)


def cmd_import(args):
    workspace = get_workspace_path(args.workspace)
    log_info(f"Importing CSV logs from {workspace / '.agents'} into SQLite database...")
    try:
        import_csv_to_db(workspace, args.project_id)
        log_success(f"CSV import completed for project '{args.project_id}'.")
    except Exception as e:
        log_error(f"Import failed: {e}")
        sys.exit(1)

def cmd_export(args):
    workspace = get_workspace_path(args.workspace)
    log_info(f"Exporting database tables from SQLite back to CSVs in {workspace / '.agents'}...")
    try:
        export_db_to_csv(workspace, args.project_id)
        log_success("Database tables exported back to CSV format successfully.")
    except Exception as e:
        log_error(f"Export failed: {e}")
        sys.exit(1)

def cmd_proposal_create(args):
    workspace = get_workspace_path(args.workspace)
    options = None
    if args.options:
        options = [opt.strip() for opt in args.options.split(";") if opt.strip()]
        
    log_info(f"Creating proposal in project '{args.project_id}'...")
    try:
        prop = council_orchestrator.create_proposal(
            workspace_dir=workspace,
            project_id=args.project_id,
            description=args.description,
            proposal_id=args.proposal_id,
            topic=args.topic,
            options=options
        )
        log_success(f"Proposal '{prop.id}' created. Status: {prop.status}")
        
        # Check auto-run flags
        if getattr(args, "vote", False):
            log_info(f"Auto-running Phase 1 Deliberation for proposal '{prop.id}'...")
            prop = asyncio.run(council_orchestrator.run_deliberation(workspace, prop.id))
            log_success(f"Deliberation complete. Status: {prop.status}")
            
            log_info(f"Auto-running Phase 2 Voting Loop for proposal '{prop.id}' (max {args.max_cycles} cycles)...")
            prop = asyncio.run(council_orchestrator.run_voting(workspace, prop.id, max_cycles=args.max_cycles))
            log_success(f"Voting complete. Final Status: {prop.status}")
        elif getattr(args, "deliberate", False):
            log_info(f"Auto-running Phase 1 Deliberation for proposal '{prop.id}'...")
            prop = asyncio.run(council_orchestrator.run_deliberation(workspace, prop.id))
            log_success(f"Deliberation complete. Status: {prop.status}")
            
    except Exception as e:
        log_error(f"Proposal creation or auto-run failed: {e}")
        sys.exit(1)


async def run_deliberation_async(args):
    workspace = get_workspace_path(args.workspace)
    proposal_id = get_proposal_id(args, workspace)
    log_info(f"Running Phase 1 Deliberation for proposal '{proposal_id}'...")
    
    def cli_progress(team_id: str, team_name: str, status: str, elapsed: float):
        if status == "STARTED":
            log_info(f"Team {team_id} ({team_name}) started deliberation...")
        elif status == "COMPLETED":
            log_success(f"Team {team_id} ({team_name}) completed in {elapsed:.2f}s.")

    try:
        prop = await council_orchestrator.run_deliberation(workspace, proposal_id, on_progress=cli_progress)
        log_success(f"Deliberation complete. Status updated to: {prop.status}")
        log_info(f"Collected rationales from {len(prop.rationales)} teams.")
    except Exception as e:
        log_error(f"Deliberation failed: {e}")
        sys.exit(1)

def cmd_deliberate(args):
    if getattr(args, "async_mode", False):
        workspace = get_workspace_path(args.workspace)
        proposal_id = get_proposal_id(args, workspace)
        session = db_manager.get_session(workspace)
        try:
            p = session.query(Proposal).filter_by(id=proposal_id).first()
            if not p:
                log_error(f"Proposal '{proposal_id}' not found.")
                sys.exit(1)
                
            task_id = generate_task_id(session, p.project_id)
            task = BackgroundTask(
                id=task_id,
                project_id=p.project_id,
                task_type="DELIBERATION",
                proposal_id=proposal_id,
                status="PENDING"
            )
            session.add(task)
            session.commit()
            
            spawn_background_task(workspace, task_id)
            log_success(f"Deliberation task '{task_id}' queued in background for proposal '{proposal_id}'.")
            log_info(f"Check status with: council-manager task-status {task_id}")
            log_info(f"View logs with:   council-manager task-logs {task_id} --tail")
        finally:
            session.close()
            db_manager.close_all()
    else:
        asyncio.run(run_deliberation_async(args))

async def run_voting_async(args):
    workspace = get_workspace_path(args.workspace)
    proposal_id = get_proposal_id(args, workspace)
    log_info(f"Running Phase 2 Voting Loop for proposal '{proposal_id}' (max {args.max_cycles} cycles)...")
    try:
        prop = await council_orchestrator.run_voting(workspace, proposal_id, max_cycles=args.max_cycles)
        log_success(f"Voting complete. Final Status: {prop.status}")
        log_info(f"Recorded {len(prop.votes)} votes in database.")
    except Exception as e:
        log_error(f"Voting failed: {e}")
        sys.exit(1)

def cmd_vote(args):
    if getattr(args, "async_mode", False):
        workspace = get_workspace_path(args.workspace)
        proposal_id = get_proposal_id(args, workspace)
        session = db_manager.get_session(workspace)
        try:
            p = session.query(Proposal).filter_by(id=proposal_id).first()
            if not p:
                log_error(f"Proposal '{proposal_id}' not found.")
                sys.exit(1)
                
            task_id = generate_task_id(session, p.project_id)
            task = BackgroundTask(
                id=task_id,
                project_id=p.project_id,
                task_type="VOTING",
                proposal_id=proposal_id,
                status="PENDING"
            )
            session.add(task)
            session.commit()
            
            spawn_background_task(workspace, task_id, max_cycles=args.max_cycles)
            log_success(f"Voting task '{task_id}' queued in background for proposal '{proposal_id}'.")
            log_info(f"Check status with: council-manager task-status {task_id}")
            log_info(f"View logs with:   council-manager task-logs {task_id} --tail")
        finally:
            session.close()
            db_manager.close_all()
    else:
        asyncio.run(run_voting_async(args))

def cmd_list(args):
    workspace = get_workspace_path(args.workspace)
    log_info(f"Listing proposals in database at {workspace}...")
    session = db_manager.get_session(workspace)
    try:
        props = session.query(Proposal).order_by(Proposal.created_at.desc()).all()
        if not props:
            print("No proposals found.")
            return
            
        print(f"\n{COLOR_BOLD}{'PROPOSAL ID':<15} {'STATUS':<25} {'TOPIC':<30}{COLOR_RESET}")
        print("-" * 75)
        for p in props:
            print(f"{p.id:<15} {p.status:<25} {p.topic:<30}")
        print()
    except Exception as e:
        log_error(f"Failed to query database: {e}")
    finally:
        session.close()
        db_manager.close_all()

def cmd_show(args):
    workspace = get_workspace_path(args.workspace)
    proposal_id = get_proposal_id(args, workspace)
    session = db_manager.get_session(workspace)
    try:
        p = session.query(Proposal).filter_by(id=proposal_id).first()
        if not p:
            log_error(f"Proposal '{proposal_id}' not found.")
            sys.exit(1)
            
        print(f"\n{COLOR_BOLD}{COLOR_CYAN}=== PROPOSAL DETAILS: {p.id} ==={COLOR_RESET}")
        print(f"{COLOR_BOLD}Topic:{COLOR_RESET}       {p.topic}")
        print(f"{COLOR_BOLD}Status:{COLOR_RESET}      {p.status}")
        print(f"{COLOR_BOLD}Description:{COLOR_RESET} {p.description}")
        print(f"{COLOR_BOLD}Options:{COLOR_RESET}     {'; '.join(p.options)}")
        print(f"{COLOR_BOLD}Created At:{COLOR_RESET}  {p.created_at}")
        
        if p.rationales:
            print(f"\n{COLOR_BOLD}{COLOR_CYAN}--- PHASE 1: DELIBERATION REPORTS ---{COLOR_RESET}")
            print(f"{COLOR_BOLD}### PROPOSAL{COLOR_RESET}\n{p.description}\n\n{COLOR_BOLD}### Stances:{COLOR_RESET}")
            for r in p.rationales:
                formatted = format_rationale(r['rationale'])
                # Indent formatted block slightly for readability
                indented = "  " + formatted.replace("\n", "\n  ")
                print(f"\n{COLOR_BOLD}Team: {r['team_id']}{COLOR_RESET}\n{indented}")
                
        if p.votes:
            print(f"\n{COLOR_BOLD}{COLOR_CYAN}--- PHASE 2: CAST VOTES ---{COLOR_RESET}")
            for v in p.votes:
                vote_val = v.get("vote", "")
                team_id = v.get("team_id", "")
                voter_id = v.get("voter_id", "")
                
                # Fetch rationale directly or fallback to Phase 1 list
                rationale = v.get("rationale", "")
                if not rationale and p.rationales:
                    for rat in p.rationales:
                        if rat.get("team_id") == team_id:
                            rationale = rat.get("rationale", "")
                            break
                            
                print(f"{COLOR_BOLD}[Voter {voter_id} / Team {team_id}]{COLOR_RESET} voted {COLOR_GREEN}'{vote_val}'{COLOR_RESET}")
                if rationale:
                    formatted = format_rationale(rationale)
                    indented = "  " + formatted.replace("\n", "\n  ")
                    print(f"{indented}")
        print()
    except Exception as e:
        log_error(f"Query failed: {e}")
    finally:
        session.close()
        db_manager.close_all()

def cmd_run_task_worker(args):
    workspace = get_workspace_path(args.workspace)
    task_id = args.task_id
    session = db_manager.get_session(workspace)
    try:
        task = session.query(BackgroundTask).filter_by(id=task_id).first()
        if not task:
            print(f"Task '{task_id}' not found.", file=sys.stderr)
            sys.exit(1)
            
        task.status = "RUNNING"
        session.commit()
        
        proposal_id = task.proposal_id
        task_type = task.task_type
        project_id = task.project_id
        
        def send_event(event_payload):
            import urllib.request
            import json
            import os
            server_url = os.environ.get("COUNCIL_SERVER_URL", "http://127.0.0.1:8000")
            url = f"{server_url}/tasks/{task_id}/events"
            req = urllib.request.Request(
                url,
                data=json.dumps(event_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            if workspace:
                req.add_header("X-Workspace-Path", str(workspace.resolve()))
            if settings.council_api_key:
                req.add_header("X-API-Key", settings.council_api_key)
            try:
                with urllib.request.urlopen(req, timeout=1.0) as response:
                    response.read()
            except Exception:
                pass

        def delib_progress(team_id: str, team_name: str, progress_status: str, elapsed: float):
            print(f"[PROGRESS] Team {team_id} ({team_name}): {progress_status} (elapsed: {elapsed:.2f}s)", flush=True)
            send_event({
                "event": "deliberation_progress",
                "team_id": team_id,
                "team_name": team_name,
                "status": progress_status,
                "elapsed": elapsed
            })

        def vote_progress(cycle: int, max_cycles: int, tally: dict, consensus_reached: bool):
            print(f"[PROGRESS] Cycle {cycle}/{max_cycles} complete. Tally: {tally}. Consensus: {consensus_reached}", flush=True)
            send_event({
                "event": "voting_cycle_complete",
                "cycle": cycle,
                "max_cycles": max_cycles,
                "tally": tally,
                "consensus_reached": consensus_reached
            })

        # Close connection handles before spawning the async run
        session.close()
        db_manager.close_all()
        
        if task_type == "DELIBERATION":
            asyncio.run(council_orchestrator.run_deliberation(workspace, proposal_id, on_progress=delib_progress))
        elif task_type == "VOTING":
            asyncio.run(council_orchestrator.run_voting(workspace, proposal_id, max_cycles=args.max_cycles, on_cycle_complete=vote_progress))
            
        # Re-open session to complete task
        session = db_manager.get_session(workspace)
        task = session.query(BackgroundTask).filter_by(id=task_id).first()
        task.status = "COMPLETED"
        session.commit()
        
        # Export database state back to CSV files
        export_db_to_csv(workspace, project_id)
        
    except Exception as e:
        try:
            session = db_manager.get_session(workspace)
            task = session.query(BackgroundTask).filter_by(id=task_id).first()
            if task:
                task.status = "FAILED"
                task.error_message = str(e)
                session.commit()
        except Exception:
            pass
        print(f"Task execution failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        try:
            session.close()
        except Exception:
            pass
        db_manager.close_all()

def cmd_task_status(args):
    workspace = get_workspace_path(args.workspace)
    task_id = args.task_id
    session = db_manager.get_session(workspace)
    try:
        task = session.query(BackgroundTask).filter_by(id=task_id).first()
        if not task:
            log_error(f"Task '{task_id}' not found.")
            sys.exit(1)
            
        print(f"\n{COLOR_BOLD}=== Task Status: {task.id} ==={COLOR_RESET}")
        print(f"{COLOR_BOLD}Type:{COLOR_RESET}        {task.task_type}")
        print(f"{COLOR_BOLD}Proposal ID:{COLOR_RESET} {task.proposal_id}")
        
        status_color = COLOR_RESET
        if task.status == "RUNNING":
            status_color = COLOR_CYAN
        elif task.status == "COMPLETED":
            status_color = COLOR_GREEN
        elif task.status == "FAILED":
            status_color = COLOR_RED
            
        print(f"{COLOR_BOLD}Status:{COLOR_RESET}      {status_color}{task.status}{COLOR_RESET}")
        if task.error_message:
            print(f"{COLOR_BOLD}Error:{COLOR_RESET}       {COLOR_RED}{task.error_message}{COLOR_RESET}")
        print(f"{COLOR_BOLD}Created At:{COLOR_RESET}  {task.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{COLOR_BOLD}Updated At:{COLOR_RESET}  {task.updated_at.strftime('%Y-%m-%d %H:%M:%S')}")
        print()
    finally:
        session.close()
        db_manager.close_all()

def cmd_task_logs(args):
    workspace = get_workspace_path(args.workspace)
    task_id = args.task_id
    log_file = workspace / ".agents" / "logs" / f"{task_id}.log"
    
    if not log_file.exists():
        log_error(f"No log file found for task '{task_id}'. (It may not have started running yet)")
        sys.exit(1)
        
    print(f"\n{COLOR_BOLD}=== Logs for Task: {task_id} ==={COLOR_RESET}")
    
    if not getattr(args, "tail", False):
        with open(log_file, "r", encoding="utf-8") as f:
            print(f.read())
        return
        
    import time
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            print(f.read(), end="")
            while True:
                line = f.readline()
                if not line:
                    session = db_manager.get_session(workspace)
                    task = session.query(BackgroundTask).filter_by(id=task_id).first()
                    status = task.status if task else "COMPLETED"
                    session.close()
                    db_manager.close_all()
                    
                    if status in ("COMPLETED", "FAILED"):
                        line = f.readline()
                        while line:
                            print(line, end="")
                            line = f.readline()
                        break
                        
                    time.sleep(0.5)
                    continue
                print(line, end="")
        print(f"\n{COLOR_GREEN}Task finished execution.{COLOR_RESET}\n")
    except KeyboardInterrupt:
        print(f"\n{COLOR_CYAN}Stopped tailing logs.{COLOR_RESET}\n")

def cmd_server(args):
    import uvicorn
    log_info(f"Starting Council Manager API server on {args.host}:{args.port}...")
    if settings.council_api_key:
        log_warn("API security is enabled. Set COUNCIL_API_KEY environment variable or pass X-API-Key header to authorize requests.")
    else:
        log_info("API security is disabled. Enforce security by setting COUNCIL_API_KEY environment variable.")
        
    try:
        uvicorn.run("council_manager.server.main:app", host=args.host, port=args.port, reload=args.reload)
    except KeyboardInterrupt:
        log_info("Server stopped by user.")

def cmd_dashboard(args):
    from council_manager.server.tui import CouncilDashboardApp
    workspace = get_workspace_path(args.workspace)
    log_info("Starting Council Manager Terminal Dashboard UI...")
    app = CouncilDashboardApp(workspace=workspace)
    app.run()

def cmd_show_teams(args):
    workspace = get_workspace_path(args.workspace)
    log_info("Querying teams from registry database...")
    session = db_manager.get_session(workspace)
    try:
        teams = session.query(Team).all()
        if not teams:
            print("No registered teams found.")
            return
        print(f"\n{COLOR_BOLD}{'TEAM ID':<8} {'TEAM NAME':<30} {'WEIGHT':<8} {'PARADIGM SPECIALTY':<40}{COLOR_RESET}")
        print("-" * 90)
        for t in teams:
            print(f"{t.id:<8} {t.name:<30} {t.vote_weight:<8} {t.paradigm_specialty:<40}")
        print()
    except Exception as e:
        log_error(f"Failed: {e}")
    finally:
        session.close()
        db_manager.close_all()

def cmd_show_decisions(args):
    workspace = get_workspace_path(args.workspace)
    log_info("Querying ratified decisions...")
    session = db_manager.get_session(workspace)
    try:
        decisions = session.query(Decision).all()
        if not decisions:
            print("No ratified decisions found.")
            return
        print(f"\n{COLOR_BOLD}{'DEC ID':<10} {'DATE':<12} {'TOPIC':<25} {'DECISION':<25}{COLOR_RESET}")
        print("-" * 80)
        for d in decisions:
            print(f"{d.id:<10} {d.date.strftime('%Y-%m-%d'):<12} {d.topic:<25} {d.decision:<25}")
        print()
    except Exception as e:
        log_error(f"Failed: {e}")
    finally:
        session.close()
        db_manager.close_all()

def cmd_show_roadmap(args):
    workspace = get_workspace_path(args.workspace)
    log_info("Querying project roadmap tasks...")
    session = db_manager.get_session(workspace)
    try:
        tasks = session.query(RoadmapTask).order_by(RoadmapTask.phase, RoadmapTask.id).all()
        if not tasks:
            print("No roadmap tasks found.")
            return
        print(f"\n{COLOR_BOLD}{'PHASE':<6} {'TASK ID':<10} {'TASK NAME':<45} {'STATUS':<10}{COLOR_RESET}")
        print("-" * 80)
        for t in tasks:
            print(f"{t.phase:<6} {t.id:<10} {t.task:<45} {t.status:<10}")
        print()
    except Exception as e:
        log_error(f"Failed: {e}")
    finally:
        session.close()
        db_manager.close_all()

def cmd_show_audits(args):
    workspace = get_workspace_path(args.workspace)
    log_info("Querying quality audits log...")
    session = db_manager.get_session(workspace)
    try:
        audits = session.query(AuditLog).order_by(AuditLog.timestamp.desc()).all()
        if not audits:
            print("No audit entries found.")
            return
        print(f"\n{COLOR_BOLD}{'TIMESTAMP':<20} {'AUDIT ID':<10} {'ALIGNMENT':<12} {'AUDITOR':<10} {'SUMMARY':<30}{COLOR_RESET}")
        print("-" * 90)
        for a in audits:
            ts = a.timestamp.strftime("%Y-%m-%d %H:%M")
            print(f"{ts:<20} {a.id:<10} {int(a.alignment_score)}%{' ':<8} {a.auditor_team:<10} {a.summary:<30}")
        print()
    except Exception as e:
        log_error(f"Failed: {e}")
    finally:
        session.close()
        db_manager.close_all()

async def run_team_deliberate_async(args):
    workspace = get_workspace_path(args.workspace)
    proposal_id = get_proposal_id(args, workspace)
    team_id = args.team_id
    
    log_info(f"Triggering individual deliberation for Team '{team_id}' on proposal '{proposal_id}'...")
    from council_manager.core.registry import agent_registry
    team = agent_registry.get_team(workspace, team_id)
    if not team:
        log_error(f"Team '{team_id}' not found in workspace.")
        sys.exit(1)
        
    session = db_manager.get_session(workspace)
    try:
        prop = session.query(Proposal).filter_by(id=proposal_id).first()
        if not prop:
            log_error(f"Proposal '{proposal_id}' not found.")
            sys.exit(1)
        topic = prop.topic
        desc = prop.description
        opts = prop.options
    finally:
        session.close()
        
    try:
        delib_res = await council_orchestrator.prompter.generate_deliberation_async(
            team_name=team.name,
            paradigm_specialty=team.paradigm_specialty,
            title=topic,
            description=desc,
            options=opts
        )
        rat_dict = {
            "stance": delib_res.stance,
            "motivation": delib_res.motivation,
            "suggestion": delib_res.suggestion
        }
        formatted = format_rationale(rat_dict)
        print(f"\n{COLOR_BOLD}{COLOR_CYAN}=== TEAM DELIBERATION RESULT: {team.name} ({team.id}) ==={COLOR_RESET}")
        print(formatted)
        print()
    except Exception as e:
        log_error(f"Failed to deliberate: {e}")
        sys.exit(1)

def cmd_team_deliberate(args):
    asyncio.run(run_team_deliberate_async(args))

async def run_team_vote_async(args):
    workspace = get_workspace_path(args.workspace)
    proposal_id = get_proposal_id(args, workspace)
    team_id = args.team_id
    
    log_info(f"Triggering individual vote for Team '{team_id}' on proposal '{proposal_id}'...")
    from council_manager.core.registry import agent_registry
    team = agent_registry.get_team(workspace, team_id)
    if not team:
        log_error(f"Team '{team_id}' not found in workspace.")
        sys.exit(1)
        
    session = db_manager.get_session(workspace)
    try:
        prop = session.query(Proposal).filter_by(id=proposal_id).first()
        if not prop:
            log_error(f"Proposal '{proposal_id}' not found.")
            sys.exit(1)
        topic = prop.topic
        desc = prop.description
        opts = prop.options
        delib_rationales = prop.rationales or []
    finally:
        session.close()
        
    # Seed deliberations context
    rationales_context = "Deliberation Justifications:\n" + "\n".join(
        f"- {r['team_id']}: {r['rationale'][:400]}" for r in delib_rationales
    )

    
    try:
        res = await council_orchestrator.prompter.generate_vote_async(
            team_name=team.name,
            paradigm_specialty=team.paradigm_specialty,
            title=topic,
            description=desc,
            options=opts,
            rationales_context=rationales_context
        )
        print(f"\n{COLOR_BOLD}{COLOR_CYAN}=== TEAM VOTE RESULT: {team.name} ({team.id}) ==={COLOR_RESET}")
        print(f"{COLOR_BOLD}Vote cast:{COLOR_RESET}  {COLOR_GREEN}'{res.vote}'{COLOR_RESET}")
        print(f"{COLOR_BOLD}Rationale:{COLOR_RESET}  {res.rationale}")
        print()
    except Exception as e:
        log_error(f"Failed to vote: {e}")
        sys.exit(1)

async def run_proposal_ratify_async(args):
    workspace = get_workspace_path(args.workspace)
    proposal_id = get_proposal_id(args, workspace)
    
    session = db_manager.get_session(workspace)
    try:
        p = session.query(Proposal).filter_by(id=proposal_id).first()
        if not p:
            log_error(f"Proposal '{proposal_id}' not found.")
            sys.exit(1)
            
        print(f"\n{COLOR_BOLD}{COLOR_CYAN}=== INTERACTIVE RATIFICATION WIZARD: {p.id} ==={COLOR_RESET}")
        print(f"{COLOR_BOLD}Topic:{COLOR_RESET}       {p.topic}")
        print(f"{COLOR_BOLD}Description:{COLOR_RESET} {p.description}")
        print(f"{COLOR_BOLD}Status:{COLOR_RESET}      {p.status}")
        print(f"{COLOR_BOLD}Options:{COLOR_RESET}")
        for i, opt in enumerate(p.options, 1):
            print(f"  {i}. {opt}")
            
        # Display full rationales for the votes
        print(f"\n{COLOR_BOLD}{COLOR_CYAN}--- VOTES CAST & DETAILED RATIONALES ---{COLOR_RESET}")
        rat_dict = {r["team_id"]: r["rationale"] for r in (p.rationales or [])}
        
        votes = p.votes or []
        if not votes:
            print("No votes recorded for this proposal yet.")
        else:
            for v in votes:
                team_id = v.get("team_id", "")
                vote_val = v.get("vote", "")
                rationale_val = v.get("rationale", "") or rat_dict.get(team_id, "")
                
                print(f"\n{COLOR_BOLD}[Team {team_id}] voted '{vote_val}'{COLOR_RESET}")
                formatted = format_rationale(rationale_val)
                indented = "  " + formatted.replace("\n", "\n  ")
                print(f"{indented}")
                print("-" * 50)
                
        # Ask user for decision
        print(f"\n{COLOR_BOLD}Select an action:{COLOR_RESET}")
        for i, opt in enumerate(p.options, 1):
            print(f"  [{i}] Ratify Option: '{opt}'")
        print(f"  [A] State a new custom alternative (starts a new proposal & voting cycle)")
        print(f"  [Q] Cancel / Quit")
        
        choice = input("\nEnter choice: ").strip()
        if choice.lower() == 'q':
            print("Ratification cancelled.")
            return
            
        if choice.lower() == 'a':
            new_desc = input("\nEnter description for the new proposal/alternative: ").strip()
            if not new_desc:
                log_error("Description cannot be empty.")
                return
            
            log_info("Starting a new proposal & voting cycle immediately...")
            
            # Create, Deliberate, and Vote
            new_prop = council_orchestrator.create_proposal(
                workspace_dir=workspace,
                project_id=p.project_id,
                description=new_desc
            )
            log_success(f"Created new proposal '{new_prop.id}' with topic: '{new_prop.topic}'")
            
            log_info(f"Running Phase 1 Deliberation for '{new_prop.id}'...")
            new_prop = await council_orchestrator.run_deliberation(workspace, new_prop.id)
            log_success("Deliberation complete.")
            
            log_info(f"Running Phase 2 Voting Loop for '{new_prop.id}'...")
            new_prop = await council_orchestrator.run_voting(workspace, new_prop.id)
            log_success("Voting complete.")
            
            # Rerun the ratification command on the new proposal
            args.proposal_id = new_prop.id
            session.close()
            db_manager.close_all()
            await run_proposal_ratify_async(args)
            return
            
        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(p.options):
                raise ValueError()
            selected_option = p.options[idx]
        except ValueError:
            log_error("Invalid selection.")
            return
            
        # 1. Ask for Roadmap Task ID
        print(f"\n{COLOR_BOLD}Roadmap Sync:{COLOR_RESET}")
        roadmap_tasks = session.query(RoadmapTask).filter_by(project_id=p.project_id).all()
        todo_tasks = [t for t in roadmap_tasks if t.status != 'DONE']
        if todo_tasks:
            print("Open roadmap tasks:")
            for t in todo_tasks:
                print(f"  - {t.id}: {t.task}")
        else:
            print("No open roadmap tasks found.")
            
        task_id = input("\nEnter roadmap task ID to mark as DONE (leave empty to skip): ").strip()
        
        session.close()
        
        # 2. Ratify the proposal using orchestrator logic
        council_orchestrator.ratify_proposal(
            workspace_dir=workspace,
            proposal_id=p.id,
            decision_option=selected_option,
            roadmap_task_id=task_id if task_id else None
        )
        
        log_success(f"Proposal '{p.id}' successfully ratified!")
        log_info(f"Decision registered: '{selected_option}'")
        if task_id:
            log_info(f"Roadmap task '{task_id}' updated to DONE.")
            
    except Exception as e:
        log_error(f"Ratification failed: {e}")
    finally:
        db_manager.close_all()

def cmd_proposal_ratify(args):
    asyncio.run(run_proposal_ratify_async(args))

def cmd_team_vote(args):
    asyncio.run(run_team_vote_async(args))

def cmd_register_skill(args):
    import json
    target_path = Path(args.workspace or os.getcwd()).resolve()
    agents_dir = target_path / ".agents"
    
    if not agents_dir.exists():
        log_error(f"No initialized project found at '{target_path}'. Please run 'init-project' first.")
        sys.exit(1)
        
    skills_dir = agents_dir / "skills"
    entries = []
    
    if skills_dir.exists():
        for item in skills_dir.iterdir():
            if item.is_dir() and (item / "SKILL.md").exists():
                entries.append({ "path": str(item.as_posix()) })
                
    if not entries:
        log_error(f"No skill files found in '{skills_dir}'. Please run 'init-project --fix-missing' to restore them.")
        sys.exit(1)
        
    skills_json_path = agents_dir / "skills.json"
    config_data = {
        "entries": entries
    }
    
    try:
        with open(skills_json_path, "w", encoding="utf-8", newline="") as f:
            json.dump(config_data, f, indent=2)
        log_success(f"Successfully registered skills in {skills_json_path}")
        for entry in entries:
            log_info(f"Registered path: {entry['path']}")
    except Exception as e:
        log_error(f"Failed to write skills.json: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Council Manager CLI: Interact with isolated multi-team governance databases.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug logging of transition events and API communications.")
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    # Command: init-project
    p_init = subparsers.add_parser("init-project", help="Initialize a new project directory with templates and interactive onboarding.")
    p_init.add_argument("--path", help="Target folder to initialize project in. (optional, prompts if omitted)")
    p_init.add_argument("--project-id", help="Identifier of the project. (optional, prompts if omitted)")
    p_init.add_argument("--name", help="Name of the project. (optional, prompts if omitted)")
    p_init.add_argument("--description", help="Description of the project. (optional, prompts if omitted)")
    p_init.add_argument("--member-count", type=int, help="Global member count for all teams. (optional, prompts/infers if omitted)")
    p_init.add_argument("--council-template", choices=["software", "education", "marketing", "general"], help="Pre-defined council template to use. (optional, prompts/infers if omitted)")
    p_init.add_argument("--fix-missing", action="store_true", help="Fix missing default files (like AGENTS.md or SKILL.md) in an already initialized project without re-onboarding.")


    # Command: import
    p_import = subparsers.add_parser("import", help="Import CSV data into the SQLite database.")
    p_import.add_argument("-w", "--workspace", help="Path to the workspace folder containing .agents/")
    p_import.add_argument("-p", "--project-id", default="council_manager", help="ID of the project target.")

    # Command: export
    p_export = subparsers.add_parser("export", help="Export SQLite database state back to CSV files.")
    p_export.add_argument("-w", "--workspace", help="Path to the workspace folder.")
    p_export.add_argument("-p", "--project-id", default="council_manager", help="ID of the project.")

    # Command: proposal-create
    p_create = subparsers.add_parser("proposal-create", help="Create a new proposal in the database.")
    p_create.add_argument("description", help="Detailed description of the proposal.")
    p_create.add_argument("-w", "--workspace", help="Path to the workspace folder.")
    p_create.add_argument("-p", "--project-id", default="council_manager", help="ID of the project.")
    p_create.add_argument("--proposal-id", help="Unique identifier for the proposal.")
    p_create.add_argument("--topic", help="Title or topic of the proposal.")
    p_create.add_argument("--options", help="Semicolon-delimited list of options (e.g. 'Alt 1; Alt 2').")
    p_create.add_argument("--deliberate", action="store_true", help="Automatically run Phase 1 Deliberation after creation.")
    p_create.add_argument("--vote", action="store_true", help="Automatically run Phase 1 Deliberation and Phase 2 Voting Loop after creation.")
    p_create.add_argument("--max-cycles", type=int, default=5, help="Maximum voting cycles to run (used with --vote).")

    # Command: deliberate
    p_deliberate = subparsers.add_parser("deliberate", help="Run Phase 1 (Deliberation) to gather engineering justifications.")
    p_deliberate.add_argument("-w", "--workspace", help="Path to the workspace folder.")
    p_deliberate.add_argument("--proposal-id", help="ID of the target proposal (defaults to latest).")
    p_deliberate.add_argument("--async", action="store_true", dest="async_mode", help="Run deliberation in the background.")

    # Command: vote
    p_vote = subparsers.add_parser("vote", help="Run Phase 2 (Voting Loop) to cast consensus votes.")
    p_vote.add_argument("-w", "--workspace", help="Path to the workspace folder.")
    p_vote.add_argument("--proposal-id", help="ID of the target proposal (defaults to latest).")
    p_vote.add_argument("--max-cycles", type=int, default=5, help="Maximum number of debate/voting cycles.")
    p_vote.add_argument("--async", action="store_true", dest="async_mode", help="Run voting in the background.")

    # Command: list
    p_list = subparsers.add_parser("list", help="List all proposals in the workspace database.")
    p_list.add_argument("-w", "--workspace", help="Path to the workspace folder.")

    # Command: show
    p_show = subparsers.add_parser("show", help="Show full detail log of a specific proposal.")
    p_show.add_argument("-w", "--workspace", help="Path to the workspace folder.")
    p_show.add_argument("--proposal-id", help="ID of the proposal to show (defaults to latest).")

    # Command: show-teams
    p_teams = subparsers.add_parser("show-teams", help="Show all registered teams in the registry.")
    p_teams.add_argument("-w", "--workspace", help="Path to the workspace folder.")

    # Command: show-decisions
    p_decs = subparsers.add_parser("show-decisions", help="Show all ratified decisions in the database.")
    p_decs.add_argument("-w", "--workspace", help="Path to the workspace folder.")

    # Command: show-roadmap
    p_road = subparsers.add_parser("show-roadmap", help="Show all tasks listed in the database roadmap.")
    p_road.add_argument("-w", "--workspace", help="Path to the workspace folder.")

    # Command: show-audits
    p_auds = subparsers.add_parser("show-audits", help="Show quality and compliance audit logs.")
    p_auds.add_argument("-w", "--workspace", help="Path to the workspace folder.")

    # Command: team-deliberate
    p_td = subparsers.add_parser("team-deliberate", help="Instruct a single team to deliberate on a proposal individually.")
    p_td.add_argument("-w", "--workspace", help="Path to the workspace folder.")
    p_td.add_argument("--team-id", required=True, help="ID of the team to call.")
    p_td.add_argument("--proposal-id", help="ID of the target proposal (defaults to latest).")

    # Command: team-vote
    p_tv = subparsers.add_parser("team-vote", help="Instruct a single team to vote on a proposal individually.")
    p_tv.add_argument("-w", "--workspace", help="Path to the workspace folder.")
    p_tv.add_argument("--team-id", required=True, help="ID of the team to call.")
    p_tv.add_argument("--proposal-id", help="ID of the target proposal (defaults to latest).")
    
    # Command: proposal-ratify
    p_pr = subparsers.add_parser("proposal-ratify", help="Interactively review rationales, choose decision, and update roadmap.")
    p_pr.add_argument("-w", "--workspace", help="Path to the workspace folder.")
    p_pr.add_argument("--proposal-id", help="ID of the target proposal (defaults to latest).")

    # Command: run-task-worker (internal hidden subprocess worker)
    p_worker = subparsers.add_parser("run-task-worker", help=argparse.SUPPRESS)
    p_worker.add_argument("task_id", help="ID of the background task.")
    p_worker.add_argument("-w", "--workspace", help="Path to the workspace folder.")
    p_worker.add_argument("--max-cycles", type=int, default=5, help="Maximum debate cycles.")

    # Command: task-status
    p_tstatus = subparsers.add_parser("task-status", help="Check the current status of a background task.")
    p_tstatus.add_argument("task_id", help="ID of the target background task.")
    p_tstatus.add_argument("-w", "--workspace", help="Path to the workspace folder.")

    # Command: task-logs
    p_tlogs = subparsers.add_parser("task-logs", help="View or tail the console logs for a background task.")
    p_tlogs.add_argument("task_id", help="ID of the target background task.")
    p_tlogs.add_argument("-w", "--workspace", help="Path to the workspace folder.")
    p_tlogs.add_argument("--tail", action="store_true", help="Tail the log output in real-time.")

    # Command: start-server
    p_server = subparsers.add_parser("start-server", help="Start the FastAPI API backend server.")
    p_server.add_argument("--host", default="127.0.0.1", help="Binding host address.")
    p_server.add_argument("--port", type=int, default=8000, help="Binding port number.")
    p_server.add_argument("--reload", action="store_true", help="Enable code hot-reloading for development.")

    # Command: dashboard
    p_dash = subparsers.add_parser("dashboard", help="Launch the interactive Terminal UI dashboard.")
    p_dash.add_argument("-w", "--workspace", help="Path to the workspace folder.")

    # Command: register-skill
    p_reg = subparsers.add_parser("register-skill", help="Explicitly register all local workspace skills (council-manager, project-council) in skills.json.")
    p_reg.add_argument("-w", "--workspace", help="Path to the workspace folder.")

    args = parser.parse_args()
    if args.debug:
        settings.debug = True

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Subcommand routing
    if args.command == "init-project":
        cmd_init_project(args)
    elif args.command == "import":
        cmd_import(args)
    elif args.command == "export":
        cmd_export(args)
    elif args.command == "proposal-create":
        cmd_proposal_create(args)
    elif args.command == "deliberate":
        cmd_deliberate(args)
    elif args.command == "vote":
        cmd_vote(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "show-teams":
        cmd_show_teams(args)
    elif args.command == "show-decisions":
        cmd_show_decisions(args)
    elif args.command == "show-roadmap":
        cmd_show_roadmap(args)
    elif args.command == "show-audits":
        cmd_show_audits(args)
    elif args.command == "team-deliberate":
        cmd_team_deliberate(args)
    elif args.command == "team-vote":
        cmd_team_vote(args)
    elif args.command == "proposal-ratify":
        cmd_proposal_ratify(args)
    elif args.command == "run-task-worker":
        cmd_run_task_worker(args)
    elif args.command == "task-status":
        cmd_task_status(args)
    elif args.command == "task-logs":
        cmd_task_logs(args)
    elif args.command == "start-server":
        cmd_server(args)
    elif args.command == "dashboard":
        cmd_dashboard(args)
    elif args.command == "register-skill":
        cmd_register_skill(args)

if __name__ == "__main__":
    main()
