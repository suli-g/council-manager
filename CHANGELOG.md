# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.6] - 2026-06-21

### Added
- **UML Diagrams**: Restructured the `uml/` directory, updating the use case diagram and drafting detailed core class and sequence diagrams mapping all main workflows (Proposal Inception, Deliberation, Voting Loop, Ratification Wizard, and CSV Migration).

## [0.6.5] - 2026-06-20

### Fixed
- **Ollama Timeout**: Resolved concurrent model inference timeouts for local custom providers by introducing a configurable `llm_timeout` setting (defaulting to 300 seconds), preventing early client disconnections.

## [0.6.4] - 2026-06-20

### Added
- **Deliberation Progress Indicators**: Added a new roadmap task `P3-02c` to implement status indicators and duration tracking for each team during active deliberation in CLI/TUI viewports.
- **Structured Deliberations Schema**: Configured structured Pydantic response models (`DeliberationResponse`) for custom LLM providers to ensure clean parsing, reliable execution, and dynamic layout presentation.

## [0.6.3] - 2026-06-20

### Fixed
- **TUI Connection Failures**: Safely target the default main screen stack when toggle-disabling button controls in the dashboard background workers, preventing `NoMatches` exception crashes during LLM connectivity failures and ensuring error notifications are cleanly handled.

## [0.6.2] - 2026-06-20

### Added
- **TUI Proposal Creation Dialog**: Added a thread-safe, interactive proposal creation modal directly within the TUI dashboard, allowing user-driven proposal entries with custom titles/topics and choices.

## [0.6.1] - 2026-06-19

### Added
- **Interactive Terminal UI (TUI) Dashboard**: Built a stunning terminal-based dashboard UI (`P3-02a` and `P3-02b`) using Textual and Rich. It visualizes project decisions, voting records, and development roadmaps.
- **Interactive Dashboard Actions**: Added interactive CLI actions (creating proposals, ratifying proposals, and importing/exporting CSVs) directly inside the Textual TUI dashboard using custom inputs and dialog modals.
- **Unified Model Configuration**: Enforced a single unified LLM model across all voting agents, preventing reasoning unbalances, biases, and synchronization discrepancies in deliberations.

## [0.5.0] - 2026-06-19

### Added
- **FastAPI API Backend Server**: Introduced a lightweight, concurrent API server featuring endpoints for managing proposals, triggering asynchronous background deliberations and voting loops, and querying decisions, roadmaps, and audits.
- **Dynamic Database Routing & API Security**: Configured headers-based dynamic workspace database routing via `X-Workspace-Path` to isolate tenant data, and optional endpoint protection using `COUNCIL_API_KEY` verification through the `X-API-Key` header.
- **Logical Workspace Mapping & Auto-Resolution Fallbacks**: Added support for `X-Project-ID` header resolving project slugs, configurable workspace path registry (`workspace_mappings`), and automatic fallback routing to uvicorn's server directory when headers are omitted.
- **CLI Subcommand `start-server`**: Added `start-server` subcommand to launch the FastAPI backend server using Uvicorn.
- **Server Test Suite**: Implemented comprehensive unit tests in `tests/core/test_server.py` verifying header routing, auth security, endpoints, and asynchronous task execution.
- **Configurable Database Location**: Relocated SQLite database files outside of the project workspace by default (stored slugified under the user's home directory `~/.council_manager/databases`) to eliminate workspace clutter, avoid file locking during parallel/cloned runs, and prevent the need for Git ignore rules. Supported custom path overrides using the `COUNCIL_DATABASE_DIR` environment variable.

## [0.4.3] - 2026-06-18

### Added
- **Interactive Ratification Subcommand**: Added the new `proposal-ratify` CLI subcommand and `ratify_proposal` orchestrator workflow. The command lets users inspect detailed vote rationales, select/ratify a decision option (updating `decisions.csv` and `alternatives.csv`), complete a corresponding roadmap task (updating `roadmap.csv` and SQLite tables), and immediately start a new proposal & voting cycle if they specify a custom alternative.

## [0.4.2] - 2026-06-18


### Added
- **Multi-Stage Connectivity Probes**: Added upfront connection validation checking target server root endpoints (e.g. `http://localhost:11434`) and verifying specific model availability via Ollama's tags API before execution to avoid generic 404/500 errors.
- **Orchestrator Debug Event Logs**: Injected rich transition, voting cycles, and consensus verification logs under the `--debug` execution flag.
- **Truncated JSON Parsing Support**: Improved regex fallbacks inside the JSON parser to gracefully handle and extract data from truncated model completions lacking closing quotes/braces.

### Changed
- **Compact Vote CSV Export**: Excluded the detailed rationale text column from the exported individual vote CSV files (`.agents/votes/DEC-xxx.csv`) to keep Git-trackable files concise and focused. Rationales are still fully maintained inside the SQLite database.

## [0.4.1] - 2026-06-18


### Added
- **LLM Config Aliases**: Introduced support for `LLM_MODEL` and `OLLAMA_MODEL` environment variable aliases to specify the target LLM model name, eliminating configuration friction when using non-Gemini local models.

## [0.4.0] - 2026-06-17

### Added
- **Swappable LLM Providers**: Added support for custom, OpenAI-compatible LLM backends (such as local Ollama, vLLM, or alternative OpenAI-compliant providers) to run orchestrations entirely offline or bypass Gemini API rate-limiting and demand spikes.
- **Environment Configuration**: Integrated a `.env` loader schema with default configs, creating a new `.env.example` template and securing secrets from source control by updating `.gitignore`.
- **Custom Provider Tests**: Added synchronous and asynchronous mock unit tests checking custom API integrations to the test suite.

### Changed
- **Model Default**: Upgraded the default target Gemini model to `gemini-3.5-flash` across all settings, documentation, and unit test assertions.

---

## [0.3.0] - 2026-06-16

### Added
- **5-Cycle Blind Consensus Voting**: Core orchestrator feature allowing up to 5 cycles of weighted voting with automated feedback loops between rounds.
- **Physical Tenant Isolation**: Routed database connections to workspace-specific local SQLite databases (`.agents/governance.db`) using physical database file separation.
- **Bi-directional Roadmap Sync**: Implemented database models and CLI tools to synchronize active development roadmap status between flat CSV indices and SQLite tables.
