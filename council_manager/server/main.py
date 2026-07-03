import sys
from pathlib import Path
from typing import Generator
from fastapi import FastAPI, Header, HTTPException, Depends, status, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session
from council_manager.config import settings
from council_manager.db import (
    db_manager,
    Proposal,
    BackgroundTask,
    Decision,
    Alternative,
    AuditLog,
    RoadmapTask,
    Project,
)

# Initialize FastAPI App with rich metadata
app = FastAPI(
    title="Council Manager API",
    description="Isolated multi-team governance orchestrator server supporting dynamic workspace database routing.",
    version="0.7.0",
)

# API Key Validation Dependency
def verify_api_key(x_api_key: str | None = Header(None, alias="X-API-Key")):
    """Ensure access is restricted if council_api_key is configured in settings."""
    if settings.council_api_key:
        if not x_api_key or x_api_key != settings.council_api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing X-API-Key credentials.",
            )

def resolve_workspace(identifier: str) -> Path:
    """Resolve a logical project ID/slug or workspace folder path to an absolute Path."""
    # 1. Check workspace mappings setting
    if settings.workspace_mappings and identifier in settings.workspace_mappings:
        mapped_path = Path(settings.workspace_mappings[identifier]).resolve()
        if mapped_path.exists() and mapped_path.is_dir():
            return mapped_path

    # 2. Fallback: if identifier matches folder name or default council_manager project ID
    workspace_dir = settings.workspace_dir.resolve()
    if identifier == workspace_dir.name or identifier == "council_manager":
        return workspace_dir

    # 3. Try resolving as direct workspace path
    p = Path(identifier).resolve()
    if p.exists() and p.is_dir():
        return p

    raise ValueError(f"Could not resolve workspace identifier '{identifier}' to a valid directory path.")

def get_workspace(
    x_workspace_path: str | None = Header(None, alias="X-Workspace-Path"),
    x_project_id: str | None = Header(None, alias="X-Project-ID"),
) -> Path:
    """Dynamically resolve target workspace path from headers or default to server working directory."""
    identifier = x_project_id or x_workspace_path
    if not identifier:
        return settings.workspace_dir.resolve()
    try:
        return resolve_workspace(identifier)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

# Dynamic DB Session Factory Dependency
def get_db(workspace: Path = Depends(get_workspace)) -> Generator[Session, None, None]:
    """Dynamically route the database connection using the resolved workspace Path."""
    session = db_manager.get_session(workspace)
    try:
        yield session
    finally:
        session.close()

# Request Pydantic Schemas
class ProposalCreate(BaseModel):
    project_id: str = "council_manager"
    description: str
    topic: str | None = None
    options: list[str] | None = None

# Connection Manager for WebSockets
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, workspace_path: str):
        await websocket.accept()
        self.active_connections.setdefault(workspace_path, []).append(websocket)

    async def disconnect(self, websocket: WebSocket, workspace_path: str):
        if workspace_path in self.active_connections:
            if websocket in self.active_connections[workspace_path]:
                self.active_connections[workspace_path].remove(websocket)
            if not self.active_connections[workspace_path]:
                del self.active_connections[workspace_path]

    async def broadcast(self, workspace_path: str, message: dict):
        connections = self.active_connections.get(workspace_path, [])
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

@app.websocket("/ws/workspace")
async def websocket_endpoint(
    websocket: WebSocket,
    path: str | None = None,
    project_id: str | None = None
):
    identifier = project_id or path
    try:
        if not identifier:
            workspace = settings.workspace_dir.resolve()
        else:
            workspace = resolve_workspace(identifier)
    except ValueError:
        await websocket.accept()
        await websocket.send_json({"error": "Invalid workspace path or project ID"})
        await websocket.close()
        return

    workspace_key = str(workspace.resolve().as_posix())
    await manager.connect(websocket, workspace_key)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await manager.disconnect(websocket, workspace_key)

@app.post("/tasks/{task_id}/events")
async def post_task_event(
    task_id: str,
    event: dict,
    workspace: Path = Depends(get_workspace),
    api_key_check: None = Depends(verify_api_key)
):
    workspace_key = str(workspace.resolve().as_posix())
    event["task_id"] = task_id
    await manager.broadcast(workspace_key, event)
    return {"status": "broadcasted"}


# --- Endpoints ---

@app.get("/health")
def health_check():
    """Simple health check verification endpoint."""
    return {"status": "healthy", "service": "council-manager-api", "version": "0.7.0"}

@app.get("/proposals")
def list_proposals(
    db: Session = Depends(get_db),
    api_key_check: None = Depends(verify_api_key)
):
    """Retrieve all proposals from the workspace database."""
    return db.query(Proposal).order_by(Proposal.created_at.desc()).all()

@app.get("/proposals/{proposal_id}")
def get_proposal(
    proposal_id: str,
    db: Session = Depends(get_db),
    api_key_check: None = Depends(verify_api_key)
):
    """Retrieve details for a specific proposal."""
    prop = db.query(Proposal).filter_by(id=proposal_id).first()
    if not prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proposal '{proposal_id}' not found.",
        )
    return prop

@app.post("/proposals", status_code=status.HTTP_201_CREATED)
def create_proposal(
    payload: ProposalCreate,
    workspace: Path = Depends(get_workspace),
    db: Session = Depends(get_db),
    api_key_check: None = Depends(verify_api_key)
):
    """Create a new proposal, running AI-powered topic & option inception if omitted."""
    
    # Auto-initialize Project if missing in DB
    proj = db.query(Project).filter_by(id=payload.project_id).first()
    if not proj:
        proj = Project(
            id=payload.project_id,
            name=payload.project_id.replace("_", " ").title()
        )
        db.add(proj)
        db.commit()

    from council_manager.core.orchestrator import council_orchestrator
    try:
        prop = council_orchestrator.create_proposal(
            workspace_dir=workspace,
            project_id=payload.project_id,
            description=payload.description,
            topic=payload.topic,
            options=payload.options
        )
        prop = db.query(Proposal).filter_by(id=prop.id).first()
        return prop
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create proposal: {e}"
        )

