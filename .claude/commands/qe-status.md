---
description: Show the QE workflow status for a story and the next command to run
argument-hint: <JIRA-KEY>
---

Run `python3 .claude/scripts/story_state.py status $ARGUMENTS`. If no state exists, say so and suggest `/qe-story <KEY>`.

Show a compact table (phase | status | note), the traceability score, gate result and any override, the bug
keys, and the MR URL. Then show the **next command** by mapping `next_phase`:
story→`/qe-story`, traceability→`/qe-trace`, test_cases→`/qe-testcases`, automation→`/qe-automate`,
triage→`/qe-triage`, bugs→`/qe-bugs`, pr→`/qe-pr`. If the latest triage still has unresolved
`test_defect` items, suggest `/qe-automate <KEY> --fix` instead.

If state has `exploration`, also show one line: exploratory verdict, coverage, findings (high), date, and the
report path. If it doesn't, mention that `/qe-explore <KEY>` is available once the story phase is done.

If state has `bug_verification`, show one line per bug: key, latest verdict, date, and whether the comment
was posted. Filed bugs without a verification: suggest `/qe-bug-verify <BUG>` once they are marked fixed.
If state has `heal`, show its status and summary (next step `/qe-pr <KEY>` when `applied` and no MR yet).

Do not run any phase.
