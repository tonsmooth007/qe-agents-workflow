# {{KEY}} — Execution & triage report

- Environment: {{qa}} · Run: `{{run_dir}}` · Log: `{{log_html}}`
- Totals: {{total}} tests · {{pass}} pass · {{fail}} fail · {{flaky}} flaky · pass rate {{pass_rate}}%
- Triage loop: {{n}} / 2
- Zephyr sync: cycle {{LOAN-R12}} ({{env}}) · {{posted}} executions posted ({{pass}} Pass / {{fail}} Fail / {{blocked}} Blocked) · {{ok | FAILED: error → /qe-sync-results}}

## Failures
| # | Robot test | Zephyr | Category | Confidence | Summary |
|---|---|---|---|---|---|
| 1 | Loan Amount Rejects 50,001 | LOAN-T103 | product_defect | high | API accepts 50001 (no @Max on DTO) |

Categories: `product_defect` · `test_defect` · `environment` · `test_data` · `flaky`

### 1. {{Robot test name}}
- **Failure:** `{{robot message}}`
- **Failing keyword chain:** {{kw > kw > kw}}
- **Evidence:** screenshot `{{path}}`, log lines, HTTP status/body
- **Root-cause analysis:** {{what in the app or the test explains this; app code file:line}}
- **Category / why:** {{reasoning that rules out the other categories}}
- **Recommended action:** {{fix test (what) | file bug | re-run after env fix | fix data}}

## Flaky tests
| Robot test | First failure | Suspected cause | Suggested hardening |
|---|---|---|---|

## Hand-offs
- To robot-automation (test defects): {{list}}
- To bug agent (product defects): {{list}}
- To human (environment/test data): {{list}}
