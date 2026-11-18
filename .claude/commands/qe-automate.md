---
description: QE phase 4 — write Robot Framework tests (data-testid locators) for the Zephyr test cases
argument-hint: <JIRA-KEY> [--fix] [--allow-fallback]
---

# qe-automate — run ONE phase of the QE flow (phase `automation`, agent `robot-automation`)

Arguments: `$ARGUMENTS` (first token = Jira key; `--force` skips the prerequisite check).

You are acting as the **QE Manager for a single phase**. Run only this phase, then stop.

## Steps
1. `python3 .claude/scripts/story_state.py init <KEY>` (idempotent). Show the user a one-line status for every phase.
2. **Prerequisite:** phase `test_cases` is `done` and every case in .stories/<KEY>/03-test-cases.json has a `zephyr_key`.
   If it is not met and `--force` was not given, stop. Tell the user which command to run first.
3. If phase `automation` is already `done`, ask the user: **Re-run** / **Cancel**.
4. `python3 .claude/scripts/story_state.py set-phase <KEY> automation in_progress`
5. Run the phase **exactly as described in section "### 4. automation → `robot-automation`"** of `.claude/skills/qe-manager/SKILL.md`. Read that
   section now. It covers the delegation to the `robot-automation` subagent, the gate and human-approval rules, and the
   state updates. Those rules apply in full here.
   With `--fix`: run the agent in **fix mode** on the `test_defect` items in 05-triage-report.md, and increment `triage_loops`. With `--allow-fallback`: tell the agent the user approved role/text locators for the reported locator gaps.
6. Set the final phase status with `story_state.py set-phase <KEY> automation done|blocked|failed|skipped --note "<one line>"`.
7. Report back in 15 lines or fewer: the result, any gate or approval outcome, the artifact paths, and the **next step: `/qe-triage <KEY>`**.
   Do not start the next phase.
