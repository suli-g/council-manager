import csv
import os
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Any
from sqlalchemy.orm import Session
from council_manager.db import db_manager
from council_manager.db.models import Project, Team, Proposal, Decision, Alternative, AuditLog

def safe_parse_date(date_str: str) -> date:
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except Exception:
        return datetime.now().date()

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
            with open(audits_csv, mode="r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    audit_id = row["audit_id"].strip()
                    audit = session.query(AuditLog).filter_by(id=audit_id).first()
                    if not audit:
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
                writer.writerow(["voter_id", "team_id", "vote", "rationale"])
                
                # Combine votes and rationales
                rat_dict = {r["team_id"]: r["rationale"] for r in p.rationales}
                for v in p.votes:
                    voter_id = v.get("voter_id", f"V-{v.get('team_id')}")
                    team_id = v.get("team_id", "")
                    vote_val = v.get("vote", "")
                    rationale_val = rat_dict.get(team_id, "")
                    writer.writerow([voter_id, team_id, vote_val, rationale_val])
            
            # Format timestamp for manifest
            manifest_ts = p.created_at.strftime("%Y-%m-%dT%H:%M:%S")
            manifest_entries.append([p.id, p.topic, f"docs/.agents/votes/{p.id}.csv", manifest_ts])

        # Write manifest
        with open(manifest_csv, mode="w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["decision_id", "topic", "file_path", "timestamp"])
            for entry in sorted(manifest_entries, key=lambda x: x[0]):
                writer.writerow(entry)

    finally:
        session.close()
