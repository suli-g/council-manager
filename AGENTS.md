# Project Governance & Workflow

This file provides the meta-framework for how AI agents and LLMs must operate within this repository. It prioritizes dynamic configuration over hard-coded rules to ensure the project can scale its governance and team structure.

## Dynamic Source-of-Truth
Never assume the state of the project or its team structure. Always consult these live CSV indices before proposing or executing changes. 

**Format Standard:** All CSV files in this repository MUST use semi-colons (`;`) as delimiters to ensure compatibility with text fields containing commas.

*   **Teams & Roles (`docs/.agents/teams.csv`):** Defines the current team makeup, paradigm specialties, and voting weights.
*   **Ratified Decisions (`docs/.agents/decisions.csv`):** The immutable log of all technical and architectural choices made by the project teams.
*   **Voting Records (`docs/.agents/votes_manifest.csv`):** The central index of all formal paradigm-weighted votes, pointing to detailed records in `docs/.agents/votes/`.
*   **Alternatives Evaluated (`docs/.agents/alternatives.csv`):** Context on why certain paths were rejected, preserving the "design space" for future reference.
*   **Development Roadmap (`docs/.agents/roadmap.csv`):** The authoritative list of tasks, their priorities, and current implementation status.
*   **Audit Logs (`docs/.agents/audits.csv`):** Historical record of project alignment and quality assessments.
*   **Audit Resolutions (`docs/.agents/audit_decisions.csv`):** Relational mapping between audit findings and the architectural decisions that resolve them.

## Multi-Team, Multi-Tier Governance
The project operates under a decentralized, paradigm-weighted governance model.

1.  **Perspective Gathering:** Before any significant change, identify which teams in `teams.csv` are affected by or have expertise in the domain.
2.  **Tiered Evaluation:** 
    *   Any request starting with **PROPOSAL:** triggers a formal **interactive** vote.
    *   Every proposal must include at least **two alternatives** (including the Contrarian view).
    *   **Human Oversight:** Votes must NEVER be simulated or handled autonomously by an agent. The agent must present the alternatives and team perspectives to the human user for explicit validation and selection. Human overseer decisions should only be documented in the vote record if they contradict all team-proposed options.
3.  **Conflict Resolution:** If paradigms disagree, the decision is resolved through the multi-team voting system defined by the current weights in `teams.csv`. The **Contrarians (Team G)** provide critical friction to prevent groupthink.

## Mandatory AI Workflow
Any AI agent (including yourself) must follow these procedural mandates:

### 0. Mandatory Deliberation
*   **The PROPOSAL: Halt:** When a message starts with **PROPOSAL:**, you MUST NOT execute any state-changing tools (e.g., `write_file`, `replace`, `run_shell_command`) until a formal interactive vote has been conducted and documented in `votes_manifest.csv`.
*   **Interactive Decision Making:** You must use the `ask_user` tool to present paradigm perspectives to the user. You are forbidden from simulating the final outcome of a vote without real-time human interaction.

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

## Protocol Breach & Alignment
If an agent (AI or human) deviates from these principles (e.g., by executing changes without a vote):
1.  **Immediate Halt:** Stop all current execution.
2.  **Audit & Rollback:** Analyze the deviation and revert any unsanctioned changes if necessary.
3.  **Formal Re-Alignment:** Re-document the current state and return to the proper deliberation phase for the original proposal.

