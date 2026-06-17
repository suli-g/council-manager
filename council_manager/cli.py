import argparse
import asyncio
import os
import sys
from pathlib import Path
from council_manager.db import db_manager, Proposal, Team, Decision, AuditLog, RoadmapTask, initialize_new_project, import_csv_to_db, export_db_to_csv
from council_manager.core.orchestrator import council_orchestrator

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

def get_workspace_path(path_arg: str | None) -> Path:
    if path_arg:
        p = Path(path_arg).resolve()
    else:
        p = Path(os.getcwd()).resolve()
    return p

def cmd_init_project(args):
    target_path = Path(args.path).resolve()
    log_info(f"Initializing new project '{args.project_id}' in directory: {target_path}")
    try:
        initialize_new_project(target_path, args.project_id)
        log_success("Project initialized and template CSV files imported successfully.")
    except Exception as e:
        log_error(f"Failed to initialize project: {e}")
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
    except Exception as e:
        log_error(f"Proposal creation failed: {e}")
        sys.exit(1)


async def run_deliberation_async(args):
    workspace = get_workspace_path(args.workspace)
    log_info(f"Running Phase 1 Deliberation for proposal '{args.proposal_id}'...")
    try:
        prop = await council_orchestrator.run_deliberation(workspace, args.proposal_id)
        log_success(f"Deliberation complete. Status updated to: {prop.status}")
        log_info(f"Collected rationales from {len(prop.rationales)} teams.")
    except Exception as e:
        log_error(f"Deliberation failed: {e}")
        sys.exit(1)

def cmd_deliberate(args):
    asyncio.run(run_deliberation_async(args))

async def run_voting_async(args):
    workspace = get_workspace_path(args.workspace)
    log_info(f"Running Phase 2 Voting Loop for proposal '{args.proposal_id}' (max {args.max_cycles} cycles)...")
    try:
        prop = await council_orchestrator.run_voting(workspace, args.proposal_id, max_cycles=args.max_cycles)
        log_success(f"Voting complete. Final Status: {prop.status}")
        log_info(f"Recorded {len(prop.votes)} votes in database.")
    except Exception as e:
        log_error(f"Voting failed: {e}")
        sys.exit(1)

def cmd_vote(args):
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
    session = db_manager.get_session(workspace)
    try:
        p = session.query(Proposal).filter_by(id=args.proposal_id).first()
        if not p:
            log_error(f"Proposal '{args.proposal_id}' not found.")
            sys.exit(1)
            
        print(f"\n{COLOR_BOLD}{COLOR_CYAN}=== PROPOSAL DETAILS: {p.id} ==={COLOR_RESET}")
        print(f"{COLOR_BOLD}Topic:{COLOR_RESET}       {p.topic}")
        print(f"{COLOR_BOLD}Status:{COLOR_RESET}      {p.status}")
        print(f"{COLOR_BOLD}Description:{COLOR_RESET} {p.description}")
        print(f"{COLOR_BOLD}Options:{COLOR_RESET}     {'; '.join(p.options)}")
        print(f"{COLOR_BOLD}Created At:{COLOR_RESET}  {p.created_at}")
        
        if p.rationales:
            print(f"\n{COLOR_BOLD}{COLOR_CYAN}--- PHASE 1: COLLECTED RATIONALES ---{COLOR_RESET}")
            for r in p.rationales:
                print(f"{COLOR_BOLD}[Team {r['team_id']}]{COLOR_RESET} {r['rationale']}")
                
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
                    print(f"  Rationale: {rationale}")
        print()
    except Exception as e:
        log_error(f"Query failed: {e}")
    finally:
        session.close()
        db_manager.close_all()

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
    team_id = args.team_id
    proposal_id = args.proposal_id
    
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
        rationale = await council_orchestrator.prompter.generate_deliberation_async(
            team_name=team.name,
            paradigm_specialty=team.paradigm_specialty,
            title=topic,
            description=desc,
            options=opts
        )
        print(f"\n{COLOR_BOLD}{COLOR_CYAN}=== TEAM DELIBERATION RESULT: {team.name} ({team.id}) ==={COLOR_RESET}")
        print(rationale)
        print()
    except Exception as e:
        log_error(f"Failed to deliberate: {e}")
        sys.exit(1)

def cmd_team_deliberate(args):
    asyncio.run(run_team_deliberate_async(args))

async def run_team_vote_async(args):
    workspace = get_workspace_path(args.workspace)
    team_id = args.team_id
    proposal_id = args.proposal_id
    
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
        f"- {r['team_id']}: {r['rationale']}" for r in delib_rationales
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

def cmd_team_vote(args):
    asyncio.run(run_team_vote_async(args))

def main():
    parser = argparse.ArgumentParser(
        description="Council Manager CLI: Interact with isolated multi-team governance databases.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    # Command: init-project
    p_init = subparsers.add_parser("init-project", help="Initialize a new project directory with templates.")
    p_init.add_argument("--path", required=True, help="Target folder to initialize project in.")
    p_init.add_argument("--project-id", default="new_project", help="Identifier of the project.")

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


    # Command: deliberate
    p_deliberate = subparsers.add_parser("deliberate", help="Run Phase 1 (Deliberation) to gather engineering justifications.")
    p_deliberate.add_argument("-w", "--workspace", help="Path to the workspace folder.")
    p_deliberate.add_argument("--proposal-id", required=True, help="ID of the target proposal.")

    # Command: vote
    p_vote = subparsers.add_parser("vote", help="Run Phase 2 (Voting Loop) to cast consensus votes.")
    p_vote.add_argument("-w", "--workspace", help="Path to the workspace folder.")
    p_vote.add_argument("--proposal-id", required=True, help="ID of the target proposal.")
    p_vote.add_argument("--max-cycles", type=int, default=5, help="Maximum number of debate/voting cycles.")

    # Command: list
    p_list = subparsers.add_parser("list", help="List all proposals in the workspace database.")
    p_list.add_argument("-w", "--workspace", help="Path to the workspace folder.")

    # Command: show
    p_show = subparsers.add_parser("show", help="Show full detail log of a specific proposal.")
    p_show.add_argument("-w", "--workspace", help="Path to the workspace folder.")
    p_show.add_argument("--proposal-id", required=True, help="ID of the proposal to show.")

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
    p_td.add_argument("--proposal-id", required=True, help="ID of the target proposal.")

    # Command: team-vote
    p_tv = subparsers.add_parser("team-vote", help="Instruct a single team to vote on a proposal individually.")
    p_tv.add_argument("-w", "--workspace", help="Path to the workspace folder.")
    p_tv.add_argument("--team-id", required=True, help="ID of the team to call.")
    p_tv.add_argument("--proposal-id", required=True, help="ID of the target proposal.")

    args = parser.parse_args()

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

if __name__ == "__main__":
    main()
