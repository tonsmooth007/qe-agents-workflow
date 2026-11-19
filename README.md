# QE Agent Harness for Claude Code

A Claude Code harness that takes one Jira user story for the loan application portal from requirements to
automated tests, synced results, bugs and a merge request:

```
/qe-manager LOAN-123   (QE Manager skill: runs in the main session, owns the gates and human approvals)
 1 story         jira-user-story           Jira → .stories/LOAN-123/01-story.md (ACs, attachments, api/ui/both)
 2 traceability  requirement-traceability  static analysis of React / Go / Spring Boot / MySQL against the ACs → score
                 ── GATE: score ≥ 75% (.claude/scripts/trace_score.py): stop / override with a reason / re-scan
 3 test_cases    zephyr-test-case          designs test cases (draft) → HUMAN REVIEWS & APPROVES → Zephyr Scale
 4 automation    robot-automation          creates the story branch qe/<KEY>-<slug> first, then writes Robot tests
                                           (Browser + RequestsLibrary); data-testid locators only
 5 triage        triage                    run → rerun failures → classify → SYNC RESULTS TO ZEPHYR test cycle;
                                           test defects loop back to 4 (max 2), and every re-run is synced again
 6 bugs          bug                       drafts → HUMAN APPROVES each → Jira (child of / related to the story)
                                           → linked to the failed Zephyr executions
 7 pr            pull-request              commit + MR draft → HUMAN APPROVES → push + GitLab MR
```

You can run the whole flow with `/qe-manager`, or one phase at a time with the `/qe-*` commands.
Everything is saved under `.stories/<KEY>/`, so each story can be worked in its own context window and resumed
at any point.

## Components
| Piece | Where | Model | Color | Role |
|---|---|---|---|---|
| QE Manager | `.claude/skills/qe-manager/SKILL.md` | your session model (Sonnet is enough) | — | Orchestrator: delegates, enforces gates, asks for approvals |
| Jira User Story Agent | `.claude/agents/jira-user-story.md` | sonnet | blue | Story, ACs, attachments (mockups/PDFs), test type |
| Requirement Traceability Agent | `.claude/agents/requirement-traceability.md` | opus | purple | Code-vs-AC evidence matrix, 75% gate |
| Zephyr Test Case Agent | `.claude/agents/zephyr-test-case.md` | sonnet | cyan | Test case design as a draft for your review (no Zephyr writes) |
| Robot Framework Automation Agent | `.claude/agents/robot-automation.md` | sonnet | green | Creates the story branch, then Robot suites, data-testid locators, test-defect fixes |
| Triage Agent | `.claude/agents/triage.md` | opus | orange | Runs tests, classifies failures, syncs results to Zephyr |
| Bug Agent | `.claude/agents/bug.md` | haiku | red | Bug drafts with duplicate check (no filing) |
| Pull Request Agent | `.claude/agents/pull-request.md` | haiku | pink | Diff review, commit, MR draft (no push) |

**Why the QE Manager is a skill, not a subagent:** Claude Code subagents can't start other subagents, so the
orchestrator has to run in the main conversation. Each worker runs in its own context and returns a summary
of 15 lines or fewer, which keeps the main session small.

## Install into the Robot Framework test repo

> **Always activate the Robot Framework virtualenv before you start Claude Code.**
> The harness has no Python setting of its own. The agents run `python3 .claude/scripts/...` and `robot` from
> your PATH, and Claude Code passes on the environment of the terminal you start it from. If the venv isn't
> active, the agents use the system Python, where Robot Framework, Browser Library and RequestsLibrary are
> missing or the wrong versions.
>
> ```bash
> cd <robot-test-repo>
> source .venv/bin/activate     # your venv path; on Windows: .venv\Scripts\activate
> claude
> ```
> Activating it inside a running Claude Code session doesn't help. Exit, activate, and start `claude` again.

1. Copy into the **root of the test repo**, merging with what is already there:
   - the whole `.claude/` folder (agents, skills, commands, scripts, templates, `qe.config.yaml`, `.env.example`, settings);
   - `CLAUDE.md` and `requirements-qe.txt`.
   Append the contents of `.gitignore` to the repo's `.gitignore`. If the repo already has a `CLAUDE.md`, merge
   the two and keep the "Robot Framework conventions" section accurate, because the automation agent follows it.
2. Activate the virtualenv you run Robot from, then `pip install -r requirements-qe.txt`, and run
   `rfbrowser init` if you haven't already.
3. `cp .claude/.env.example .claude/.env` and fill in the Jira, Zephyr and GitLab tokens. The test role
   credentials go in the root `.env` instead (see "Test credentials" below).
