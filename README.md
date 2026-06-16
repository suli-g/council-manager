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
