from datetime import datetime, date, timezone
from typing import List, Dict, Any
from sqlalchemy import String, Integer, Float, DateTime, Date, ForeignKey, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    proposals: Mapped[List["Proposal"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    decisions: Mapped[List["Decision"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    audit_logs: Mapped[List["AuditLog"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    roadmap_tasks: Mapped[List["RoadmapTask"]] = relationship(back_populates="project", cascade="all, delete-orphan")



class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # e.g., 'A', 'B'
    name: Mapped[str] = mapped_column(String, nullable=False)
    vote_weight: Mapped[int] = mapped_column(Integer, default=10)
    paradigm_specialty: Mapped[str] = mapped_column(String, nullable=False)


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), nullable=False)
    topic: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    options: Mapped[List[str]] = mapped_column(JSON, nullable=False)  # List of string options
    status: Mapped[str] = mapped_column(String, default="DELIBERATION_PENDING")
    rationales: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)  # List of deliberation dicts
    votes: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)  # List of votes cast
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    project: Mapped["Project"] = relationship(back_populates="proposals")


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # e.g., 'DEC-001'
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, default=lambda: datetime.now(timezone.utc).date())
    topic: Mapped[str] = mapped_column(String, nullable=False)
    decision: Mapped[str] = mapped_column(String, nullable=False)
    rationale: Mapped[str] = mapped_column(String, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="decisions")
    alternatives: Mapped[List["Alternative"]] = relationship(back_populates="decision", cascade="all, delete-orphan")


class Alternative(Base):
    __tablename__ = "alternatives"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # e.g., 'ALT-001'
    decision_id: Mapped[str] = mapped_column(String, ForeignKey("decisions.id"), nullable=False)
    option: Mapped[str] = mapped_column(String, nullable=False)
    pros: Mapped[str] = mapped_column(String, nullable=False)
    cons: Mapped[str] = mapped_column(String, nullable=False)

    decision: Mapped["Decision"] = relationship(back_populates="alternatives")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # e.g., 'AUDIT-001'
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    summary: Mapped[str] = mapped_column(String, nullable=False)
    alignment_score: Mapped[float] = mapped_column(Float, nullable=False)
    auditor_team: Mapped[str] = mapped_column(String, default="F")

    project: Mapped["Project"] = relationship(back_populates="audit_logs")


class RoadmapTask(Base):
    __tablename__ = "roadmap_tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # e.g., 'P1-01'
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), primary_key=True)
    phase: Mapped[int] = mapped_column(Integer, nullable=False)
    task: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)  # 'TODO', 'DONE'
    notes: Mapped[str] = mapped_column(String, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="roadmap_tasks")


