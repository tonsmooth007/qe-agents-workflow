---
issue: LOAN-456              # the bug this comment is posted on
story: LOAN-123
verdict: verified            # verified | still_failing | new_failure | flaky | blocked | not_deployed
proposed_verdict: verified   # what bug_verify.py compare proposed (kept for audit if you override it)
env: qa
run_dir: .stories/LOAN-123/results/verify-1
results: .stories/LOAN-123/verify-LOAN-456.json
zephyr_keys: [LOAN-T103]
zephyr_cycle: LOAN-R12       # cycle the retest executions were posted to
bug_status_at_retest: Ready for QA
fix_versions: []
recommendation: close        # close | reopen | investigate | rerun_later
approval: pending            # pending -> approved (by QE Manager after human OK) -> posted
approved_by: null
comment_id: null
---
<!-- Everything below this front matter is posted to the bug as the Jira comment. Keep it factual and short.
     No credentials, usernames or real PII. Refer to test users by role. -->
**QE retest: {{VERDICT IN CAPS}}** (automated, {{env}}, {{date}})

| Zephyr | Robot test | Before ({{original run}}) | Now ({{run}}) |
|---|---|---|---|
| {{LOAN-T103}} | {{Loan Amount Rejects 50,001}} | FAIL: {{original message, shortened}} | {{PASS / FAIL: message}} |

**What was checked:** {{one or two sentences: the AC and behaviour the tests cover, e.g. "AC-2: the API rejects amounts above 50,000 with 400 and a validation error."}}

**Result:** {{verified: every linked test passed on the first attempt. still_failing: same failing keyword and message as the original report. new_failure: fails differently (what changed). flaky: passed only on the automatic rerun. blocked: why the tests could not run.}}

**Evidence:** Robot log `{{run_dir}}/log.html`{{, screenshot `<path>`}} · Zephyr cycle {{LOAN-R12}}, executions linked to this bug.

**Recommendation:** {{Close the bug | Reopen: <reason> | Needs investigation: <what to look at> | Re-run after <env/data fix>}}.
