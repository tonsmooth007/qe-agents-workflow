---
description: Find data-testid locators that drifted from the React source and repair them on a heal branch after you approve the mapping
argument-hint: [<HEAL-KEY>] [--scope <STORY-KEY> ...] [--env <env>] [--no-run]
---

# qe-heal — locator drift check and repair (agent `locator-healer`)

Arguments: `$ARGUMENTS` (optional first token = the Jira key the heal work is tracked under, e.g. a
maintenance ticket; `--scope` limits the check to those stories' tests).

This is a **standalone** command, not one of the 7 gated phases.
- **Without a key it is report only:** nothing in `tests/` or `resources/` changes.
- **With a key** it can repair the locators on the branch `qe/<KEY>-locator-heal`, after you approve the mapping.
  The commit and MR then go through `/qe-pr <KEY>` with its usual approval.

## Steps
1. If a key was given: `python3 .claude/scripts/story_state.py init <KEY>` (idempotent).
2. Delegate to the `locator-healer` subagent in **propose** mode:
   > Mode propose. Heal key `<KEY or none>`, scope `<stories or all>`. Repo root is the current working
   > directory. Follow your agent instructions and CLAUDE.md. Return the ≤15-line summary.
3. Show the user the proposals from `heal/proposals.json`: one row per locator with old → new, confidence,
   one-line evidence (commit, component file:line), usages, and the proposed action (heal / gap / resolve_gap).
   Also show the unverifiable dynamic locators and the gaps now resolvable.
   If nothing is missing: say the locators are in sync and stop.
4. **Without a key: stop here.** Point to the report, and say to re-run with a key (e.g. `/qe-heal LOAN-999`) to
   apply the fixes.

## HUMAN IN THE LOOP: the mapping (mandatory before any edit)
5. AskUserQuestion: **Apply the high-confidence fixes, gaps as blocked-locator (Recommended)** /
   **Let me pick per locator** / **Report only**.
   - **Let me pick** → for each low-confidence or `none` item, ask: **Heal as <new>** / **Mark as locator gap** /
     **Skip**. The user may also type a different testid. Check that it exists in
     `python3 .claude/scripts/testid_index.py --filter <id>` before accepting it.
   - Low-confidence items are never applied as part of "Apply the high-confidence fixes".
   - **Report only** → stop.
6. Save the approved mapping: `python3 .claude/scripts/story_state.py set <KEY> heal.approved_mapping '<json>'`
   and `heal.approved_by '"<the user's name>"'`.
7. Delegate to `locator-healer` in **apply** mode with the approved mapping (exact list). It creates/switches to
   the heal branch first. Exit 4 (uncommitted changes elsewhere): show the files and ask the user to commit or
   stash them. Don't do it for them.
8. Check: the drift re-check shows every healed locator `ok`, and every dry-run passed. If not, show what's left.

## Verify against an environment (unless `--no-run`)
9. Ask: **Run the affected tests on <env> and sync to Zephyr** / **Skip**. If yes, for each affected story:
   `python3 .claude/scripts/run_robot.py <STORY> --include <ZEPHYR-KEYS of the affected tests> --run-prefix heal --out heal-<KEY>.json --env <env>`
   then **always** `python3 .claude/scripts/zephyr_cli.py sync-results <STORY> --results heal-<KEY>.json --label "Locator heal <KEY>" --env <env>`.
   Tests without a story tag run under `<KEY>` itself. Put the results in `heal/report.md`. A healed test that
   still fails is not a locator problem: suggest `/qe-triage <STORY>`.
10. `story_state.py set <KEY> heal.status '"applied"'`, plus a `heal.summary` one-liner.

## Report (≤15 lines)
Locators checked / missing, healed (old → new), gaps tagged `blocked-locator` (with suggested testids for the
FE team), branch, dry-run and run results, the report path, and the **next step: `/qe-pr <KEY>`** to commit and
open the MR after approval.
