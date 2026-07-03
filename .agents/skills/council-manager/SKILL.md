---
name: council-manager
description: "Follows the multi-team, multi-tier governance model for this project. Use when the user submits a PROPOSAL: or QUERY: or when performing any development work in this workspace."
---

# Council Manager Governance Skill

You are operating in a workspace governed by the `council_manager` system. You must strictly adhere to the following rules:

## 1. Dynamic Source-of-Truth
Never assume the state of the project or its team structure. Always consult these live CSV indices before proposing or executing changes:
*   **Teams & Roles (`.agents/teams.csv`):** Defines the current team makeup, paradigm specialties, and voting weights.
*   **Ratified Decisions (`.agents/decisions.csv`):** The immutable log of all technical and architectural choices made by the project teams.
*   **Voting Records (`.agents/votes_manifest.csv`):** The central index of all formal paradigm-weighted votes, pointing to detailed records in `.agents/votes/`.
*   **Alternatives Evaluated (`.agents/alternatives.csv`):** Context on why certain paths were rejected, preserving the "design space" for future reference.
*   **Development Roadmap (`.agents/roadmap.csv`):** The authoritative list of tasks, their priorities, and current implementation status.
*   **Audit Logs (`.agents/audits.csv`):** Historical record of project alignment and quality assessments.
*   **Audit Resolutions (`.agents/audit_decisions.csv`):** Relational mapping between audit findings and the architectural decisions that resolve them.

All CSV files in this repository MUST use semi-colons (`;`) as delimiters.

## 2. Multi-Team, Multi-Tier Governance
The project operates under a decentralized, paradigm-weighted governance model.
1.  **Perspective Gathering:** Before any significant change, identify which teams in `teams.csv` are affected by or have expertise in the domain.
2.  **Tiered Evaluation:** 
    *   Any request starting with **PROPOSAL:** triggers a formal **interactive** vote.
    *   Every proposal must include at least **two alternatives** (including the Contrarian view).
    *   **Human Oversight:** Votes must NEVER be simulated or handled autonomously by an agent. The agent must present the alternatives and team perspectives to the human user for explicit validation and selection. Human overseer decisions should only be documented in the vote record if they contradict all team-proposed options.
    *   Any request starting with **QUERY:** triggers a lightweight, non-voting team deliberation flow. The agent will concurrently query all active teams for their immediate rationales and perspectives on how the queried item affects the project, presenting them to the user. This does not involve any voting or formal ratification, and query results are not written to the static decisions or alternatives CSV files to prevent documentation rot.
3.  **Conflict Resolution:** If paradigms disagree, the decision is resolved through the multi-team voting system defined by the current weights in `teams.csv`. The **Contrarians (Team G)** provide critical friction to prevent groupthink.

## 3. Mandatory AI Workflow
Any AI agent (including yourself) must follow these procedural mandates:

### 0. Mandatory Deliberation
*   **The PROPOSAL: Halt:** When a message starts with **PROPOSAL:**, you MUST NOT execute any state-changing tools (e.g., `write_to_file`, `replace_file_content`, `run_command`) until a formal interactive vote has been conducted and documented in `votes_manifest.csv`.
*   **Interactive Decision Making:** You must use the `ask_question` tool to present paradigm perspectives to the user. You are forbidden from simulating the final outcome of a vote without real-time human interaction.
*   **Tool Delegation (Critical):** Do NOT simulate deliberations or voting outcomes yourself within your model context. You MUST run all deliberations and votes by executing the official CLI commands `uv run council-manager deliberate` and `uv run council-manager vote`. This ensures the deliberations use the correct council-specific LLM configuration (such as Ollama or local settings) defined for the project, even if you are running on a different model (like Gemini).

### 1. Research & Alignment
*   Search `decisions.csv` for any existing rulings that constrain your task.
*   Consult `alternatives.csv` to avoid re-proposing previously rejected strategies.
*   Review `roadmap.csv` to ensure your work aligns with the current phase's priorities.

### 2. Execution & Documentation
*   **Ratification:** After a strategy is agreed upon, you must update `decisions.csv` and `alternatives.csv` to reflect the new state.
*   **Roadmap Maintenance:** Update the status of tasks in `roadmap.csv` (and `README.md` if applicable) as you progress.
*   **Scalability:** Do not hard-code team counts, tier counts, or specific paradigm names into the codebase or memory files. Reference `teams.csv` dynamically.

### 3. Sub-Agent/Teammate Integration
*   When spawning sub-agents or collaborating with other LLMs, ensure they are first directed to this file.
*   The `.agents/` directory is the "nervous system" of the project; any teammate must be able to autonomously read its state to orient themselves without human intervention.

## 4. Protocol Breach & Alignment
If an agent (AI or human) deviates from these principles (e.g., by executing changes without a vote):
1.  **Immediate Halt:** Stop all current execution.
2.  **Audit & Rollback:** Analyze the deviation and revert any unsanctioned changes if necessary.
3.  **Formal Re-Alignment:** Re-document the current state and return to the proper deliberation phase for the original proposal.
