"""
Pipe-and-Filter Context Compaction Pipeline (P6-02, v0.9.1).

Constructs structured, token-optimized context blocks summarizing active 
teams, recent ratified decisions, and roadmap tasks for local LLM consumption.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pathlib import Path
from council_manager.db import db_manager
from council_manager.db.models import Decision, RoadmapTask, Team

class BaseContextFilter(ABC):
    """Abstract base class representing a filter stage in the Pipe-and-Filter architecture.
    
    Each filter operates on the shared state dictionary, adds/refines context elements,
    and returns the updated context dictionary.
    """
    @abstractmethod
    def process(self, context: Dict[str, Any], workspace: Path) -> Dict[str, Any]:
        pass

class TeamsFilter(BaseContextFilter):
    """Filter that extracts and formats active team personas."""
    def process(self, context: Dict[str, Any], workspace: Path) -> Dict[str, Any]:
        session = db_manager.get_session(workspace)
        try:
            teams = session.query(Team).all()
            if teams:
                lines = ["### Active Specialist Teams"]
                for t in teams:
                    lines.append(f"- Team {t.id} ({t.name}): {t.paradigm_specialty}")
                context["teams_context"] = "\n".join(lines)
        finally:
            session.close()
        return context

class DecisionsFilter(BaseContextFilter):
    """Filter that extracts and compacts historical ratified decisions."""
    def __init__(self, limit: int = 5):
        self.limit = limit

    def process(self, context: Dict[str, Any], workspace: Path) -> Dict[str, Any]:
        session = db_manager.get_session(workspace)
        try:
            # Query recent decisions ordered by timestamp/ID descending
            decisions = session.query(Decision).order_by(Decision.id.desc()).limit(self.limit).all()
            if decisions:
                lines = ["### Recent Ratified Decisions"]
                for d in reversed(decisions):
                    lines.append(f"- **{d.id}**: {d.topic} (Decision: {d.decision})")
                context["decisions_context"] = "\n".join(lines)
        finally:
            session.close()
        return context

class RoadmapFilter(BaseContextFilter):
    """Filter that extracts and summarizes current roadmap statuses."""
    def process(self, context: Dict[str, Any], workspace: Path) -> Dict[str, Any]:
        session = db_manager.get_session(workspace)
        try:
            tasks = session.query(RoadmapTask).all()
            if tasks:
                lines = ["### Roadmap Status Summary"]
                done_count = sum(1 for t in tasks if t.status == "DONE")
                total_count = len(tasks)
                percent = int((done_count / total_count) * 100) if total_count > 0 else 0
                lines.append(f"Overall Progress: {percent}% ({done_count}/{total_count} tasks completed)")
                
                # List open/non-done tasks
                open_tasks = [t for t in tasks if t.status not in ("DONE", "DEFERRED")]
                if open_tasks:
                    lines.append("Open Tasks:")
                    for t in open_tasks[:5]:
                        lines.append(f"  - [{t.status}] {t.id}: {t.task}")
                    if len(open_tasks) > 5:
                        lines.append(f"  - ... and {len(open_tasks) - 5} more open tasks.")
                context["roadmap_context"] = "\n".join(lines)
        finally:
            session.close()
        return context

class ContextPipeline:
    """Orchestrates the Pipe-and-Filter execution context collection."""
    def __init__(self, filters: List[BaseContextFilter] = None):
        self.filters = filters or []

    def add_filter(self, context_filter: BaseContextFilter):
        self.filters.append(context_filter)

    def execute(self, workspace: Path) -> str:
        context: Dict[str, Any] = {}
        for f in self.filters:
            context = f.process(context, workspace)
        
        # Combine all parts into a clean unified markdown block
        blocks = []
        if "teams_context" in context:
            blocks.append(context["teams_context"])
        if "decisions_context" in context:
            blocks.append(context["decisions_context"])
        if "roadmap_context" in context:
            blocks.append(context["roadmap_context"])
            
        return "\n\n".join(blocks)
