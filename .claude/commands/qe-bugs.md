---
description: QE phase 6 — draft bugs for product defects; file each in Jira only after your approval
argument-hint: <JIRA-KEY> 
---

# qe-bugs — run ONE phase of the QE flow (phase `bugs`, agent `bug`)

Arguments: `$ARGUMENTS` (first token = Jira key; `--force` skips the prerequisite check).

You are acting as the **QE Manager for a single phase**. Run only this phase, then stop.

## Steps
1. `python3 .claude/scripts/story_state.py init <KEY>` (idempotent). Show the user a one-line status for every phase.
2. **Prerequisite:** phase `triage` is `done`. If 05-results.json has no `product_defect`, set this phase to `skipped` and stop.
   If it is not met and `--force` was not given, stop. Tell the user which command to run first.
3. If phase `bugs` is already `done`, ask the user: **Re-run** / **Cancel**.
4. `python3 .claude/scripts/story_state.py set-phase <KEY> bugs in_progress`
5. Run the phase **exactly as described in section "### 6. bugs → `bug` — HUMAN IN THE LOOP (mandatory)"** of `.claude/skills/qe-manager/SKILL.md`. Read that
   section now. It covers the delegation to the `bug` subagent, the gate and human-approval rules, and the
   state updates. Those rules apply in full here.

6. Set the final phase status with `story_state.py set-phase <KEY> bugs done|blocked|failed|skipped --note "<one line>"`.
7. Report back in 15 lines or fewer: the result, any gate or approval outcome, the artifact paths, and the **next step: `/qe-pr <KEY>`**.
   Do not start the next phase.
