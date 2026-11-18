# QE Agent Harness for Claude Code

A Claude Code harness that takes one Jira user story for the loan application portal from requirements to
automated tests, synced results, bugs and a merge request:

```
/qe-manager LOAN-123   (QE Manager skill: runs in the main session, owns the gates and human approvals)
 1 story         jira-user-story           Jira → .stories/LOAN-123/01-story.md (ACs, attachments, api/ui/both)
 2 traceability  requirement-traceability  static analysis of React / Go / Spring Boot / MySQL against the ACs → score
                 ── GATE: score ≥ 75% (.claude/scripts/trace_score.py): stop / override with a reason / re-scan
 3 test_cases    zephyr-test-case          designs test cases → Zephyr Scale (linked to the story)
 4 automation    robot-automation          Robot (Browser + RequestsLibrary); data-testid locators only
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
| Piece | Where | Model | Role |
|---|---|---|---|
| QE Manager | `.claude/skills/qe-manager/SKILL.md` | your session model (Sonnet is enough) | Orchestrator: delegates, enforces gates, asks for approvals |
| Jira User Story Agent | `.claude/agents/jira-user-story.md` | sonnet | Story, ACs, attachments (mockups/PDFs), test type |
| Requirement Traceability Agent | `.claude/agents/requirement-traceability.md` | opus | Code-vs-AC evidence matrix, 75% gate |
| Zephyr Test Case Agent | `.claude/agents/zephyr-test-case.md` | sonnet | Test design, creates and links Zephyr test cases |
| Robot Framework Automation Agent | `.claude/agents/robot-automation.md` | sonnet | Robot suites, data-testid locators, test-defect fixes |
| Triage Agent | `.claude/agents/triage.md` | opus | Runs tests, classifies failures, syncs results to Zephyr |
| Bug Agent | `.claude/agents/bug.md` | haiku | Bug drafts with duplicate check (no filing) |
| Pull Request Agent | `.claude/agents/pull-request.md` | haiku | Diff review, commit, MR draft (no push) |

**Why the QE Manager is a skill, not a subagent:** Claude Code subagents can't start other subagents, so the
orchestrator has to run in the main conversation. Each worker runs in its own context and returns a summary
of 15 lines or fewer, which keeps the main session small.

## Install into the Robot Framework test repo
1. Copy into the **root of the test repo**, merging with what is already there:
   - the whole `.claude/` folder (agents, skills, commands, scripts, templates, `qe.config.yaml`, `.env.example`, settings);
   - `CLAUDE.md` and `requirements-qe.txt`.
   Append the contents of `.gitignore` to the repo's `.gitignore`. If the repo already has a `CLAUDE.md`, merge
   the two and keep the "Robot Framework conventions" section accurate, because the automation agent follows it.
2. `pip install -r requirements-qe.txt`. Use the same virtualenv you run Robot from, and run `rfbrowser init`
   if you haven't already.
3. `cp .claude/.env.example .claude/.env` and fill in the Jira, Zephyr and GitLab tokens and the test user credentials.
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
6. Smoke test:
   ```bash
   python3 .claude/scripts/jira_cli.py get-story LOAN-123 | head -40      # check the ACs are extracted
   python3 .claude/scripts/zephyr_cli.py list --issue LOAN-123
   python3 .claude/scripts/testid_index.py --filter loan | head -40
   ```
7. In Claude Code, `/agents` should list the 7 agents, and typing `/qe-` should autocomplete `/qe-manager`
   and the per-phase commands. Restart Claude Code if they don't appear.

## Daily use: one story per context window

### Full flow
```
claude                                   # fresh session from the test repo root
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
| – | `/qe-status LOAN-123` | — | Progress and the next command to run |
| 1 | `/qe-story LOAN-123` | jira-user-story | |
| 2 | `/qe-trace LOAN-123 [--branch feat/x]` | requirement-traceability | 75% gate: stop / override / re-scan |
| 3 | `/qe-testcases LOAN-123` | zephyr-test-case | Needs the gate passed or overridden |
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

## Zephyr Scale integration
| When | What is written | Command |
|---|---|---|
| Phase 3 | Test cases with steps, labels and AC coverage, linked to the story. Idempotent: existing linked cases with the same name are reused | `zephyr_cli.py sync` (asks permission) |
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
- The Bug and PR agents only write drafts (`06-bugs/*.md`, `07-mr.md`) with `approval: pending`.
- The QE Manager shows you each draft. Only after you explicitly approve does it set `approval: approved` and
  `approved_by`.
- `jira_cli.py create-bug` and `gitlab_cli.py create-mr` **refuse** unapproved drafts with exit code 3.
- `.claude/settings.json` sets the permissions:
  - **ask:** `create-bug`, `add-comment`, `create-mr`, `git push`, `git commit`, and Zephyr test-case
    creation, cycle creation and execution posting run directly, so Claude Code prompts you.
  - **allow:** read-only commands, plus the required results sync (`sync-results`, `link-bug`).
  - **deny:** force-push and reading `.claude/.env`.
- Every command that writes externally supports `--dry-run`.

## Layout
```
<test repo root>/
├── .claude/
│   ├── agents/*.md                7 subagents (each with its model set)
│   ├── skills/qe-manager/         orchestrator skill (full flow, the only source of phase rules)
│   ├── commands/qe-*.md           one command per phase + /qe-status + /qe-sync-results
│   ├── scripts/                   Jira / Zephyr Scale / GitLab REST clients, gates, Robot runner/parser, testid index
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
| Symptom | Likely cause / fix |
|---|---|
| `get-story` returns `acceptance_criteria_md: null` | Set `jira.acceptance_criteria_field`, or make sure the description has an "Acceptance Criteria" heading |
| `run_robot.py` fails with rc 252 | No tests are tagged with the story key, or a suite path or syntax is wrong. Run `/qe-automate --fix` or check the tags |
| Zephyr sync fails | Check the token and `zephyr.project_key`. Names in `environment_map` and `status_map` must exist in Zephyr. Retry with `/qe-sync-results <KEY>` |
| A Robot test is missing in Zephyr | It has no Zephyr key tag (see `unmapped_robot_tests` in the sync output) |
| The agents can't read the app repos | Add the paths to `.claude/settings.local.json` → `additionalDirectories` |
| A permission prompt appears on a `--dry-run` | Expected: dry-runs match the same `ask` rule as the real write |
| `create-bug` / `create-mr` exits with code 3 | The draft isn't approved. Approve it through `/qe-bugs` / `/qe-pr` |
