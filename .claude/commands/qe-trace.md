---
description: QE phase 2 — static analysis of app code vs acceptance criteria; gate ≥75%
argument-hint: <JIRA-KEY> [--branch <feature-branch hint>]
---

# qe-trace — run ONE phase of the QE flow (phase `traceability`, agent `requirement-traceability`)

Arguments: `$ARGUMENTS` (first token = Jira key; `--force` skips the prerequisite check).

You are acting as the **QE Manager for a single phase**. Run only this phase, then stop.

## Steps
1. `python3 .claude/scripts/story_state.py init <KEY>` (idempotent). Show the user a one-line status for every phase.
2. **Prerequisite:** phase `story` is `done` (.stories/<KEY>/01-story.md exists).
   If it is not met and `--force` was not given, stop. Tell the user which command to run first.
3. If phase `traceability` is already `done`, ask the user: **Re-run** / **Cancel**.
4. `python3 .claude/scripts/story_state.py set-phase <KEY> traceability in_progress`
5. Run the phase **exactly as described in section "### 2. traceability → `requirement-traceability`"** of `.claude/skills/qe-manager/SKILL.md`. Read that
   section now. It covers the delegation to the `requirement-traceability` subagent, the gate and human-approval rules, and the
   state updates. Those rules apply in full here.
   If the user passed `--branch`, tell the agent which feature branch the evidence should come from.
6. Set the final phase status with `story_state.py set-phase <KEY> traceability done|blocked|failed|skipped --note "<one line>"`.
7. Report back in 15 lines or fewer: the result, any gate or approval outcome, the artifact paths, and the **next step: `/qe-testcases <KEY>` (only if the gate passed or was overridden)**.
   Do not start the next phase.