@app.post("/proposals/{proposal_id}/deliberate")
def deliberate_proposal(
    proposal_id: str,
    async_mode: bool = True,
    workspace: Path = Depends(get_workspace),
    db: Session = Depends(get_db),
    api_key_check: None = Depends(verify_api_key)
):
    """Trigger Phase 1 Deliberation for a proposal (defaults to async background run)."""
    prop = db.query(Proposal).filter_by(id=proposal_id).first()
    if not prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proposal '{proposal_id}' not found.",
        )

    if async_mode:
        from council_manager.cli import generate_task_id, spawn_background_task
        task_id = generate_task_id(db, prop.project_id)
        task = BackgroundTask(
            id=task_id,
            project_id=prop.project_id,
            task_type="DELIBERATION",
            proposal_id=proposal_id,
            status="PENDING"
        )
        db.add(task)
        db.commit()
        
        spawn_background_task(workspace, task_id)
        return {
            "task_id": task_id,
            "status": "PENDING",
            "message": "Deliberation queued in the background."
        }
    else:
        # Synchronous execution within request lifecycle
        import asyncio
        from council_manager.core.orchestrator import council_orchestrator
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                council_orchestrator.run_deliberation(workspace, proposal_id)
            )
            db.refresh(prop)
            return prop
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Deliberation failed: {e}"
            )
        finally:
            loop.close()

@app.post("/proposals/{proposal_id}/vote")
def vote_proposal(
    proposal_id: str,
    async_mode: bool = True,
    max_cycles: int = 5,
    workspace: Path = Depends(get_workspace),
    db: Session = Depends(get_db),
    api_key_check: None = Depends(verify_api_key)
):
    """Trigger Phase 2 Consensus Voting loop (defaults to async background run)."""
    prop = db.query(Proposal).filter_by(id=proposal_id).first()
    if not prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proposal '{proposal_id}' not found.",
        )

    if async_mode:
        from council_manager.cli import generate_task_id, spawn_background_task
        task_id = generate_task_id(db, prop.project_id)
        task = BackgroundTask(
            id=task_id,
            project_id=prop.project_id,
            task_type="VOTING",
            proposal_id=proposal_id,
            status="PENDING"
        )
        db.add(task)
        db.commit()
        
        spawn_background_task(workspace, task_id, max_cycles=max_cycles)
        return {
            "task_id": task_id,
            "status": "PENDING",
            "message": "Voting loop queued in the background."
        }
    else:
        # Synchronous execution within request lifecycle
        import asyncio
        from council_manager.core.orchestrator import council_orchestrator
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                council_orchestrator.run_voting(workspace, proposal_id, max_cycles=max_cycles)
            )
            db.refresh(prop)
            return prop
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Voting loop failed: {e}"
            )
        finally:
            loop.close()

@app.get("/tasks/{task_id}/status")
def get_task_status(
    task_id: str,
    db: Session = Depends(get_db),
    api_key_check: None = Depends(verify_api_key)
):
    """Query execution status and errors of a queued background task."""
    task = db.query(BackgroundTask).filter_by(id=task_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Background task '{task_id}' not found.",
        )
    return {
        "id": task.id,
        "task_type": task.task_type,
        "proposal_id": task.proposal_id,
        "status": task.status,
        "error_message": task.error_message,
        "created_at": task.created_at,
        "updated_at": task.updated_at
    }

@app.get("/tasks/{task_id}/logs")
def get_task_logs(
    task_id: str,
    workspace: Path = Depends(get_workspace),
    api_key_check: None = Depends(verify_api_key)
):
    """Retrieve execution log content generated by the worker process for a background task."""
    log_file = workspace / ".agents" / "logs" / f"{task_id}.log"
    if not log_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Log file for task '{task_id}' not found.",
        )
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            log_content = f.read()
        return {"task_id": task_id, "logs": log_content}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read logs: {e}",
        )

@app.get("/decisions")
def list_decisions(
    db: Session = Depends(get_db),
    api_key_check: None = Depends(verify_api_key)
):
    """Retrieve list of ratified decisions and corresponding alternatives."""
    decisions = db.query(Decision).all()
    result = []
    for d in decisions:
        result.append({
            "id": d.id,
            "date": d.date,
            "topic": d.topic,
            "decision": d.decision,
            "rationale": d.rationale,
            "alternatives": [
                {"id": a.id, "option": a.option, "pros": a.pros, "cons": a.cons}
                for a in d.alternatives
            ]
        })
    return result

@app.get("/roadmap")
def get_roadmap(
    db: Session = Depends(get_db),
    api_key_check: None = Depends(verify_api_key)
):
    """Retrieve lists of completed and upcoming development roadmap tasks."""
    tasks = db.query(RoadmapTask).order_by(RoadmapTask.phase, RoadmapTask.id).all()
    return tasks

@app.get("/audits")
def list_audits(
    db: Session = Depends(get_db),
    api_key_check: None = Depends(verify_api_key)
):
    """Retrieve history of quality alignment audits."""
    audits = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).all()
    return audits


# Mount static files folder and define index routes
static_path = Path(__file__).parent / "static"
static_path.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

@app.get("/")
@app.get("/dashboard")
def get_dashboard():
    """Serve the real-time HTML/CSS/JS dashboard interface."""
    index_file = static_path / "index.html"
    return FileResponse(str(index_file))
