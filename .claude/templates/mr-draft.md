---
story: LOAN-123
title: "LOAN-123: Automate <story summary> (UI+API)"
source_branch: qe/LOAN-123-short-slug
target_branch: main
labels: [qe-automation]
draft_mr: false
approval: pending           # pending -> approved (by QE Manager after human OK) -> submitted
approved_by: null
mr_url: null
---
## What
Automated tests for [LOAN-123]({{jira url}}) — {{summary}}.

## Test cases (Zephyr)
| Zephyr | Robot test | Type | Last result |
|---|---|---|---|
| LOAN-T101 | Loan Amount Accepts Minimum | ui | PASS |

## Execution
- Env {{qa}}, {{pass}}/{{total}} passed ({{pass_rate}}%). Log attached in pipeline / `{{run_dir}}`.
- Known failures linked to bugs: {{LOAN-789 (LOAN-T103)}}

## Changes
- {{file}} — {{why}}

## Locator gaps / follow-ups
- {{element}} needs `data-testid` in {{component}} — tests {{…}} tagged `blocked`

## Checklist
- [ ] Locators use data-testid only
- [ ] Tests tagged with Zephyr key + story key + api/ui
- [ ] No secrets / hard-coded credentials
- [ ] Reused existing keywords where possible
- [ ] `robot --dryrun` passes
