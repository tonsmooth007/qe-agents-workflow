# QE Agent Harness — Loan Application Portal (Robot Framework test repo)

This repo holds the Robot Framework (Browser Library + RequestsLibrary) functional tests for the loan
application web portal **and** a Claude Code agent harness that takes one Jira user story from requirements
to automated tests, bugs and a merge request.

System under test: ReactJS frontend, Go and Java Spring Boot microservices, and MySQL. Each lives in its own
GitLab repo, cloned locally at the paths in `.claude/qe.config.yaml` → `application_repos`. **The application repos are
read-only for every agent.**

## How to work a story
- Start a **fresh Claude Code session for each story**.
- **Full flow:** `/qe-manager LOAN-123`. Resume after `/clear` or in a new window with the same command.
  `--status` shows progress, and `--from <phase>` re-runs from a phase.
- **Step by step:** `/qe-story` → `/qe-trace` → `/qe-testcases` → `/qe-automate [--fix]` → `/qe-triage` →
  `/qe-bugs` → `/qe-pr`, plus `/qe-status` and `/qe-sync-results`. Each command runs one phase and stops.
- Phases, with their subagents in `.claude/agents/`:

| Phase | Subagent | Model | Note |
|---|---|---|---|
| `story` | jira-user-story | sonnet | |
| `traceability` | requirement-traceability | opus | Gate ≥ `traceability.threshold`% |
| `test_cases` | zephyr-test-case | sonnet | |
| `automation` | robot-automation | sonnet | |
| `triage` | triage | opus | Ends with the Zephyr results sync |
| `bugs` | bug | haiku | Human approval required |
| `pr` | pull-request | haiku | Human approval required |

- The phase rules (gates, approvals, fix loop) are defined **once**, in `.claude/skills/qe-manager/SKILL.md`. The
  `/qe-*` commands execute the matching section of that file.

## Story workspace contract (`.stories/<KEY>/`, git-ignored)
| File | Written by | Read by |
|---|---|---|
| `state.json` | `story_state.py` (QE Manager), `trace_score.py` (gate), `zephyr_cli.py sync-results` (`zephyr.test_cycles`, `zephyr.executions`, `zephyr.last_sync`) | everyone; it is the resume point |
| `01-story.md`, `attachments/`, `raw/jira-story.json` | jira-user-story | all later phases |
| `02-traceability.json/.md` | requirement-traceability (+ `trace_score.py` stamps the score) | test cases, automation, triage |
| `03-test-cases.json` | zephyr-test-case (`zephyr_cli.py sync` writes the Zephyr keys back) | automation, triage, PR |
| `04-automation.md` | robot-automation | triage, PR |
| `05-results.json`, `05-triage-report.md`, `results/run-N/` | `run_robot.py` + triage (then `zephyr_cli.py sync-results`) | bug, PR |
| `06-bugs/bug-N.md` | bug (draft) → QE Manager (approval) → `jira_cli.py create-bug` → `zephyr_cli.py link-bug` | PR |
| `07-mr.md` | pull-request (draft) → QE Manager (approval) → `gitlab_cli.py create-mr` | — |
| `SUMMARY.md` | QE Manager | humans |

Templates for every artifact are in `.claude/templates/`. Agents must follow them so the next agent can parse the output.

## Helper scripts (`.claude/scripts/`: run from the repo root as `python3 .claude/scripts/<name>.py`; output is JSON on stdout)
| Script | Purpose |
|---|---|
| `story_state.py` | init / status / set-phase / set / log for `state.json` |
| `jira_cli.py` | get-story, download-attachments, search-bugs, issue-id, **create-bug** (approved drafts only), add-comment |
| `zephyr_cli.py` | list, get, **sync** (create + link test cases), **sync-results** (required after every triage: one cycle per story and env, executions with triage notes, Blocked for locator gaps), **link-bug** (filed bug → failed executions), create-cycle and post-executions (low-level) |
| `gitlab_cli.py` | mr-status, **create-mr** (approved drafts only) |
| `trace_score.py` | deterministic traceability score + gate (exit 0 pass / 2 fail) |
| `testid_index.py` | index of `data-testid`s in the frontend repo(s), with ready-made selectors |
| `run_robot.py` | runs the story's tagged tests (+ rerun of failures, `--dryrun`) → `05-results.json` |
| `robot_summary.py` | parses output.xml into JSON (failing keyword chain, logs, screenshots) |
| `adf.py` | (library) converts between Jira's rich-text format (ADF) and Markdown, used by `jira_cli.py` |

Every command that writes externally supports `--dry-run`. Credentials come from `.claude/.env` and never appear in
files, commits or output.

## Non-negotiable rules
1. **Human in the loop:** bugs are filed and MRs created/pushed only after the user explicitly approves the
   specific draft in this session. Only the QE Manager sets `approval: approved`, and the scripts refuse
   drafts that are not approved.
2. **Locators:** UI locators come **only** from `data-testid` in the React source
   (`css=[data-testid="..."]`). A missing testid is a reported *locator gap*, not a reason to write XPath.
3. **Traceability tags** on every Robot test: `<ZEPHYR-KEY>  <STORY-KEY>  api|ui`, one Robot test per
   Zephyr test case.
4. **No `Sleep`.** Use Browser Library auto-waits and assertion operators, or `Wait For Elements State`.
5. **No secrets or real PII** in tests, artifacts, bug reports or commits. Use synthetic loan/applicant data
   and `%{ENV}` variables for credentials.
6. **Never** force-push, rewrite pushed history, `git add -A`, or stage `.stories/`, `results/` or `.claude/.env`.
7. **Every execution is synced to Zephyr Scale** (`sync-results`) after triage, including fix-loop re-runs.
   A failed sync is reported, never skipped.
8. Evidence over assumption: traceability ratings and triage categories must cite file:line, log lines or
   screenshots.

## Robot Framework conventions in this repo
<!-- TODO: adjust to match this repo's real conventions; the robot-automation agent follows this section. -->
- Suites: UI in `tests/ui/<area>/`, API in `tests/api/<service>/`. File name `<story_key_lower>_<slug>.robot`.
- Page objects/resources: `resources/pages/<Page>.resource` (locator variables + page keywords).
  API keywords: `resources/api/<service>.resource`. Shared: `resources/keywords/`.
- Locator variables: `${UPPER_SNAKE}` holding `css=[data-testid="..."]`.
- Test names: Title Case, behaviour-focused. `[Documentation]` cites the Zephyr key, ACs and objective.
- Variables: `${UI_BASE_URL}` and `${API_BASE_URL}` are injected by `run_robot.py` from `.claude/qe.config.yaml`
  `environments.<env>`.
- Indentation is 4 spaces, with keyword arguments separated by 4 spaces.
