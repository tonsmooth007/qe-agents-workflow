# Change impact — {{id}}

- Ranges: {{loan-portal-web v1.4.0..v1.5.0 · loan-application-service origin/main..origin/release/1.5}}
- Commits: {{n}} · Files changed: {{n}} · Analysis: `.stories/_impact/{{id}}/impact.json`
- Selection: **{{n}} Robot tests / {{n}} Zephyr test cases across {{n}} stories** (of {{total}} tests in the repo)
- Verdict: {{RUN THE SELECTION | RUN THE SELECTION + FULL REGRESSION FOR <area> | NO AUTOMATED COVERAGE FOR <area>}}

## Impacted stories
| Risk | Story | ACs hit (line/file) | Zephyr keys | Robot tests | Why |
|---|---|---|---|---|---|
| high | LOAN-123 | AC-2 (line) | LOAN-T103, LOAN-T104 | 2 | `LoanRequestDto.java:18` @Max changed in abc1234 |

Risk: **high** = a changed hunk touches the traceability evidence line, or a testid the tests use was removed ·
**medium** = same file, different lines · **low** = shared page resource / locator touched only.

## Locator impact (data-testid)
| Change | testid | Used at | Suites affected | Action |
|---|---|---|---|---|
| removed | apply-next-button | `resources/pages/LoanAmountPage.resource:4` | 3 | `/qe-heal <KEY>`: likely renamed to `apply-continue-button` |

## Changes without traceability coverage
| Repo | File | Change | Assessment (agent) | Suggested coverage |
|---|---|---|---|---|
| credit-decision-service | internal/handler/decision.go | modified (+40/−3) | {{what the change does, risk}} | {{existing story/test to run, or "gap: no test covers this"}} |

## Stories without a traceability matrix
{{LOAN-140, LOAN-141: run /qe-trace on them to include them in future impact analysis}}

## Run plan
Per story (each run is synced to that story's Zephyr cycle with the label "Impact {{id}}"):
```
python3 .claude/scripts/run_robot.py LOAN-123 --include LOAN-T103 LOAN-T104 --run-prefix impact --out impact-{{id}}.json --env qa
```

## Results (filled after the run)
| Story | Run | Pass | Fail | Flaky | Zephyr cycle | Notes |
|---|---|---|---|---|---|---|
