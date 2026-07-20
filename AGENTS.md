# Project Governance & Workflow

This file provides the meta-framework for how AI agents and LLMs must operate within this repository. It prioritizes dynamic configuration over hard-coded rules to ensure the project can scale its governance and team structure.

## Dynamic Source-of-Truth (CLI Encapsulation — CRITICAL)

**IMPORTANT: You MUST NOT manually navigate, list, or read files inside `.agents/` directly** (e.g., do not use `ListDir`, `Read`, or similar tools on `roadmap.csv`, `teams.csv`, `decisions.csv`, `alternatives.csv`, or the `votes/` folder). All governance data is managed through a SQLite database and must be accessed exclusively via the official `council-manager` CLI commands:

*   **To check the roadmap:** `uv run council-manager show-roadmap`
*   **To check registered teams:** `uv run council-manager show-teams`
*   **To check ratified decisions:** `uv run council-manager show-decisions`
*   **To check audit logs:** `uv run council-manager show-audits`
*   **To create a proposal:** `uv run council-manager proposal-create "..." -w <workspace>`
*   **To run deliberation:** `uv run council-manager deliberate -w <workspace>`
*   **To run voting:** `uv run council-manager vote -w <workspace>`
*   **To update roadmap tasks:** `uv run council-manager roadmap-update -w <workspace>` (add/update versioned tasks)
*   **To gather token-optimized context:** `uv run council-manager get-context -w <workspace>` (get compacted workspace context)

Direct file reads bypass the SQLite database cache and ORM schema boundaries, leading to stale or out-of-sync state.

**Format Standard:** All CSV files in this repository use semi-colons (`;`) as delimiters.

## Multi-Team, Multi-Tier Governance
The project operates under a decentralized, paradigm-weighted governance model.

1.  **Perspective Gathering:** Before any significant change, identify which teams are affected. Use `uv run council-manager show-teams` to see the current team roster.
2.  **Tiered Evaluation:** 
    *   Any request starting with **PROPOSAL:** triggers a formal **interactive** vote.
    *   Every proposal must include at least **two alternatives** (including the Contrarian view).
    *   **Human Oversight:** Votes must NEVER be simulated or handled autonomously by an agent. The agent must present the alternatives and team perspectives to the human user for explicit validation and selection. Human overseer decisions should only be documented in the vote record if they contradict all team-proposed options.
    *   Any request starting with **QUERY:** triggers a lightweight, non-voting team deliberation flow. The agent will concurrently query all active teams for their immediate rationales and perspectives on how the queried item affects the project, presenting them to the user. This does not involve any voting or formal ratification, and query results are not written to the static decisions or alternatives CSV files to prevent documentation rot.
3.  **Conflict Resolution:** If paradigms disagree, the decision is resolved through the multi-team voting system. The **Contrarians (Team G)** provide critical friction to prevent groupthink.

## Mandatory AI Workflow
Any AI agent (including yourself) must follow these procedural mandates:

### 0. Mandatory Deliberation
*   **The PROPOSAL: Halt:** When a message starts with **PROPOSAL:**, you MUST NOT execute any state-changing tools (e.g., `write_file`, `replace`, `run_shell_command`) until a formal interactive vote has been conducted and documented in `votes_manifest.csv`.
*   **Interactive Decision Making:** You must use the `ask_question` tool to present paradigm perspectives to the user. You are forbidden from simulating the final outcome of a vote without real-time human interaction.
*   **Tool Delegation (Critical):** Do NOT simulate deliberations or voting outcomes yourself. You MUST run all deliberations and votes via `uv run council-manager deliberate` and `uv run council-manager vote`.

### 1. Research & Alignment
*   Run `uv run council-manager get-context` (or individual queries like `show-decisions` and `show-roadmap`) to check project state and existing constraints. Use `get-context` to retrieve token-optimized context blocks instead of loading raw tables.
*   Do NOT read `decisions.csv`, `roadmap.csv`, or any other `.agents/` file directly.

### 2. Execution & Documentation
*   **Ratification:** After a strategy is agreed upon, update `decisions.csv` and `alternatives.csv` to reflect the new state (these CSVs are the append-only log; the SQLite DB is the canonical live state).
*   **Roadmap Maintenance:** Use `uv run council-manager roadmap-update` to add or update versioned roadmap tasks. Do NOT edit `roadmap.csv` directly — the command syncs both SQLite and CSV automatically.
*   **Scalability:** Do not hard-code team counts, tier counts, or specific paradigm names. Use `uv run council-manager show-teams` to read team structure dynamically.

### 3. Sub-Agent/Teammate Integration
*   When spawning sub-agents or collaborating with other LLMs, ensure they are first directed to this file and the workspace skill at `.agents/skills/council-manager/SKILL.md`.
*   Sub-agents must read both this file AND the skill before taking any action.

## Protocol Breach & Alignment
If an agent (AI or human) deviates from these principles (e.g., by reading CSV files directly or executing changes without a vote):
1.  **Immediate Halt:** Stop all current execution.
2.  **Audit & Rollback:** Analyze the deviation and revert any unsanctioned changes if necessary.
3.  **Formal Re-Alignment:** Re-document the current state and return to the proper deliberation phase for the original proposal.
