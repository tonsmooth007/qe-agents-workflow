# {{KEY}} — {{SUMMARY}}

| Field | Value |
|---|---|
| Jira | {{URL}} |
| Type / Status / Priority | {{TYPE}} / {{STATUS}} / {{PRIORITY}} |
| Components | {{COMPONENTS}} |
| Fix version / Sprint | {{FIX_VERSION}} / {{SPRINT}} |
| Parent / Epic | {{PARENT}} |
| AC source | {{field:customfield_x \| description \| none}} |
| **Test type** | **{{api \| ui \| both}}** — reason: {{why}} |

## Business context
{{2–5 sentence plain-language summary of what the user can now do and why}}

## Acceptance criteria (normalised)
| ID | Criterion (verbatim or minimally reworded) | Testable? | Layer (api/ui/both) | Notes / ambiguity |
|---|---|---|---|---|
| AC-1 | | yes | ui | |
| AC-2 | | needs clarification | api | {{question for PO}} |

## Business rules & data
- {{validation rules, limits (loan amount min/max, term, rate, eligibility), roles/permissions, states}}

## Attachments reviewed
| File | What it shows | Relevant ACs |
|---|---|---|
| attachments/{{id_name.png}} | {{mockup of loan application step 2…}} | AC-1, AC-3 |

## Linked issues & sub-tasks
- {{key}} ({{relation}}) — {{summary}} [{{status}}]

## Relevant comments
- {{author, date}}: {{decision/clarification that changes expected behaviour}}

## Open questions / risks
- {{ambiguities, missing info, dependencies on other .stories/services}}
