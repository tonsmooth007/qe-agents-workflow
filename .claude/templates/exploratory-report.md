# {{KEY}} — Exploratory testing report

- Environment: {{qa}} · UI: {{ui_base_url}} · Date: {{YYYY-MM-DD}}
- Roles used: {{ADMIN, UNDERWRITER}} · Credential gaps: {{none | COMS_<ROLE>_USERNAME/PASSWORD}}
- Browser / viewports: {{chromium desktop 1440×900, mobile}}
- Budget: {{n}} / {{150}} browser actions
- Inputs used: 01-story.md{{, 02-traceability.json}}{{, 03-test-cases.json}}
- **Coverage verdict:** {{edge-to-edge covered | partial — see "Not explored"}}
  {{one or two sentences: why the agent judges the edge cases covered, or what is left}}

## Summary
| Charters | Covered | Blocked | N/A | Not explored | ACs probed (+ / − / boundary) | Findings |
|---|---|---|---|---|---|---|
| {{12}} | {{10}} | {{1}} | {{1}} | {{0}} | {{5 / 5}} | {{4}} ({{1 high, 2 medium, 1 low}}) |

## Coverage matrix
| Charter | AC(s) | Heuristic | Status | Evidence |
|---|---|---|---|---|
| C1 Submit application with valid data | AC1 | happy path | covered | `evidence/C1-1.png`, log #3–9 |
| C2 Loan amount boundaries (0, min−1, min, max, max+1) | AC2 | boundary | covered | `evidence/C2-1.png` … |
| C7 Underwriter cannot edit submitted application | AC4 | RBAC | blocked | Credential gap: COMS_UNDERWRITER_* |

Status: `covered` · `blocked` (why) · `n/a` (why) · `not explored` (budget)

## Findings
| # | Title | Type | Severity | AC | Charter |
|---|---|---|---|---|---|
| F1 | {{Amount 50,001 accepted without error}} | suspected_defect | high | AC2 | C2 |

Types: `suspected_defect` · `ux` · `a11y` · `console_error` · `ac_ambiguity`
Severity: `critical` · `high` · `medium` · `low`

### F1. {{Title}}
- **Role / page:** {{UNDERWRITER}} · `{{/applications/new}}`
- **Steps to reproduce:**
  1. {{…}}
- **Expected (from {{AC2}}):** {{AC wording or reasonable expectation, quoted}}
- **Actual:** {{what happened}}
- **Evidence:** screenshot `evidence/{{F1-1.png}}` · console `{{line}}` · request `{{POST /api/... → 200}}`
- **Elements:** `css=[data-testid="{{loan-amount-input}}"]` {{or: no data-testid (locator gap)}}
- **Confidence:** {{high | medium | low}} — {{what would confirm it}}
- **Reviewer decision:** [ ] confirm as bug · [ ] not a bug · [ ] needs PO clarification

## Locator gaps
Elements used during exploration that have no `data-testid`. They matter for automation.
| Page | Element (role + name from snapshot) | Suggested testid |
|---|---|---|

## Test ideas worth automating
Scenarios not in 03-test-cases.json that proved valuable. Add them through `/qe-testcases` if you agree.
- {{idea}} ({{AC}}, {{technique}})

## Not explored and remaining risk
- {{area}}: {{why not (budget, blocked, out of scope)}} — risk {{high/medium/low}}

## Session artifacts
- Charters: `explore/charters.md` · Session log: `explore/session-log.md` · Evidence: `explore/evidence/`