4. Edit `.claude/qe.config.yaml`:
   - `jira`: project key, the AC custom field id (or null), and the bug issue types. A child bug needs a
     sub-task type.
   - `zephyr`: project key, optional folders, `status_map`, `blocked_status`, and `environment_map`. Each
     environment name must exist in your Zephyr project, or you remove that entry.
   - `gitlab`: this repo's project path and target branch.
   - `application_repos`: **local paths to the React, Go and Spring Boot repos**, plus where the migrations live.
   - `test_repo`: your suite and resource folder layout. `environments`: the UI and API base URLs per environment.
5. `cp .claude/settings.local.json.example .claude/settings.local.json` and list the same application repo
   paths under `additionalDirectories`, so Claude Code is allowed to read them.
6. Run the doctor until it reports no failures:
   ```bash
   .claude/scripts/qe-doctor.sh            # tools, packages, harness files, git, config, app repos, secrets
   .claude/scripts/qe-doctor.sh --online   # + Jira / Zephyr / GitLab auth, issue types, statuses, environments, app URLs
   ```
   The results print as one table (Section | Status | Check | Fix), with PASS/WARN/FAIL/INFO in color and a
   summary line. Use `--no-color` for logs. Run it with the virtualenv active (the Tools row shows which Python
   it found), or point at it with `QE_PYTHON=/path/to/venv/bin/python`. Exit code 1 means
   at least one failure, so you can use it in CI too. Inside Claude Code, `/qe-doctor [--online]` runs it and
   summarises the fixes.
7. Smoke test:
   ```bash
   python3 .claude/scripts/jira_cli.py get-story LOAN-123 | head -40      # check the ACs are extracted
   python3 .claude/scripts/zephyr_cli.py list --issue LOAN-123
   python3 .claude/scripts/testid_index.py --filter loan | head -40
   ```
8. Start Claude Code **from the activated virtualenv** (see the note above). In it, `/agents` should list the 7 agents, and typing `/qe-` should autocomplete `/qe-manager`
   and the per-phase commands. Restart Claude Code if they don't appear.

## Daily use: one story per context window

Every session starts the same way. Activate the venv first, then start Claude Code:
```bash
cd <robot-test-repo> && source .venv/bin/activate && claude
```

### Full flow
```
claude                                   # fresh session from the test repo root, with the venv ACTIVE
/qe-manager LOAN-123                     # runs every phase; asks you at the gates and before filing or pushing
/clear                                   # any time; state is on disk
/qe-manager LOAN-123                     # resumes at the next unfinished phase
/qe-manager LOAN-123 --status
/qe-manager LOAN-123 --from automation   # redo from a phase (e.g. after new data-testids land)
```

### Step by step (one phase per command)
Each command checks that the previous phase is done, then runs one phase with the same gates and approvals
as `/qe-manager`. It saves state, then **stops and tells you the next command**. You can `/clear` between any
two of them.

| # | Command | Phase / agent | Notes |
|---|---|---|---|
| – | `/qe-doctor [--online]` | — | Checks the harness setup and dependencies |
| – | `/qe-status LOAN-123` | — | Progress and the next command to run |
| 1 | `/qe-story LOAN-123` | jira-user-story | |
| 2 | `/qe-trace LOAN-123 [--branch feat/x]` | requirement-traceability | 75% gate: stop / override / re-scan |
| 3 | `/qe-testcases LOAN-123` | zephyr-test-case | Needs the gate passed or overridden. You review and approve the test cases before they're created |
| 4 | `/qe-automate LOAN-123 [--fix] [--allow-fallback]` | robot-automation | `--fix` fixes the test defects from triage |
| 5 | `/qe-triage LOAN-123 [--env uat]` | triage | Always syncs the results to Zephyr Scale |
| – | `/qe-sync-results LOAN-123 [--env uat]` | — | Retries a failed sync or re-pushes it, and re-links bugs |
| 6 | `/qe-bugs LOAN-123` | bug | You approve each draft before it's filed |
| 7 | `/qe-pr LOAN-123` | pull-request | You approve before push and MR creation |

- **Fix loop:** `/qe-triage` → `/qe-automate LOAN-123 --fix` → `/qe-triage`, at most 2 loops.
- **`--force`** skips a prerequisite check, e.g. to redo automation for test cases that already exist in Zephyr.
- **The rules for each phase live only in `.claude/skills/qe-manager/SKILL.md`.** The commands read them
  from there, so both ways of running behave the same.
- **You can also call any agent directly,** e.g. *"use the triage agent on LOAN-123 against uat"*.

