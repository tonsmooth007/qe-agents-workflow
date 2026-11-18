#!/usr/bin/env python3
"""Per-story state machine stored in .stories/<KEY>/state.json.

This file is the hand-off between context windows: the QE Manager reads it to
know which phase to resume from.

Usage:
  story_state.py init KEY
  story_state.py get KEY                       # full JSON
  story_state.py status KEY                    # compact table + next phase
  story_state.py set-phase KEY PHASE STATUS [--note TEXT] [--artifact PATH ...]
  story_state.py set KEY dotted.path JSON_VALUE   # e.g. set LOAN-1 gates.traceability.override '"PO accepted"'
  story_state.py log KEY "message"
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from common import die, out, read_json, story_dir, validate_key, write_json

PHASES = [
    ("story", "jira-user-story", "01-story.md"),
    ("traceability", "requirement-traceability", "02-traceability.json"),
    ("test_cases", "zephyr-test-case", "03-test-cases.json"),
    ("automation", "robot-automation", "04-automation.md"),
    ("triage", "triage", "05-triage-report.md"),
    ("bugs", "bug", "06-bugs"),
    ("pr", "pull-request", "07-mr.md"),
]
STATUSES = {"pending", "in_progress", "done", "blocked", "skipped", "failed"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def path(key: str):
    return story_dir(key) / "state.json"


def load(key: str) -> dict:
    p = path(key)
    if not p.is_file():
        die(f"No state for {key}. Run: story_state.py init {key}")
    return read_json(p)


def save(key: str, st: dict) -> None:
    st["updated_at"] = now()
    write_json(path(key), st)


def init(key: str) -> dict:
    p = path(key)
    if p.is_file():
        return read_json(p)
    st = {
        "story": key,
        "created_at": now(),
        "updated_at": now(),
        "test_type": None,  # api | ui | both  (set by jira-user-story agent)
        "branch": None,
        "phases": {
            name: {"agent": agent, "status": "pending", "artifact": artifact, "note": None, "updated_at": None}
            for name, agent, artifact in PHASES
        },
        "gates": {"traceability": {"score": None, "threshold": None, "passed": None, "override": None}},
        "triage_loops": 0,
        "zephyr": {"test_cases": [], "test_cycles": {}, "executions": {}, "last_sync": None},
        "bugs": [],  # [{draft, jira_key, status}]
        "mr": {"url": None, "status": None},
        "log": [],
    }
    save(key, st)
    return st


def next_phase(st: dict) -> str | None:
    for name, _, _ in PHASES:
        if st["phases"][name]["status"] not in ("done", "skipped"):
            return name
    return None


def status_view(st: dict) -> dict:
    rows = [
        {"phase": n, "agent": st["phases"][n]["agent"], "status": st["phases"][n]["status"],
         "note": st["phases"][n].get("note")}
        for n, _, _ in PHASES
    ]
    return {
        "story": st["story"],
        "test_type": st.get("test_type"),
        "branch": st.get("branch"),
        "traceability": st["gates"]["traceability"],
        "phases": rows,
        "next_phase": next_phase(st),
        "bugs": st.get("bugs", []),
        "mr": st.get("mr"),
    }


def set_dotted(d: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    for p in parts[:-1]:
        d = d.setdefault(p, {})
    d[parts[-1]] = value


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("init", "get", "status"):
        sub.add_parser(c).add_argument("key")
    sp = sub.add_parser("set-phase")
    sp.add_argument("key"); sp.add_argument("phase"); sp.add_argument("status")
    sp.add_argument("--note"); sp.add_argument("--artifact", nargs="*")
    s = sub.add_parser("set")
    s.add_argument("key"); s.add_argument("path"); s.add_argument("value", help="JSON value")
    lg = sub.add_parser("log")
    lg.add_argument("key"); lg.add_argument("message")
    a = ap.parse_args()
    key = validate_key(a.key)

    if a.cmd == "init":
        out(status_view(init(key)))
        return
    st = load(key)
    if a.cmd == "get":
        out(st)
    elif a.cmd == "status":
        out(status_view(st))
    elif a.cmd == "set-phase":
        if a.phase not in st["phases"]:
            die(f"Unknown phase {a.phase}. Valid: {[p[0] for p in PHASES]}")
        if a.status not in STATUSES:
            die(f"Unknown status {a.status}. Valid: {sorted(STATUSES)}")
        ph = st["phases"][a.phase]
        ph.update(status=a.status, updated_at=now())
        if a.note is not None:
            ph["note"] = a.note
        if a.artifact:
            ph["artifacts"] = a.artifact
        st["log"].append({"at": now(), "msg": f"{a.phase} -> {a.status}" + (f": {a.note}" if a.note else "")})
        save(key, st)
        out(status_view(st))
    elif a.cmd == "set":
        try:
            val = json.loads(a.value)
        except json.JSONDecodeError:
            val = a.value
        set_dotted(st, a.path, val)
        st["log"].append({"at": now(), "msg": f"set {a.path}"})
        save(key, st)
        out({"ok": True, a.path: val})
    elif a.cmd == "log":
        st["log"].append({"at": now(), "msg": a.message})
        save(key, st)
        out({"ok": True})


if __name__ == "__main__":
    main()
