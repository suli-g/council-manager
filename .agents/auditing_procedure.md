# Council Manager Auditing Procedure

This document defines the formal quality assurance and alignment verification procedure for the **Council Manager** project.

---

## 1. Immutable Audit Ledger
*   All audit entries logged in [audits.csv](file:///B:/projects/council_manager/.agents/audits.csv) are **immutable and append-only**.
*   Logged audits must **never** be edited, deleted, or retroactively modified in the CSV file once they have been committed to git.

---

## 2. Corrective Re-Auditing
If an audit score is later found to be incorrect, if process deviations are identified, or if a bug is discovered after the audit:
1.  **Do not edit the original audit row.**
2.  **Append a new re-audit entry** to `audits.csv` using a new timestamp.
3.  The summary of the new entry must explicitly state:
    *   The target of the re-audit (e.g., `Re-evaluation of Phase 1`).
    *   A reference back to the original audit ID (e.g., `Corrects AUDIT-012`).
    *   The corrected alignment score.
    *   The detailed findings (e.g., process omissions, bugs) that necessitated the correction.

---

## 3. Auditing Criteria
Every audit must assess three core pillars:

| Pillar | Focus | Target |
|---|---|---|
| **Functional Quality** | Verification | Code compiles, passes strict typing (ruff/mypy), and unit/integration tests cover edge cases (minimum 90% coverage target). |
| **Governance Compliance** | Alignment | Checks that the solution adheres strictly to all active architectural decisions (`DEC-001` through `DEC-xyz`). |
| **Process Checkpoints** | Collaboration | Ensures that major changes were voted on (`PROPOSAL:` protocol), and that implementation did not proceed as an unchecked batch without user feedback. |

---

## 4. Audit Frequency
*   Audits must occur at the end of **every granular task** listed in the roadmap.
*   Moving to a subsequent task is prohibited until a successful audit log has been committed.
