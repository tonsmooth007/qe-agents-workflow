# QE Agent Harness — Loan Application Portal (Robot Framework test repo)

This repo holds the Robot Framework (Browser Library + RequestsLibrary) functional tests for the loan
application web portal **and** a Claude Code agent harness that takes one Jira user story from requirements
to automated tests, bugs and a merge request.

System under test: ReactJS frontend, Go and Java Spring Boot microservices, and MySQL. Each lives in its own
GitLab repo, cloned locally at the paths in `.claude/qe.config.yaml` → `application_repos`. **The application repos are
read-only for every agent.**

## How to work a story
- Start a **fresh Claude Code session for each story**, launched **from the activated Robot Framework
  virtualenv** (`source .venv/bin/activate && claude`). The scripts and `robot` come from PATH, so without the
  venv they run on the system Python.
- **Full flow:** `/qe-manager LOAN-123`. Resume after `/clear` or in a new window with the same command.
  `--status` shows progress, and `--from <phase>` re-runs from a phase.
- **Step by step:** `/qe-story` → `/qe-trace` → `/qe-testcases` → `/qe-automate [--fix]` → `/qe-triage` →
  `/qe-bugs` → `/qe-pr`, plus `/qe-status` and `/qe-sync-results`. Each command runs one phase and stops.
- Phases, with their subagents in `.claude/agents/`:

| Phase | Subagent | Model | Note |
|---|---|---|---|
| `story` | jira-user-story | sonnet | |
| `traceability` | requirement-traceability | opus | Gate ≥ `traceability.threshold`% |
| `test_cases` | zephyr-test-case | sonnet | Human approval required |
| `automation` | robot-automation | sonnet | |
| `triage` | triage | opus | Ends with the Zephyr results sync |
| `bugs` | bug | haiku | Human approval required |
| `pr` | pull-request | haiku | Human approval required |

- **Exploratory testing (standalone, not a phase):** `/qe-explore LOAN-123 [--env qa] [--roles ROLE ...]
  [--budget n]` runs the `exploratory-tester` subagent (opus). It needs the `story` phase done (better after
  traceability and test cases). It drives the live UI with the `playwright-cli` skill along charters (ACs plus
  edge-case heuristics) until every charter is covered or blocked, then writes `explore/report.md` for human
  review. It is report only: it files nothing in Jira, Zephyr or GitLab.
- **Maintenance flows (standalone, not phases):**
  - `/qe-bug-verify LOAN-456 [--story LOAN-123] [--env qa] [--regression]` (`bug-verifier`, sonnet): retests a
    bug that's marked fixed with the tests that found it. It runs a subset run, compares it with the original
    failure signature, syncs the retest to Zephyr and links it to the bug. It drafts a Jira comment, which is
    posted **only after human approval**. It never transitions the bug.
  - `/qe-impact --range A..B | --repo NAME=A..B [--run]` (`change-impact`, sonnet): maps an app-repo diff to
    stories, ACs, Zephyr keys and Robot tests through every story's traceability evidence and the testid
    locators. Output is a risk-ranked selection and coverage gaps (`.stories/_impact/<id>/`). `--run` runs the
    selection per story after confirmation, and syncs each run.
  - `/qe-heal [HEAL-KEY] [--scope STORY ...]` (`locator-healer`, sonnet): finds `data-testid` locators missing
    from the React source and proposes replacements from frontend git history. With a key, and after the
    human approves the mapping, it fixes only locator values on `qe/<KEY>-locator-heal`. Elements that are
    gone become `blocked-locator` gaps, never XPath. The commit and MR go through `/qe-pr <KEY>`.
- The phase rules (gates, approvals, fix loop) are defined **once**, in `.claude/skills/qe-manager/SKILL.md`. The
  `/qe-*` commands execute the matching section of that file.

