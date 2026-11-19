# {{KEY}} — Automation summary

- Branch: `qe/{{KEY}}-{{slug}}`
- Dry-run: {{PASS/FAIL}} (`.stories/{{KEY}}/results/dryrun/log.html`)

## Files added / changed
| File | Change | Purpose |
|---|---|---|
| tests/ui/{{area}}/{{key_lower}}_{{slug}}.robot | added | UI tests for TC-01..TC-04 |
| resources/pages/{{Page}}.resource | modified | new locators/keywords |

## Test case ↔ Robot test map
| Zephyr | Local | Robot file | Robot test | Type | Status |
|---|---|---|---|---|---|
| LOAN-T101 | TC-01 | tests/ui/... | Loan Amount Accepts Minimum | ui | automated |
| LOAN-T104 | TC-04 | — | — | ui | blocked: locator gap |

## Locator map (all from data-testid)
| Logical name | Selector | Source (component file:line) |
|---|---|---|
| LOAN_AMOUNT_INPUT | css=[data-testid="loan-amount-input"] | loan-portal-web/src/.../LoanAmountStep.tsx:42 |

## Locator gaps (ask FE devs to add data-testid)
| Element | Component file:line | Suggested data-testid | Blocking tests |
|---|---|---|---|

## Roles used (RBAC: credentials from the root .env, values never written here)
| Role | Variables | Used by tests |
|---|---|---|
| UNDERWRITER | `%{COMS_UNDERWRITER_USERNAME}` / `%{COMS_UNDERWRITER_PASSWORD}` | LOAN-T101, LOAN-T102 |

## Credential gaps (add these to the test repo's root .env)
| Role | Missing variables | Blocking tests |
|---|---|---|

## Reused keywords
- {{existing keyword}} ({{resource file}})

## Notes / assumptions
- {{test data setup, API auth approach, waits used}}
