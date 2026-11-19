---
story: LOAN-123
title: "[Loan Application] API accepts loan amount above 50,000 maximum"
link_mode: relates          # child | relates  (default from .claude/qe.config.yaml jira.bug.default_link_mode)
severity: Major             # Blocker | Critical | Major | Minor | Trivial (also stated in body)
priority: High              # Jira priority name
labels: [regression]
zephyr_keys: [LOAN-T103]
robot_test: "Loan Amount Rejects 50,001"
found_in_run: run-1         # results/run-N the failure came from (used by /qe-bug-verify)
attachments:                # repo-relative paths (screenshots, log excerpts)
  - .stories/LOAN-123/results/run-1/browser/screenshot/fail-1.png
duplicates_checked: [LOAN-456]   # keys returned by search-bugs that were reviewed
approval: pending           # pending -> approved (by QE Manager after human OK) -> filed
approved_by: null
jira_key: null
---
## Summary
{{one sentence: what is wrong, where}}

## Environment
- Env: {{qa}} · UI: {{url}} · API: {{url}}
- Build/version: {{if known}}
- Found by: Robot test `{{robot test}}` ({{zephyr key}}), run `{{run_dir}}`

## Steps to reproduce
1. {{…}}
2. {{…}}

## Expected result
{{per AC-x: quote the acceptance criterion}}

## Actual result
{{observed behaviour, HTTP status/body, UI message}}

## Evidence
- Screenshot / log excerpt (attached)
- Suspected code location: `{{repo}}/{{file}}:{{line}}` — {{why}}

## Severity rationale
{{impact on borrower/business, workaround?}}
