---
description: Check that everything the QE harness needs is installed and configured (add --online to also test Jira, Zephyr and GitLab access)
argument-hint: [--online]
---

Run `COLUMNS=120 bash .claude/scripts/qe-doctor.sh --no-color $ARGUMENTS` from the repo root.

Show the user the results table and the summary line **exactly as printed**, in a code block. Don't
re-format the table. Then add a short summary:
- **Failures first**, each with the fix from the output (the `→` lines), grouped as tools, packages, harness
  files, git, config, app repos, secrets and connectivity.
- Then the warnings, in one line each.
- End with: ready / not ready for `/qe-manager <KEY>`.

Never print or ask for secret values. If a failure needs the user to run something interactive (e.g.
`rfbrowser init`, `pip install`), suggest it with the `!` prefix so it runs in this session. Do not change
config or install anything unless the user asks.