## Story workspace contract (`.stories/<KEY>/`, git-ignored)
| File | Written by | Read by |
|---|---|---|
| `state.json` | `story_state.py` (QE Manager), `trace_score.py` (gate), `zephyr_cli.py sync-results` (`zephyr.test_cycles`, `zephyr.executions`, `zephyr.last_sync`) | everyone; it is the resume point |
| `01-story.md`, `attachments/`, `raw/jira-story.json` | jira-user-story | all later phases |
| `02-traceability.json/.md` | requirement-traceability (+ `trace_score.py` stamps the score) | test cases, automation, triage |
| `03-test-cases.json` | zephyr-test-case (draft) → QE Manager (`zephyr_cli.py approve`, after human approval) → `zephyr_cli.py sync` (writes the Zephyr keys back) | automation, triage, PR |
| `04-automation.md` | robot-automation | triage, PR |
| `05-results.json`, `05-triage-report.md`, `results/run-N/` | `run_robot.py` + triage (then `zephyr_cli.py sync-results`) | bug, PR |
| `06-bugs/bug-N.md` | bug (draft) → QE Manager (approval) → `jira_cli.py create-bug` → `zephyr_cli.py link-bug` | PR |
| `07-mr.md` | pull-request (draft) → QE Manager (approval) → `gitlab_cli.py create-mr` | — |
| `explore/charters.md`, `session-log.md`, `evidence/`, `report.md` (+ `exploration` in state) | exploratory-tester (`/qe-explore`) | humans (review); test case ideas go to `/qe-testcases` by hand |
| `08-verify/<BUG>.md`, `verify-<BUG>.json`, `results/verify-N/` (+ `bug_verification` in state) | bug-verifier (draft) → QE Manager (approval) → `jira_cli.py post-comment` | humans, `/qe-status` |
| `heal/drift.json`, `heal/proposals.json`, `heal/report.md`, `heal-<KEY>.json` (+ `heal` in state) | `testid_drift.py`, locator-healer | QE Manager (mapping approval), PR (locator-heal MR) |
| `impact-<id>.json`, `results/impact-N/` | `/qe-impact --run` (`run_robot.py --out`) | Zephyr sync |
| `SUMMARY.md` | QE Manager | humans |

