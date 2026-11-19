---
description: Exploratory testing of the story's UI with playwright-cli, then a report for your review (files nothing)
argument-hint: <JIRA-KEY> [--env <env>] [--roles ROLE ...] [--budget <n>]
---

# qe-explore — exploratory testing for one story (agent `exploratory-tester`)

Arguments: `$ARGUMENTS` (first token = Jira key; `--force` skips the prerequisite check).

This is a **standalone** command, not one of the 7 gated phases. It changes no phase status and starts no
other phase.

## Steps
1. `python3 .claude/scripts/story_state.py init <KEY>` (idempotent). Show a one-line status for every phase.
2. **Prerequisite:** phase `story` is `done` (`.stories/<KEY>/01-story.md` exists). If not, and `--force` wasn't
   given, stop and tell the user to run `/qe-story <KEY>` first. Mention that results are better after
   `/qe-trace` and `/qe-testcases`, but they aren't required.
3. If `exploration` is already set in state, show its verdict and date, and ask: **Explore again** (the
   previous `explore/` folder is renamed `explore-<timestamp>/`) / **Cancel**.
4. Run `python3 .claude/scripts/test_credentials.py` and show the role names (never values). If `--roles` names
   a role that is missing, warn that its charters will be blocked as a credential gap.
5. Check that the environment (`--env`, or `robot.default_env`) is in `exploratory.allowed_envs`, and that
   `exploratory.login` is configured:
   `python3 .claude/scripts/explore_login.py <KEY> --role <any listed role> --dry-run [--env <env>]`.
   Exit 3 or 4 means stop, and tell the user exactly which config to fill.
6. Delegate to the `exploratory-tester` subagent:
   > Story `<KEY>`. Repo root is the current working directory. Inputs are in `.stories/<KEY>/`.
   > Explore the UI for this story on env `<env>` with roles `<roles or "the roles the story names">` and a
   > budget of `<n>` browser actions. Follow your agent instructions and CLAUDE.md. Return the ≤15-line summary.
7. After it returns, check that `.stories/<KEY>/explore/report.md` exists and that state has `exploration`.
   Show the agent's summary, then **point the user to the report:**
   `Review the report: .stories/<KEY>/explore/report.md` (evidence in `.stories/<KEY>/explore/evidence/`).
   Ask the user to tick a reviewer decision for each finding.
8. Stop. Do not file bugs, create test cases or start another phase. If the user later confirms findings,
   they can ask for them to be drafted as bugs or added as test cases through the normal approval steps.
