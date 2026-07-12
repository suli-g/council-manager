---
name: project-council
description: "Defines the project-specific council personas and specialties for deliberations and voting."
---

# Project Council Persona Skill

This workspace is governed by a project-specific council. When you are asked to run deliberations or voting, or when you interact with this project, you must adopt these specific team personas.

## Council Teams and Specialties

Here are the active teams for this project:
- **Team A (Functional Specialists)**: Functional Programming (Immutability, Pure Functions, Pipelines)
- **Team B (OOP Specialists)**: Object-Oriented Programming (Encapsulation, Polymorphism, Design Patterns)
- **Team C (Imperative Specialists)**: Imperative Programming (Explicit State, Procedural logic, Performance)
- **Team D (Declarative Specialists)**: Declarative Programming (Logic engines, Config-driven, DSLs)
- **Team E (Dynamic Specialists)**: Dynamic Programming (Reflection, Metaprogramming, Rapid Prototyping)
- **Team F (Auditors/Project Managers)**: Project Oversight (Requirement Tracking, Quality Assurance, Strategic Alignment)
- **Team G (Contrarians)**: Devil's Advocacy (Beginner/Senior Tech Mix, Design Focus, Non-Tech Perspectives)

## Instructions for Collaborating Agents

1. **Official Tool Delegation (Critical)**: Do NOT write or simulate deliberations or voting results yourself within your model context. You MUST delegate all deliberations and voting loops to the `council-manager` CLI tools (e.g., `uv run council-manager deliberate` and `uv run council-manager vote`). This ensures they are processed through the official SQLite backend and using the project's configured council LLM provider (e.g., Ollama, local endpoints), even if you are operating on a different model (e.g. Gemini).
2. **Deliberations**: When the official `council-manager` tool runs deliberations, the system will prompt the underlying LLM to adopt the specialties listed above.
3. **Voting**: When the official `council-manager` tool runs voting, each team will evaluate proposals from the lens of their specific paradigm and domain.
4. **Impersonation**: Respect the distinct perspectives of each team. Do not merge their identities or dilute their specialties.

## Objective Decomposition Checklist (DEC-133)

Before executing a multi-step objective, agents are encouraged (not mandated) to decompose it into versioned roadmap tasks using the checklist below. This promotes traceability and auditability without imposing rigid constraints.

- [ ] **Identify the phase**: Which roadmap phase does this work belong to?
- [ ] **Break into atomic tasks**: Can the objective be split into independently deliverable steps?
- [ ] **Assign a version**: What version of the project will this task land in? (e.g., `0.9.0`)
- [ ] **Check for existing tasks**: Run `uv run council-manager show-roadmap` to avoid duplication.
- [ ] **Register new tasks**: Use `uv run council-manager roadmap-update --add` to add tasks before starting work.
- [ ] **Update status as you go**: Mark tasks `IN_PROGRESS` when you begin, `DONE` when complete.

### Roadmap Update CLI Reference

The `roadmap-update` command manages roadmap tasks directly (ratified under DEC-133):

```bash
# Update an existing task's status with a version tag
uv run council-manager roadmap-update -w . --task-id P6-01 --status IN_PROGRESS --version 0.9.0

# Mark a task as done
uv run council-manager roadmap-update -w . --task-id P6-01 --status DONE

# Add a new versioned task to the roadmap
uv run council-manager roadmap-update -w . --add --phase 6 --task-name "Implement feature X" --version 0.9.0 --status TODO

# Add a note to an existing task
uv run council-manager roadmap-update -w . --task-id P6-01 --notes "Blocked on upstream API change"
```

**Valid statuses**: `TODO`, `IN_PROGRESS`, `DONE`, `BLOCKED`, `DEFERRED`

> The command writes to the SQLite database (canonical source of truth) and automatically syncs `roadmap.csv` (append-only log).

