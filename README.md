# Council Manager

A Python-based, multi-team AI project governance orchestrator. Council Manager enables collaborative decision-making, blind voting, and structured project audits across multiple isolated workspaces.

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
3.  **Proposal Creation** (with optional auto-inception):
    ```bash
    uv run council-manager proposal-create "Detailed description here" -w <workspace-dir>
    ```
4.  **Orchestrate Deliberations & Votes**:
    ```bash
    uv run council-manager deliberate -w <workspace-dir> --proposal-id <id>
    uv run council-manager vote -w <workspace-dir> --proposal-id <id> --max-cycles 5
    ```
5.  **Status & Log Inspection**:
    ```bash
    uv run council-manager list -w <workspace-dir>
    uv run council-manager show -w <workspace-dir> --proposal-id <id>
    uv run council-manager show-decisions -w <workspace-dir>
    uv run council-manager show-roadmap -w <workspace-dir>
    uv run council-manager show-audits -w <workspace-dir>
    ```