## Test credentials (RBAC)
The application uses role-based access control, so tests log in as different roles. There are two `.env` files,
both git-ignored:

| File | Holds | Used by |
|---|---|---|
| `.env` (test repo root) | `COMS_<ROLE>_USERNAME` and `COMS_<ROLE>_PASSWORD`, one pair per role | Robot tests (`%{COMS_<ROLE>_USERNAME}`), loaded into every run by `run_robot.py` |
| `.claude/.env` | Jira, Zephyr Scale and GitLab tokens | the harness scripts |

```bash
# .env (test repo root)
COMS_ADMIN_USERNAME=...
COMS_ADMIN_PASSWORD=...
COMS_UNDERWRITER_USERNAME=...
COMS_UNDERWRITER_PASSWORD=...
```

- **Roles:** `python3 .claude/scripts/test_credentials.py` lists them (names only, never values). The agents use
  it to pick the right role for each test case and to write negative RBAC cases. The doctor checks that every
  pair is complete.
- **In tests:** `%{COMS_<ROLE>_USERNAME}` / `%{COMS_<ROLE>_PASSWORD}`, through a role-based login keyword. Passwords
  are typed with `Fill Secret`, and API logins run under `Set Log Level    NONE`, so they never show in `log.html`.
- **Values stay private:** Claude Code is blocked from reading either `.env`. No username or password is ever
  written into tests, `.stories/`, Zephyr, Jira or commits.
- **Missing roles:** if a test needs a role that isn't in `.env`, it's tagged `blocked-credentials`, posted to
  Zephyr as Blocked, and the variable names to add are listed in `04-automation.md`.

## Zephyr Scale integration
| When | What is written | Command |
|---|---|---|
| Phase 3, **after your approval** | Test cases with steps, labels and AC coverage, linked to the story. Idempotent: existing linked cases with the same name are reused | `zephyr_cli.py approve`, then `zephyr_cli.py sync` (asks permission) |
| Phase 5, after **every** triage run | Results posted to the story's test cycle | `zephyr_cli.py sync-results` (automatic) |
| Phase 6, after each bug is filed | Bug linked to the failed executions of its test cases | `zephyr_cli.py link-bug` (automatic) |

What `sync-results` posts:
- **One test cycle per story and environment**, e.g. `LOAN-123 | QA | Automated regression`. It's created on
  the first run, linked to the story, and reused afterwards. The cycle keys are saved in
  `state.json → zephyr.test_cycles`.
- **One execution per Zephyr key on each Robot test:**
  - Pass, Fail, or Not Executed for skipped tests (`zephyr.status_map`).
  - The comment holds the Robot test name, the triage category, confidence and summary, and the failure message.
  - **Flaky** tests are posted as Pass, with a note that the first attempt failed.
- **Test cases that couldn't be automated because of a locator gap** are posted as **Blocked**
  (`zephyr.blocked_status`), so the cycle covers every test case for the story.
- **The Zephyr environment** comes from `zephyr.environment_map` and is left out when there's no entry.
- **Re-runs add new executions to the same cycle,** and Zephyr shows the latest one.
- **The execution ids** are saved to `state.json → zephyr.executions` (used by `link-bug`). `zephyr.last_sync`
  records when the last sync ran and for which run.

**Traceability back to Zephyr comes from Robot tags.** Every test carries
`[Tags]    <ZEPHYR-KEY>    <STORY-KEY>    api|ui`. Robot tests without a Zephyr tag are listed under
`unmapped_robot_tests` and aren't posted.

## Safety and human in the loop
- **Three approval points:** test cases (phase 3), bugs (phase 6) and the MR (phase 7). The agents for these only
  write drafts (`03-test-cases.json`, `06-bugs/*.md`, `07-mr.md`) with approval pending.
- **Test cases:** the QE Manager shows you a review (one row per case, AC coverage, `expected-fail` cases,
  assumptions). You choose **Approve**, **Revise with feedback**, **Edit the file yourself** or **Don't create**.
  On approval, `zephyr_cli.py approve` records your name and a fingerprint of the test cases. `sync` refuses
  (exit 3) if they weren't approved, or if anything in the design changed after approval.
- **Bugs and MR:** the QE Manager shows you each draft. Only after you explicitly approve does it set `approval: approved` and
  `approved_by`.
