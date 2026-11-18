#!/usr/bin/env python3
"""Zephyr Scale Cloud helper (API v2). All output is JSON on stdout.

Read-only:
  zephyr_cli.py list --issue KEY                 # test cases already linked to the story
  zephyr_cli.py get TESTKEY                      # one test case (+ steps)

Write:
  zephyr_cli.py sync KEY [--file PATH] [--dry-run]
      Creates every test case in .stories/KEY/03-test-cases.json that has no zephyr_key,
      adds its steps, links it to the story and writes the new key back to the file.
      Idempotent: a test case already linked to the story with the same name is adopted.
  zephyr_cli.py create-cycle KEY --name NAME [--dry-run]
  zephyr_cli.py post-executions KEY --cycle CYCLEKEY [--results PATH] [--environment NAME] [--dry-run]
      Low-level: posts Robot results (.stories/KEY/05-results.json) as executions in the cycle.
  zephyr_cli.py sync-results KEY [--env ENV] [--cycle CYCLEKEY] [--dry-run]
      MANDATORY after every triage. Reuses or creates the story's cycle for the environment, posts every
      result with its triage notes, posts locator-blocked cases as Blocked, and saves the execution ids in state.
  zephyr_cli.py link-bug KEY --bug BUGKEY [--zephyr-keys K ...] [--dry-run]
      Links a filed bug to the latest execution of its Zephyr test cases.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from common import Http, config, die, env, out, read_json, repo_root, story_dir, validate_key, write_json


def client(dry_run: bool = False) -> Http:
    cfg = config()["zephyr"]
    return Http(cfg.get("base_url", "https://api.zephyrscale.smartbear.com/v2"),
                headers={"Authorization": f"Bearer {env('ZEPHYR_API_TOKEN')}",
                         "Content-Type": "application/json"},
                dry_run=dry_run)


def jira_issue_id(key: str) -> int:
    from jira_cli import issue_id
    return int(issue_id(key))


# --------------------------------------------------------------------------- read
def list_for_issue(key: str) -> list[dict]:
    z = client()
    links = z.get(f"issuelinks/{key}/testcases") or []
    result = []
    for l in links:
        tc = z.get(f"testcases/{l['key']}")
        result.append({"key": tc["key"], "name": tc["name"], "status": (tc.get("status") or {}).get("id"),
                       "labels": tc.get("labels", []), "version": l.get("version")})
    return result


def get_tc(tkey: str) -> dict:
    z = client()
    tc = z.get(f"testcases/{tkey}")
    try:
        tc["steps"] = z.get(f"testcases/{tkey}/teststeps", params={"maxResults": 100}).get("values", [])
    except SystemExit:
        tc["steps"] = []
    return tc


# --------------------------------------------------------------------------- write
def sync(key: str, file: str | None, dry_run: bool) -> dict:
    cfg = config()["zephyr"]
    path = Path(file) if file else story_dir(key) / "03-test-cases.json"
    if not path.is_absolute():
        path = repo_root() / path
    doc = read_json(path)
    tcs = doc.get("test_cases") or []
    if not tcs:
        die(f"No test_cases in {path}")

    z = client(dry_run)
    existing = {} if dry_run else {t["name"].strip().lower(): t["key"] for t in list_for_issue(key)}
    issue_id = None if dry_run else jira_issue_id(key)
    created, adopted, skipped = [], [], []

    for tc in tcs:
        if tc.get("zephyr_key"):
            skipped.append(tc["zephyr_key"])
            continue
        name = tc["name"].strip()
        if name.lower() in existing:
            tc["zephyr_key"] = existing[name.lower()]
            adopted.append(tc["zephyr_key"])
            continue
        labels = sorted(set((cfg.get("labels") or []) + (tc.get("labels") or []) + [tc.get("type", ""), key]) - {""})
        body = {
            "projectKey": cfg["project_key"],
            "name": name[:255],
            "objective": _html(tc.get("objective", "")) + _ac_line(tc),
            "precondition": _html(tc.get("precondition", "")),
            "priorityName": tc.get("priority") or cfg.get("default_priority", "Normal"),
            "statusName": cfg.get("default_status", "Draft"),
            "labels": labels,
        }
        if cfg.get("folder_id"):
            body["folderId"] = cfg["folder_id"]
        res = z.post("testcases", json=body)
        tkey = res.get("key", f"DRY-{tc.get('local_id', len(created) + 1)}")

        steps = [{"inline": {"description": _html(s.get("description", "")),
                             "testData": _html(s.get("test_data", "")),
                             "expectedResult": _html(s.get("expected_result", ""))}}
                 for s in tc.get("steps", [])]
        if steps:
            z.post(f"testcases/{tkey}/teststeps", json={"mode": "OVERWRITE", "items": steps})
        if issue_id is not None:
            z.post(f"testcases/{tkey}/links/issues", json={"issueId": issue_id})
        if not dry_run:
            tc["zephyr_key"] = tkey
        created.append({"local_id": tc.get("local_id"), "key": tkey, "name": name})

    if not dry_run:
        write_json(path, doc)
    return {"ok": True, "dry_run": dry_run, "file": str(path), "created": created,
            "adopted_existing": adopted, "already_had_key": skipped}


def _html(s: str) -> str:
    """Zephyr fields accept simple HTML; keep line breaks."""
    return (s or "").replace("\n", "<br>")


def _ac_line(tc: dict) -> str:
    return f"<br><br><b>Covers:</b> {', '.join(tc['ac_ids'])}" if tc.get("ac_ids") else ""


def create_cycle(key: str, name: str, dry_run: bool) -> dict:
    cfg = config()["zephyr"]
    body = {"projectKey": cfg["project_key"], "name": name,
            "description": f"Automated run for {key} (QE agent harness)"}
    if cfg.get("cycle_folder_id"):
        body["folderId"] = cfg["cycle_folder_id"]
    z = client(dry_run)
    res = z.post("testcycles", json=body)
    ckey = res.get("key", "DRY-CYCLE")
    if not dry_run:
        z.post(f"testcycles/{ckey}/links/issues", json={"issueId": jira_issue_id(key)})
    return {"ok": True, "dry_run": dry_run, "cycle_key": ckey}


def post_executions(key: str, cycle: str, results: str | None, environment: str | None, dry_run: bool) -> dict:
    cfg = config()["zephyr"]
    smap = cfg.get("status_map") or {"PASS": "Pass", "FAIL": "Fail", "SKIP": "Not Executed"}
    path = Path(results) if results else story_dir(key) / "05-results.json"
    data = read_json(path)
    z = client(dry_run)
    posted, unmapped = [], []
    for t in data.get("tests", []):
        tkeys = t.get("zephyr_keys") or []
        if not tkeys:
            unmapped.append(t["name"])
            continue
        for tk in tkeys:
            body = {"projectKey": cfg["project_key"], "testCaseKey": tk, "testCycleKey": cycle,
                    "statusName": smap.get(t["status"], t["status"]),
                    "executionTime": int(t.get("elapsed_ms") or 0),
                    "comment": (t.get("triage_category", "") + " " + (t.get("message") or ""))[:4000].strip()}
            if environment:
                body["environmentName"] = environment
            z.post("testexecutions", json=body)
            posted.append({"test": t["name"], "zephyr_key": tk, "status": body["statusName"]})
    return {"ok": True, "dry_run": dry_run, "cycle": cycle, "posted": posted, "unmapped_tests": unmapped}


def _comment(t: dict) -> str:
    parts = [f"<b>Robot test:</b> {t.get('longname', t['name'])}"]
    if t.get("triage_category"):
        parts.append(f"<b>Triage:</b> {t['triage_category']} ({t.get('triage_confidence', 'n/a')}) — "
                     f"{t.get('triage_summary', '')}")
    if t.get("flaky"):
        parts.append(f"<b>Flaky:</b> failed on the first attempt and passed on re-run "
                     f"({(t.get('first_attempt') or {}).get('message', '')[:300]})")
    elif t["status"] == "FAIL" and t.get("message"):
        parts.append(f"<b>Failure:</b> {t['message'][:1500]}")
    return "<br>".join(parts)[:4000]


def sync_results(key: str, env_name: str | None, cycle: str | None, dry_run: bool) -> dict:
    """Push the latest run (05-results.json + triage fields) to Zephyr Scale.

    - Reuses one test cycle per story and environment (state: zephyr.test_cycles[env]), creating it on first use.
    - Posts one execution per Zephyr key on each Robot test. Re-runs add new executions to the same cycle,
      and Zephyr shows the latest one.
    - Test cases that could not be automated because of a locator gap are posted as Blocked.
    - Saves the execution ids to state (zephyr.executions), so `link-bug` can attach filed bugs.
    """
    cfg = config()["zephyr"]
    sd = story_dir(key)
    results = read_json(sd / "05-results.json")
    env_name = env_name or results.get("environment") or config().get("robot", {}).get("default_env", "qa")
    state_p = sd / "state.json"
    st = read_json(state_p) if state_p.is_file() else {}
    zst = st.setdefault("zephyr", {})
    cycles = zst.setdefault("test_cycles", {})

    cycle = cycle or cycles.get(env_name)
    created_cycle = False
    if not cycle:
        cycle = create_cycle(key, f"{key} | {env_name.upper()} | Automated regression", dry_run)["cycle_key"]
        created_cycle = True

    smap = cfg.get("status_map") or {"PASS": "Pass", "FAIL": "Fail", "SKIP": "Not Executed"}
    zenv = (cfg.get("environment_map") or {}).get(env_name)
    z = client(dry_run)
    posted, unmapped, executed = [], [], set()

    def post(tk: str, status: str, comment: str, elapsed: int = 0) -> None:
        body = {"projectKey": cfg["project_key"], "testCaseKey": tk, "testCycleKey": cycle,
                "statusName": status, "executionTime": int(elapsed), "comment": comment}
        if zenv:
            body["environmentName"] = zenv
        res = z.post("testexecutions", json=body)
        posted.append({"zephyr_key": tk, "status": status, "execution_id": res.get("id")})

    for t in results.get("tests", []):
        keys = t.get("zephyr_keys") or []
        if not keys:
            unmapped.append(t["name"])
            continue
        for tk in keys:
            executed.add(tk)
            post(tk, smap.get(t["status"], t["status"]), _comment(t), t.get("elapsed_ms") or 0)

    blocked = []
    tc_path = sd / "03-test-cases.json"
    if tc_path.is_file():
        for tc in read_json(tc_path).get("test_cases", []):
            tk, auto = tc.get("zephyr_key"), (tc.get("automation") or {})
            if tk and tk not in executed and str(auto.get("status", "")).startswith("blocked"):
                post(tk, cfg.get("blocked_status", "Blocked"),
                     f"<b>Not automated:</b> {auto.get('status')} — {auto.get('notes') or 'see 04-automation.md'}")
                blocked.append(tk)

    if not dry_run and state_p.is_file():
        from datetime import datetime, timezone
        cycles[env_name] = cycle
        execs = zst.setdefault("executions", {})
        for p in posted:
            execs[p["zephyr_key"]] = {"execution_id": p["execution_id"], "status": p["status"],
                                      "cycle": cycle, "env": env_name, "run_dir": results.get("run_dir")}
        zst["last_sync"] = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "cycle": cycle,
                            "env": env_name, "run_dir": results.get("run_dir"), "posted": len(posted)}
        write_json(state_p, st)

    return {"ok": True, "dry_run": dry_run, "cycle": cycle, "cycle_created": created_cycle, "env": env_name,
            "zephyr_environment": zenv, "posted": len(posted),
            "by_status": {s: sum(p["status"] == s for p in posted) for s in {p["status"] for p in posted}},
            "blocked_posted": blocked, "unmapped_robot_tests": unmapped}


def link_bug(key: str, bug_key: str, zephyr_keys: list[str] | None, dry_run: bool) -> dict:
    """Link a filed Jira bug to the latest Zephyr execution of each affected test case."""
    sd = story_dir(key)
    if not zephyr_keys:  # take them from the filed bug draft
        from common import read_front_matter
        for d in sorted((sd / "06-bugs").glob("*.md")):
            meta, _ = read_front_matter(d)
            if meta.get("jira_key") == bug_key:
                zephyr_keys = meta.get("zephyr_keys") or []
                break
    if not zephyr_keys:
        die(f"No Zephyr keys found for {bug_key}. Pass --zephyr-keys.")
    execs = read_json(sd / "state.json").get("zephyr", {}).get("executions", {})
    z = client(dry_run)
    issue_id = None if dry_run else jira_issue_id(bug_key)
    linked, missing = [], []
    for tk in zephyr_keys:
        ex = (execs.get(tk) or {}).get("execution_id")
        if not ex:
            missing.append(tk)
            continue
        z.post(f"testexecutions/{ex}/links/issues", json={"issueId": issue_id})
        linked.append({"zephyr_key": tk, "execution_id": ex})
    return {"ok": True, "dry_run": dry_run, "bug": bug_key, "linked": linked,
            "no_execution_found": missing}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list"); ls.add_argument("--issue", required=True)
    sub.add_parser("get").add_argument("testkey")
    sy = sub.add_parser("sync"); sy.add_argument("key"); sy.add_argument("--file"); sy.add_argument("--dry-run", action="store_true")
    cc = sub.add_parser("create-cycle"); cc.add_argument("key"); cc.add_argument("--name", required=True)
    cc.add_argument("--dry-run", action="store_true")
    pe = sub.add_parser("post-executions"); pe.add_argument("key"); pe.add_argument("--cycle", required=True)
    pe.add_argument("--results"); pe.add_argument("--environment"); pe.add_argument("--dry-run", action="store_true")
    sr = sub.add_parser("sync-results"); sr.add_argument("key"); sr.add_argument("--env"); sr.add_argument("--cycle")
    sr.add_argument("--dry-run", action="store_true")
    lb = sub.add_parser("link-bug"); lb.add_argument("key"); lb.add_argument("--bug", required=True)
    lb.add_argument("--zephyr-keys", nargs="*"); lb.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.cmd == "sync-results":
        out(sync_results(validate_key(a.key), a.env, a.cycle, a.dry_run))
    elif a.cmd == "link-bug":
        out(link_bug(validate_key(a.key), validate_key(a.bug), a.zephyr_keys, a.dry_run))
    elif a.cmd == "list":
        tcs = list_for_issue(validate_key(a.issue))
        out({"issue": a.issue, "count": len(tcs), "test_cases": tcs})
    elif a.cmd == "get":
        out(get_tc(a.testkey))
    elif a.cmd == "sync":
        out(sync(validate_key(a.key), a.file, a.dry_run))
    elif a.cmd == "create-cycle":
        out(create_cycle(validate_key(a.key), a.name, a.dry_run))
    elif a.cmd == "post-executions":
        out(post_executions(validate_key(a.key), a.cycle, a.results, a.environment, a.dry_run))


if __name__ == "__main__":
    main()