Outside story folders: `.stories/_impact/<id>/impact.json|impact.md|selection.json` (`/qe-impact`) and
`.stories/_heal/<id>/drift.json` (`/qe-heal` without a key). Subset runs (`run_robot.py --run-prefix … --out …`)
never overwrite a story's `05-results.json`. They are synced with `zephyr_cli.py sync-results --results <file>
--label <text>`, which records them under `zephyr.extra_syncs`.

Templates for every artifact are in `.claude/templates/`. Agents must follow them so the next agent can parse the output.

## Helper scripts (`.claude/scripts/`: run from the repo root as `python3 .claude/scripts/<name>.py`; output is JSON on stdout)
| Script | Purpose |
|---|---|
| `story_state.py` | init / status / set-phase / set / log for `state.json` |
| `test_credentials.py` | lists the RBAC roles in the root `.env` (`COMS_<ROLE>_USERNAME/PASSWORD`) without values; `--require ROLE ...` exits 5 if any is missing |
| `story_branch.py` | creates or switches to the story branch `qe/<KEY>-<slug>` from the latest `origin/<target_branch>` (run by robot-automation before any test code); `--check` verifies it |
| `jira_cli.py` | get-story, get-issue, download-attachments, search-bugs, issue-id, **create-bug** (approved drafts only), add-comment, **post-comment** (approved comment drafts only) |
| `zephyr_cli.py` | list, get, **approve** (records the human's test case approval + fingerprint), **sync** (create + link test cases; approved drafts only), **sync-results** (required after every triage: one cycle per story and env, executions with triage notes, Blocked for locator gaps; `--results`/`--label` for subset runs), **link-bug** (filed bug → failed executions), create-cycle and post-executions (low-level) |
| `gitlab_cli.py` | mr-status, **create-mr** (approved drafts only) |
| `trace_score.py` | deterministic traceability score + gate (exit 0 pass / 2 fail) |
| `testid_index.py` | index of `data-testid`s in the frontend repo(s), with ready-made selectors |
| `explore_login.py` | logs a `playwright-cli` session in as a role (`--role ROLE --session name`) from the root `.env` without exposing values; only for `exploratory.allowed_envs`; exit 5 credential gap, 3 login config missing, 2 login failed |
| `run_robot.py` | runs the story's tagged tests (+ rerun of failures, `--dryrun`) → `05-results.json`; `--include … --run-prefix verify --out verify-X.json` for subset runs |
| `robot_catalog.py` | Robot tests with their tags (Zephyr/story keys) and every `data-testid` locator used in tests/resources (text parsing, no Robot import) |
| `bug_verify.py` | find (bug → story, Zephyr keys, tests, original failure signature), compare (retest vs original → proposed verdict), record |
| `impact_map.py` | analyze app-repo git ranges → impacted stories/ACs/Zephyr keys/Robot tests, removed testids, unmapped changes |
| `testid_drift.py` | check locators against the current frontend; missing ids with replacement candidates from frontend git history |
| `robot_summary.py` | parses output.xml into JSON (failing keyword chain, logs, screenshots) |
| `qe-doctor.sh` | (bash) checks tools, packages, harness files, git, config, app repos and secrets; `--online` also checks Jira, Zephyr, GitLab and the app URLs. Run it with `bash` (`/qe-doctor`) |
| `adf.py` | (library) converts between Jira's rich-text format (ADF) and Markdown, used by `jira_cli.py` |

Every command that writes externally supports `--dry-run`. Credentials come from `.claude/.env` and never appear in
files, commits or output.

## Test credentials (RBAC)
- The application uses role-based access control. Each test role's login is in the **test repo's root `.env`**
  (not `.claude/.env`) as `COMS_<ROLE>_USERNAME` and `COMS_<ROLE>_PASSWORD`, e.g. `COMS_ADMIN_*`,
  `COMS_UNDERWRITER_*`.
- `run_robot.py` loads the root `.env` into every Robot run, so tests use `%{COMS_<ROLE>_USERNAME}` /
  `%{COMS_<ROLE>_PASSWORD}`.
- Find out which roles exist with `python3 .claude/scripts/test_credentials.py`. It shows names and set/empty
  flags, never values. **Never read, print, grep or copy `.env`**, and never write usernames or passwords into
  tests, variable files, `.stories/`, Zephyr, Jira, commits or chat.
- Type passwords with Browser's `Fill Secret` (`%COMS_<ROLE>_PASSWORD`), and wrap API logins in
  `Set Log Level    NONE`, so values never reach `log.html`.
- Exploratory sessions log in **only** through `explore_login.py`. Never type credentials with
  `playwright-cli fill`/`type`, and never inspect the login request, cookies, storage or `state-save` output.
- A role a test needs but that isn't in the root `.env` is a **credential gap**: tag the test
  `blocked-credentials` and report the variable names to add. Never substitute another role.

## Python environment
- Run all harness scripts with `python3` from PATH. That's the activated venv the user started Claude Code from.
- If `robot` isn't found, or `robot`, `Browser`, `RequestsLibrary`, `requests` or `yaml` fail to import, **stop**.
  Tell the user to exit Claude Code, activate the Robot venv (`source .venv/bin/activate`), and start `claude`
  again. They can check with `.claude/scripts/qe-doctor.sh`.
- Never `pip install` into the system Python. Never try to activate a venv from inside the session, since that
  doesn't carry over to later commands. Never hard-code an interpreter path as a workaround.

## Non-negotiable rules
1. **Human in the loop:** test cases are created in Zephyr, bugs are filed, bug-verification comments are posted, healed
   locator mappings are applied, and MRs are created and pushed only
   after the user explicitly approves the specific draft in this session. Only the QE Manager records an
   approval (`zephyr_cli.py approve` for test cases, `approval: approved` front matter for bugs, verification
   comments and the MR, `heal.approved_mapping` in state for locator heals), and
   the scripts refuse drafts that are not approved. Test cases also need re-approval if the design changes
   after approval.
2. **Locators:** UI locators come **only** from `data-testid` in the React source
   (`css=[data-testid="..."]`). A missing testid is a reported *locator gap*, not a reason to write XPath.
3. **Traceability tags** on every Robot test: `<ZEPHYR-KEY>  <STORY-KEY>  api|ui`, one Robot test per
   Zephyr test case.
4. **No `Sleep`.** Use Browser Library auto-waits and assertion operators, or `Wait For Elements State`.
5. **No secrets or real PII** in tests, artifacts, bug reports or commits. Use synthetic loan/applicant data,
   and only `%{COMS_<ROLE>_USERNAME}` / `%{COMS_<ROLE>_PASSWORD}` for logins.
6. **Test code is written only on the story branch** (`story_branch.py`), never on `main` or the target branch.
   **Never** force-push, rewrite pushed history, `git add -A`, or stage `.stories/`, `results/` or `.claude/.env`.
7. **Every execution is synced to Zephyr Scale** (`sync-results`) after triage, including fix-loop re-runs,
   and after every bug-verification, impact or heal run (`sync-results --results <file> --label <text>`).
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
