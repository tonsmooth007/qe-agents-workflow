---
description: Push the latest Robot results for a story to Zephyr Scale (retry a failed sync, or re-sync after editing the triage)
argument-hint: <JIRA-KEY> [--env <env>] [--cycle <CYCLE-KEY>]
---

Arguments: `$ARGUMENTS`

1. Check that `.stories/<KEY>/05-results.json` exists. If it doesn't, stop and suggest `/qe-triage <KEY>`.
2. Run `python3 .claude/scripts/zephyr_cli.py sync-results $ARGUMENTS`.
3. Report the cycle key, whether it was created or reused, the number of executions by status, any Robot tests
   that have no Zephyr tag (`unmapped_robot_tests`, which need tags), and the blocked cases that were posted.
4. If filed bugs exist in `.stories/<KEY>/06-bugs/` (front matter has a `jira_key`), re-link each one to the new
   executions with `python3 .claude/scripts/zephyr_cli.py link-bug <KEY> --bug <BUG-KEY>`.
5. If the sync failed, show the exact error and the likely fix: token, project key, `environment_map` name
   or status names in `.claude/qe.config.yaml`.
