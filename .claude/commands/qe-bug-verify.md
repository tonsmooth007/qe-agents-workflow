---
description: Retest a fixed bug with the tests that found it, sync the retest to Zephyr, and post the result to the bug after your approval
argument-hint: <BUG-KEY> [--story <STORY-KEY>] [--env <env>] [--regression | --no-regression]
---

# qe-bug-verify — retest one filed bug (agent `bug-verifier`)

Arguments: `$ARGUMENTS` (first token = the bug's Jira key).

This is a **standalone** command, not one of the 7 gated phases. It changes no phase status.
It runs the linked tests against an environment, syncs that run to Zephyr (rule 7), and writes to Jira only
after your explicit approval.

## Steps
1. **Bug status:** `python3 .claude/scripts/jira_cli.py get-issue <BUG>`. Show key, summary, status,
   resolution, fix versions and assignee in one or two lines.
   - If the status is not in `bug_verify.ready_statuses` (`.claude/qe.config.yaml`), ask:
     **Retest anyway** / **Cancel**. A bug that is still open usually means the fix isn't ready.
2. **Locate:** `python3 .claude/scripts/bug_verify.py find <BUG> [--story <STORY>]`.
   - Exit 4: no story workspace references the bug. Ask the user for the story key, or stop.
   - No Zephyr keys / no tagged Robot tests: stop and show the warnings. There is nothing automated to retest
     with. Suggest `/qe-explore <STORY>` or a manual retest.
   - Show: story, Zephyr keys → Robot tests, original failure (keyword + message), previous verifications.
   - `python3 .claude/scripts/story_state.py init <STORY>` (idempotent) so the state file exists.
3. **Environment:** `--env`, or `robot.default_env`. Regression: `--regression`/`--no-regression`, else
   `bug_verify.story_regression`.
4. Delegate to the `bug-verifier` subagent:
   > Bug `<BUG>`, story `<STORY>`. Repo root is the current working directory. Env `<env>`, regression
   > `<yes|no>`. Jira: status `<status>`, fix versions `<list>`. Follow your agent instructions and CLAUDE.md.
   > Return the ≤15-line summary.
5. After it returns, check that `.stories/<STORY>/08-verify/<BUG>.md` exists and that state has
   `zephyr.extra_syncs` with label `Retest for <BUG>` (the retest sync). If the sync is missing, run
   `python3 .claude/scripts/zephyr_cli.py sync-results <STORY> --results verify-<BUG>.json --label "Retest for <BUG>" --env <env>`
   yourself, then `zephyr_cli.py link-bug <STORY> --bug <BUG>`. If it still fails, report it. Never skip it silently.

## HUMAN IN THE LOOP: posting the result (mandatory)
6. Show the user: the verdict (and the agent's proposal if it differs), the before → now table, the evidence
   paths, the recommendation, and the **exact comment body** that would be posted.
7. AskUserQuestion: **Post comment to <BUG>** / **Edit first** / **Don't post**.
   - **Edit first** → apply the user's edits to the draft body (or wait while they edit the file), show it again, ask again.
   - **Don't post** → set `approval: rejected` in the draft's front matter.
8. Only after an explicit **Post**: set `approval: approved` and `approved_by: <the user's name>` in the front
   matter, then run `python3 .claude/scripts/jira_cli.py post-comment --draft .stories/<STORY>/08-verify/<BUG>.md`
   (Claude Code will also ask for permission).
9. Record the outcome: `python3 .claude/scripts/bug_verify.py record <BUG> --story <STORY> --verdict <verdict>
   --report .stories/<STORY>/08-verify/<BUG>.md [--comment-id <id>]`.
10. **Bug status is the team's call.** Don't transition, close or reopen the bug. If the verdict is `verified`
    or `still_failing`, remind the user to close or reopen it in Jira, as the comment recommends.

## Report (≤15 lines)
Bug, story, env, verdict, per-test before → now, Zephyr cycle and executions linked, comment posted (id) or not,
other regression failures (suggest `/qe-triage <STORY>` if any), draft path.
