---
description: Select the regression tests a code change needs (app repo git ranges → ACs → Zephyr → Robot), optionally run them and sync to Zephyr
argument-hint: --range <A..B> | --repo <NAME>=<A..B> ... [--only <NAME> ...] [--run] [--env <env>]
---

# qe-impact — change-impact analysis and regression selection (agent `change-impact`)

Arguments: `$ARGUMENTS`

This is a **standalone** command, not one of the 7 gated phases, and it isn't tied to one story. It reads
the application repos (read-only git) and every story workspace in `.stories/`.

## Steps
1. **Ranges:** need `--range A..B` (all application repos) and/or `--repo NAME=A..B` (per repo; names from
   `application_repos` in `.claude/qe.config.yaml`). If neither was given, ask the user which range: e.g. last
   release tag to the release branch, or `origin/main..origin/<feature-branch>` for an MR. The refs must already
   exist in the local clones. The harness never fetches app repos, so the user may need to `git fetch` there first.
2. Delegate to the `change-impact` subagent:
   > Repo root is the current working directory. Analyse the change impact for `<ranges>` `[--only ...]`.
   > Follow your agent instructions and CLAUDE.md. Return the ≤15-line summary.
3. Check that `.stories/_impact/<id>/impact.md` exists. Show the user: the selection size vs the total suite, the
   impacted stories table (risk, ACs, Zephyr keys, test count), removed testids, coverage gaps, and repos with
   errors. Point them to the report.
4. **Without `--run`: stop here.** Suggest `/qe-impact … --run` to execute the selection, `/qe-heal <KEY>` for
   removed testids, and `/qe-trace <STORY>` for stories without a traceability matrix.

## Running the selection (`--run`, or the user asks for it after step 3)
5. Confirm first. AskUserQuestion: **Run <n> tests on <env> and sync to Zephyr** / **Run high-risk stories only**
   / **Don't run**. Running posts executions to each story's Zephyr cycle.
6. For each selected story with a workspace (use `selection.json` if the agent wrote one, else `impact.json`):
   `python3 .claude/scripts/run_robot.py <STORY> --include <ZEPHYR-KEYS> --run-prefix impact --out impact-<id>.json --env <env>`
   then **always** `python3 .claude/scripts/zephyr_cli.py sync-results <STORY> --results impact-<id>.json --label "Impact <id>" --env <env>`.
   A failed sync is reported, never skipped.
7. Fill the "Results" table in `.stories/_impact/<id>/impact.md` (story, run dir, pass/fail/flaky, cycle).
8. **Failures are not triaged here.** For each story with failures, suggest `/qe-triage <STORY>` (the full triage
   with classification and the fix loop), or `/qe-bug-verify <BUG>` if a known bug covers it. Don't draft bugs
   from an impact run.

## Report (≤15 lines)
Analysis id, ranges, selection (tests / stories) vs total, top risks, gaps, removed testids, and, if run, the
results per story with Zephyr cycles and the next commands.
