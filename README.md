# Council Manager

A Python-based, multi-team AI project governance orchestrator. Council Manager enables collaborative decision-making, blind voting, and structured project audits across multiple isolated workspaces.

See the [CHANGELOG.md](file:///B:/projects/council_manager/CHANGELOG.md) for version release details.

---

## Architecture Overview

The system is designed around a decoupled **Ports & Adapters (Hexagonal)** architecture, keeping configuration, database engines, orchestration, and user interfaces separated by explicit input/output boundaries.

*   **Subsystem & Component Boundaries**: Detailed in [use_case_planning.md](file:///C:/Users/sulig/.gemini/antigravity-cli/brain/3ee7a652-e3b9-4285-aa73-cc8ce7ebaa96/use_case_planning.md).
*   **Use Cases Diagram**: [use_cases.puml](file:///B:/projects/council_manager/uml/use_cases.puml).
*   **Component Diagram**: [components.puml](file:///B:/projects/council_manager/uml/components.puml).

---

## Installation & Setup

Ensure you have [uv](https://github.com/astral-sh/uv) installed in your environment.

1.  **Clone the workspace** and navigate to the project root:
    ```bash
    cd B:/projects/council_manager
    ```
2.  **Install dependencies** and create the virtual environment:
    ```bash
    uv sync
    ```
3.  **Configure Environment Variables**:
    Create a `.env` file in the project root (you can copy the template from `.env.example`):
    ```bash
    cp .env.example .env
    ```
    Open `.env` and set your `GEMINI_API_KEY`:
    ```env
    GEMINI_API_KEY=your-actual-api-key
    ```
    *(Optional)* You can also change the target model by setting `LLM_MODEL`, `OLLAMA_MODEL`, or `GEMINI_MODEL`. If you experience high demand (503) or rate limits on the default model, you can try setting it to a different supported model (e.g. `gemini-3.5-pro` or `gemini-3.5-flash`).

    *(Optional)* **Swappable LLM Providers (Local Ollama / OpenAI)**:
    To bypass rate limits or run offline, configure a custom provider:
    ```env
    LLM_PROVIDER=ollama
    # Default URL is http://localhost:11434/v1
    LLM_API_BASE=http://localhost:11434/v1
    # Swapped model name matching your local library (LLM_MODEL or OLLAMA_MODEL)
    LLM_MODEL=llama3
    ```

---

## Running Tests

Verify the database models, session routing, and migration logic by executing the test suite:

```bash
uv run pytest
```

---

## Manual Testing & Developer Usage

### 1. Database Session Management
The database layer isolates data per project by creating a dedicated `governance.db` SQLite file under the project's `.agents/` folder.

To retrieve a database session for a specific project directory:
```python
from pathlib import Path
from council_manager.db import db_manager, Project

# Resolve the target project directory
workspace_path = Path("B:/projects/council_manager")

# Retrieve an isolated SQLAlchemy session
session = db_manager.get_session(workspace_path)
try:
    # Query or insert data
    project = session.query(Project).filter_by(id="council_manager").first()
    print(f"Project Name: {project.name if project else 'Not Found'}")
finally:
    session.close()
    
    # Release file locks (critical on Windows when cleaning up database resources)
    db_manager.close_all()
```

### 2. Running CSV Import/Export Migration
To bridge flat CSV governance logs into the SQLite database, or dump tables back to CSVs:

```python
from pathlib import Path
from council_manager.db import import_csv_to_db, export_db_to_csv

workspace_path = Path("B:/projects/council_manager")

# Import all CSVs (.agents/*.csv) into the new SQLite database
import_csv_to_db(workspace_path, "council_manager")

# Export database tables back into semi-colon CSVs (.agents/*.csv)
export_db_to_csv(workspace_path, "council_manager")
```

### 3. Orchestration & 5-Cycle Voting

The `CouncilOrchestrator` manages the lifecycle of proposals through deliberation and consensus voting.

#### A. Initializing a Proposal
Initialize a proposal and persist it within the isolated SQLite database:

```python
from pathlib import Path
from council_manager.core.orchestrator import council_orchestrator

workspace = Path("B:/projects/council_manager")

proposal = council_orchestrator.create_proposal(
    workspace_dir=workspace,
    project_id="council_manager",
    proposal_id="DEC-072",
    topic="Voting Subsystem Strategy",
    description="Adopt 5-cycle autonomous AI voting with final human ratification.",
    options=[
        "Alt 1: Pre-Voted and Fallback Override",
        "Alt 2: Interactive Round-by-Round",
        "Alt 3: Autonomous AI with User Ratification"
    ]
)
print(f"Proposal '{proposal.id}' created. Status: {proposal.status}")
```

#### B. Asynchronous Deliberation (Phase 1)
Run Phase 1 to collect engineering paradigm rationales from all active teams concurrently:

```python
import asyncio
from pathlib import Path
from council_manager.core.orchestrator import council_orchestrator

workspace = Path("B:/projects/council_manager")

async def run_phase1():
    proposal = await council_orchestrator.run_deliberation(workspace, "DEC-072")
    print(f"Deliberation complete. Status: {proposal.status}")
    print(f"Collected rationales: {proposal.rationales}")

asyncio.run(run_phase1())
```

#### C. Asynchronous 5-Cycle Voting Engine (Phase 2)
Conduct up to 5 cycles of consensus voting. In each cycle:
1.  **Blind Voting**: Teams cast secret, weighted votes concurrently using the official `google-genai` SDK.
2.  **Consensus Verification**: The engine tallies votes. If any option achieves **$\ge 70\%$** of the active weight, consensus is met and the loop terminates early.
3.  **Debate Feedback**: If no consensus is met, the engine feeds previous cycle vote distributions and justifications back to the team agents as context for the next cycle.
4.  **Fallback**: If no consensus is reached after 5 cycles, the engine falls back to selecting the option with the highest weighted majority.
5.  **User Ratification**: The final proposal is set to `RATIFICATION_PENDING` and awaits Approve/Reject signature from the user.

```python
import asyncio
from pathlib import Path
from council_manager.core.orchestrator import council_orchestrator

workspace = Path("B:/projects/council_manager")

async def run_phase2():
    proposal = await council_orchestrator.run_voting(workspace, "DEC-072", max_cycles=5)
    print(f"Voting complete. Final Status: {proposal.status}")
    print(f"Consensus Votes: {proposal.votes}")

asyncio.run(run_phase2())
```

---

## Command Line Interface (CLI) Usage

The system exposes a comprehensive CLI for managing projects, importing/exporting database states, and running deliberations/votes externally.

You can run the CLI tool using `uv run council-manager`:

```bash
uv run council-manager --help
```

### Key CLI Commands

1.  **Project Initialization**:
    ```bash
    uv run council-manager init-project --path <dir-path> --project-id <proj-id>
    ```
2.  **CSV Import/Export Migrations**:
    ```bash
    uv run council-manager import -w <workspace-dir> -p <project-id>
    uv run council-manager export -w <workspace-dir> -p <project-id>
    ```
3.  **Proposal Creation** (with optional auto-inception, auto-deliberation, or auto-voting):
    ```bash
    # Create proposal (returns dynamic DEC-xxx ID)
    uv run council-manager proposal-create "Detailed description here" -w <workspace-dir>

    # Create and automatically trigger Phase 1 Deliberation immediately
    uv run council-manager proposal-create "Detailed description here" -w <workspace-dir> --deliberate

    # Create and automatically trigger both Deliberation and Phase 2 Consensus Voting
    uv run council-manager proposal-create "Detailed description here" -w <workspace-dir> --vote --max-cycles 5
    ```
4.  **Orchestrate Deliberations & Votes** (omitting `--proposal-id` automatically targets the latest created proposal):
    ```bash
    # Run Phase 1 Deliberation
    uv run council-manager deliberate -w <workspace-dir> --proposal-id <id>
    uv run council-manager deliberate -w <workspace-dir>  # Targets the latest proposal

    # Run Phase 2 Consensus Voting
    uv run council-manager vote -w <workspace-dir> --proposal-id <id> --max-cycles 5
    uv run council-manager vote -w <workspace-dir> --max-cycles 5  # Targets the latest proposal
    ```
5.  **Status & Log Inspection** (omitting `--proposal-id` targets the latest proposal):
    ```bash
    uv run council-manager list -w <workspace-dir>
    uv run council-manager show -w <workspace-dir> --proposal-id <id>
    uv run council-manager show -w <workspace-dir>  # Shows details of the latest proposal
    uv run council-manager show-teams -w <workspace-dir>
    uv run council-manager show-decisions -w <workspace-dir>
    uv run council-manager show-roadmap -w <workspace-dir>
    uv run council-manager show-audits -w <workspace-dir>
    ```
6.  **Individual Team Deliberation & Voting** (omitting `--proposal-id` targets the latest proposal):
    ```bash
    uv run council-manager team-deliberate -w <workspace-dir> --team-id <team-id> --proposal-id <id>
    uv run council-manager team-deliberate -w <workspace-dir> --team-id <team-id>  # Targets latest proposal
    uv run council-manager team-vote -w <workspace-dir> --team-id <team-id> --proposal-id <id>
    uv run council-manager team-vote -w <workspace-dir> --team-id <team-id>  # Targets latest proposal
    ```
7.  **Starting the API Server**:
    ```bash
    uv run council-manager start-server --host 127.0.0.1 --port 8000 --reload
    ```

---

## FastAPI API Backend Server

The orchestrator includes a FastAPI-based backend server that supports dynamic multi-tenant database routing and optionally secured endpoints.

### Running the Server
You can launch the server via the CLI subcommand:
```bash
uv run council-manager start-server [--host <host>] [--port <port>] [--reload]
```

### Authorization & Security
Endpoints can be secured by setting the `COUNCIL_API_KEY` environment variable. When configured, all requests to the server (except `/health`) must include the API key in the `X-API-Key` header.

### Multi-Tenant Database Routing
The server dynamically routes database connections to isolated SQLite files based on the client workspace path or project slug. Requests can provide either the absolute path, a project slug, or omit headers to automatically resolve to the uvicorn process's working directory:
*   Header: `X-Project-ID` (e.g. `council_manager` or a mapped custom slug)
*   Header: `X-Workspace-Path` (e.g. `/absolute/path/to/workspace`)
*   If both headers are omitted, the server automatically resolves database connections to the server process's configured workspace directory (`settings.workspace_dir`).

Logical project-to-workspace path mappings can be registered via the `workspace_mappings` configuration setting (e.g. `COUNCIL_WORKSPACE_MAPPINGS='{"my_project": "B:/projects/my_project"}'`).

### Key Endpoints
*   `GET /health`: Health check verification (does not require auth or workspace headers).
*   `GET /proposals`: Retrieve a list of all proposals.
*   `GET /proposals/{proposal_id}`: Retrieve details for a specific proposal.
*   `POST /proposals`: Create a new proposal.
*   `POST /proposals/{proposal_id}/deliberate`: Queue Phase 1 Deliberation in the background (default `async_mode=true`) or run synchronously.
*   `POST /proposals/{proposal_id}/vote`: Queue Phase 2 Consensus Voting loop in the background (default `async_mode=true`) or run synchronously.
*   `GET /tasks/{task_id}/status`: Query execution status of a background task.
*   `GET /tasks/{task_id}/logs`: Retrieve log output content of a background task worker.
*   `GET /decisions`: Retrieve ratified decisions.
*   `GET /roadmap`: Retrieve project roadmap task statuses.
*   `GET /audits`: Retrieve history of quality alignment audits.
