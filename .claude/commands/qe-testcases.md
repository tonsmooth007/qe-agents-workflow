---
description: QE phase 3 — design test cases, have you review them, and create them in Zephyr Scale only after your approval
argument-hint: <JIRA-KEY> 
---

# qe-testcases — run ONE phase of the QE flow (phase `test_cases`, agent `zephyr-test-case`)

Arguments: `$ARGUMENTS` (first token = Jira key; `--force` skips the prerequisite check).

You are acting as the **QE Manager for a single phase**. Run only this phase, then stop.

## Steps
1. `python3 .claude/scripts/story_state.py init <KEY>` (idempotent). Show the user a one-line status for every phase.
2. **Prerequisite:** phase `traceability` is `done` AND the gate is either `passed: true` or has a recorded `override` (check `gates.traceability` in state.json).
   If it is not met and `--force` was not given, stop. Tell the user which command to run first.
3. If phase `test_cases` is already `done`, ask the user: **Re-run** / **Cancel**.
4. `python3 .claude/scripts/story_state.py set-phase <KEY> test_cases in_progress`
5. Run the phase **exactly as described in section "### 3. test_cases → `zephyr-test-case` — HUMAN IN THE LOOP (mandatory)"** of `.claude/skills/qe-manager/SKILL.md`. Read that
   section now. It covers the delegation to the `zephyr-test-case` subagent, the gate and human-approval rules, and the
   state updates. Those rules apply in full here.

6. Set the final phase status with `story_state.py set-phase <KEY> test_cases done|blocked|failed|skipped --note "<one line>"`.
7. Report back in 15 lines or fewer: the result, any gate or approval outcome, the artifact paths, and the **next step: `/qe-automate <KEY>`**.
   Do not start the next phase.
