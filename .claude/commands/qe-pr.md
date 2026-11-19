---
description: QE phase 7 — commit the tests and draft the GitLab MR; push and create it only after your approval
argument-hint: <JIRA-KEY> 
---

# qe-pr — run ONE phase of the QE flow (phase `pr`, agent `pull-request`)

Arguments: `$ARGUMENTS` (first token = Jira key; `--force` skips the prerequisite check).

You are acting as the **QE Manager for a single phase**. Run only this phase, then stop.

## Steps
1. `python3 .claude/scripts/story_state.py init <KEY>` (idempotent). Show the user a one-line status for every phase.
2. **Prerequisite:** phase `triage` is `done`, and phase `bugs` is `done` or `skipped`.
   **Exception, locator heal:** if state has `heal.status: applied` (from `/qe-heal <KEY>`), the prerequisite is
   met without the phases. Tell the agent it is a **locator-heal MR**.
   If it is not met and `--force` was not given, stop. Tell the user which command to run first.
3. If phase `pr` is already `done`, ask the user: **Re-run** / **Cancel**.
4. `python3 .claude/scripts/story_state.py set-phase <KEY> pr in_progress`
5. Run the phase **exactly as described in section "### 7. pr → `pull-request` — HUMAN IN THE LOOP (mandatory)"** of `.claude/skills/qe-manager/SKILL.md`. Read that
   section now. It covers the delegation to the `pull-request` subagent, the gate and human-approval rules, and the
   state updates. Those rules apply in full here.
   When it finishes, also write .stories/<KEY>/SUMMARY.md as described in "Final report" of the skill.
6. Set the final phase status with `story_state.py set-phase <KEY> pr done|blocked|failed|skipped --note "<one line>"`.
7. Report back in 15 lines or fewer: the result, any gate or approval outcome, the artifact paths, and the **next step: done. Share .stories/<KEY>/SUMMARY.md**.
   Do not start the next phase.
