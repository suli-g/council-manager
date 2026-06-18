# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
