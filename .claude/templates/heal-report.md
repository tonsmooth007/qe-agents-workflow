# Locator heal — {{KEY or "report only"}}

- Frontend: {{loan-portal-web @ <sha> (<branch>)}} · Locators checked: {{n}} · ok {{n}} · missing {{n}} · unverifiable {{n}}
- Scope: {{all tests | stories LOAN-123, LOAN-130}} · Drift data: `{{.stories/KEY/heal/drift.json}}`
- Branch: {{qe/LOAN-999-locator-heal or "n/a (report only)"}} · Dry-run: {{PASS | FAIL}} · Verification run: {{run dir, pass/fail}}

## Proposed fixes
| # | Old testid | New testid | Confidence | Evidence | Used at | Decision |
|---|---|---|---|---|---|---|
| 1 | apply-next-button | apply-continue-button | high | renamed in `b667454` "rename buttons", `src/LoanAmount.tsx:5`, same element (button, same onClick) | `resources/pages/LoanAmountPage.resource:4` (`${NEXT_BUTTON}`) | heal |
| 2 | ghost-thing | — | — | not in the frontend history: never existed or removed long ago | `…:5` | locator gap |

Confidence: **high** = removed and added in the same commit and file, the component shows the same element
(type, handler, text) · **low** = name similarity only, or a different element. Low-confidence items are never
applied without your explicit OK.

## Applied changes
| File:line | Variable | Before | After |
|---|---|---|---|

## Locator gaps (no replacement testid)
| Old testid | Element (component file:line) | Suggested testid for the FE team | Tests tagged `blocked-locator` |
|---|---|---|---|

## Unverifiable (dynamic ids)
| Locator | Why | What to check |
|---|---|---|

## Verification
- Dry-run: `python3 .claude/scripts/run_robot.py {{KEY}} --dryrun …` → {{result}}
- Affected tests run on {{env}}: {{pass/fail per story, Zephyr cycle}}