- `zephyr_cli.py sync`, `jira_cli.py create-bug` and `gitlab_cli.py create-mr` **refuse** unapproved drafts with exit code 3.
- `.claude/settings.json` sets the permissions:
  - **ask:** `create-bug`, `add-comment`, `create-mr`, `git push`, `git commit`, and Zephyr test-case
    creation, cycle creation and execution posting run directly, so Claude Code prompts you.
  - **allow:** read-only commands, recording your test case approval (`approve`), and the required results sync
    (`sync-results`, `link-bug`).
  - **deny:** force-push and reading `.claude/.env`.
- Every command that writes externally supports `--dry-run`.

## Layout
```
<test repo root>/
├── .claude/
│   ├── agents/*.md                7 subagents (each with its model set)
│   ├── skills/qe-manager/         orchestrator skill (full flow, the only source of phase rules)
│   ├── commands/qe-*.md           one command per phase + /qe-status + /qe-sync-results + /qe-doctor
│   ├── scripts/                   Jira / Zephyr Scale / GitLab REST clients, gates, Robot runner/parser, testid index,
│   │                              qe-doctor.sh (dependency and config check)
│   ├── templates/                 artifact templates the agents fill in
│   ├── qe.config.yaml             non-secret configuration (relative paths resolve from the repo root)
│   ├── .env.example               template for secrets → copy to .claude/.env (git-ignored, loaded by the scripts)
│   ├── settings.json              permissions (allow read-only + results sync, ask on other writes, deny force-push)
│   └── settings.local.json        per-engineer: additionalDirectories for the app repos (git-ignored)
├── CLAUDE.md                      project instructions loaded in every session
├── requirements-qe.txt
├── tests/ resources/ ...          your existing Robot Framework suites
└── .stories/<KEY>/                 per-story workspace (git-ignored), the memory between context windows
```

## Tuning
- **Gate threshold and weights:** `traceability` in `.claude/qe.config.yaml`.
- **Zephyr statuses and environments:** `zephyr.status_map`, `zephyr.blocked_status`, `zephyr.environment_map`.
- **Child-bug issue type:** in company-managed Jira projects, a "child" bug must be a sub-task issue type
  (e.g. `Sub-bug`). Otherwise use `relates`.
- **Terminal color per agent:** the `color:` line in each agent's front matter (red, blue, green, yellow,
  purple, orange, pink, cyan).
- **Model per agent:** the `model:` line in each agent's front matter (`haiku`, `sonnet`, `opus` or `inherit`).
  - **opus** for requirement-traceability and triage. They need deep reasoning across several repos, and their
    output decides the gate and whether bugs get filed.
  - **sonnet** for robot-automation, zephyr-test-case and jira-user-story. Strong at code and structured design,
    and these agents run most often.
  - **haiku** for bug and pull-request. They fill in templates from analysis that's already done, and a human
    approves the result.
  - Worth changing: robot-automation → opus if fix loops keep happening on complex UI flows; bug → sonnet if
    the drafts need a lot of editing; pull-request → sonnet if it stages the wrong files.

## Troubleshooting
Start with `.claude/scripts/qe-doctor.sh --online`. It catches most of these.

| Symptom | Likely cause / fix |
|---|---|
| `get-story` returns `acceptance_criteria_md: null` | Set `jira.acceptance_criteria_field`, or make sure the description has an "Acceptance Criteria" heading |
| `robot: command not found`, or `No module named robot / Browser / RequestsLibrary` | Claude Code was started without the venv active. Exit, `source .venv/bin/activate`, start `claude` again |
| Automation stops with "Uncommitted changes on '<branch>'" (exit 4) | Commit or stash your local changes, then re-run `/qe-automate`. The harness never stashes or discards them for you |
| Tests fail at login with 401 / "invalid credentials" | Check that role's `COMS_<ROLE>_*` pair in the root `.env` (`test_credentials.py` shows which are set). Triage classes this as `test_data`, not a bug |
| `run_robot.py` fails with rc 252 | No tests are tagged with the story key, or a suite path or syntax is wrong. Run `/qe-automate --fix` or check the tags |
| Zephyr sync fails | Check the token and `zephyr.project_key`. Names in `environment_map` and `status_map` must exist in Zephyr. Retry with `/qe-sync-results <KEY>` |
| A Robot test is missing in Zephyr | It has no Zephyr key tag (see `unmapped_robot_tests` in the sync output) |
| The agents can't read the app repos | Add the paths to `.claude/settings.local.json` → `additionalDirectories` |
| A permission prompt appears on a `--dry-run` | Expected: dry-runs match the same `ask` rule as the real write |
| `sync` / `create-bug` / `create-mr` exits with code 3 | The draft isn't approved, or the test cases changed after approval. Approve it through `/qe-testcases`, `/qe-bugs` or `/qe-pr` |
