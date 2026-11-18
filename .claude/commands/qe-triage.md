---
description: QE phase 5 — run the story's Robot tests, re-run failures, triage each failure and sync the results to Zephyr Scale
argument-hint: <JIRA-KEY> [--env <env>]
---

# qe-triage — run ONE phase of the QE flow (phase `triage`, agent `triage`)

Arguments: `$ARGUMENTS` (first token = Jira key; `--force` skips the prerequisite check).

You are acting as the **QE Manager for a single phase**. Run only this phase, then stop.

## Steps
1. `python3 .claude/scripts/story_state.py init <KEY>` (idempotent). Show the user a one-line status for every phase.
2. **Prerequisite:** phase `automation` is `done` (the dry-run passed and 04-automation.md exists).
   If it is not met and `--force` was not given, stop. Tell the user which command to run first.
3. If phase `triage` is already `done`, ask the user: **Re-run** / **Cancel**.
4. `python3 .claude/scripts/story_state.py set-phase <KEY> triage in_progress`
5. Run the phase **exactly as described in section "### 5. triage → `triage`"** of `.claude/skills/qe-manager/SKILL.md`. Read that
   section now. It covers the delegation to the `triage` subagent, the gate and human-approval rules, and the
   state updates. Those rules apply in full here.
   Pass `--env` to the agent. The results sync to Zephyr Scale is mandatory; check it as the skill section describes. Do NOT start the fix loop automatically. If there are `test_defect` failures, recommend `/qe-automate <KEY> --fix` and then `/qe-triage <KEY>` again (2 loops at most).
6. Set the final phase status with `story_state.py set-phase <KEY> triage done|blocked|failed|skipped --note "<one line>"`.
7. Report back in 15 lines or fewer: the result, any gate or approval outcome, the artifact paths, and the **next step: `/qe-automate <KEY> --fix` if there are test defects, `/qe-bugs <KEY>` if there are product defects, otherwise `/qe-pr <KEY>`**.
   Do not start the next phase.
