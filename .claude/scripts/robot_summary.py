#!/usr/bin/env python3
"""Turn a Robot Framework output.xml into a compact JSON summary for triage.

For each test: status, message, tags, Zephyr keys (tags like LOAN-T123), elapsed,
the failing keyword chain, recent WARN/ERROR/FAIL log lines and screenshot paths.

Usage:
  robot_summary.py OUTPUT_XML [--rerun RERUN_XML] [--write PATH]
"""
from __future__ import annotations

import argparse
import re
from datetime import timedelta
from pathlib import Path

from common import config, out, write_json

try:
    from robot.api import ExecutionResult
except ImportError:  # pragma: no cover
    raise SystemExit("robotframework is not installed in this environment (pip install -r requirements-qe.txt)")

IMG_RE = re.compile(r'(?:src|href)="([^"]+\.(?:png|jpe?g|webp))"', re.I)


def zephyr_tag_re() -> re.Pattern:
    proj = config().get("zephyr", {}).get("project_key", "[A-Z][A-Z0-9_]+")
    return re.compile(rf"^{proj}-T\d+$", re.I)


def _elapsed_ms(item) -> int:
    et = getattr(item, "elapsed_time", None)
    if isinstance(et, timedelta):
        return int(et.total_seconds() * 1000)
    return int(getattr(item, "elapsedtime", 0) or 0)


def _messages(item):
    msgs = list(getattr(item, "messages", []) or [])  # RF < 7
    for b in getattr(item, "body", []) or []:          # RF >= 7 puts messages in body
        if getattr(b, "type", "") == "MESSAGE":
            msgs.append(b)
    return msgs


def _children(item):
    out_ = []
    for b in getattr(item, "body", []) or []:
        if getattr(b, "type", "") == "MESSAGE":
            continue
        out_.append(b)
    for attr in ("setup", "teardown"):
        x = getattr(item, attr, None)
        if x is not None and getattr(x, "name", None):
            out_.append(x)
    return out_


def failing_chain(test) -> tuple[list[dict], list[str], list[str]]:
    """Walk down FAIL keywords to the deepest failure; collect logs + screenshots on the way."""
    chain, logs, shots = [], [], []

    def walk(item, depth=0):
        for m in _messages(item):
            text = getattr(m, "message", "") or ""
            for s in IMG_RE.findall(text):
                shots.append(s)
            if getattr(m, "level", "") in ("WARN", "ERROR", "FAIL"):
                logs.append(f"[{m.level}] {re.sub(r'<[^>]+>', '', text)[:500]}")
        for child in _children(item):
            walk_child = getattr(child, "status", "") == "FAIL"
            # screenshots may be logged by passing keywords (e.g. Take Screenshot in teardown)
            for m in _messages(child):
                text = getattr(m, "message", "") or ""
                for s in IMG_RE.findall(text):
                    shots.append(s)
                if not walk_child and getattr(m, "level", "") in ("WARN", "ERROR"):
                    logs.append(f"[{m.level}] {re.sub(r'<[^>]+>', '', text)[:500]}")
            if walk_child:
                name = getattr(child, "name", None) or getattr(child, "type", "")
                chain.append({"depth": depth, "keyword": name, "type": getattr(child, "type", ""),
                              "args": [str(a) for a in getattr(child, "args", [])][:6],
                              "message": (getattr(child, "message", "") or "")[:500]})
                walk(child, depth + 1)
                break  # follow first failure path only

    walk(test)
    return chain, list(dict.fromkeys(logs))[-15:], list(dict.fromkeys(shots))


def summarize(xml: str) -> dict:
    result = ExecutionResult(xml)
    ztag = zephyr_tag_re()
    tests = []

    def visit(suite):
        for t in suite.tests:
            chain, logs, shots = failing_chain(t) if t.status == "FAIL" else ([], [], [])
            tests.append({
                "name": t.name,
                "longname": getattr(t, "full_name", None) or t.longname,
                "source": str(getattr(t, "source", None) or suite.source or ""),
                "status": t.status,
                "message": (t.message or "")[:2000],
                "tags": list(t.tags),
                "zephyr_keys": [x.upper() for x in t.tags if ztag.match(x)],
                "elapsed_ms": _elapsed_ms(t),
                "failing_keywords": chain,
                "log_excerpt": logs,
                "screenshots": shots,
            })
        for s in suite.suites:
            visit(s)

    visit(result.suite)
    stats = {"total": len(tests), "pass": sum(t["status"] == "PASS" for t in tests),
             "fail": sum(t["status"] == "FAIL" for t in tests), "skip": sum(t["status"] == "SKIP" for t in tests)}
    stats["pass_rate"] = round(stats["pass"] / stats["total"] * 100, 2) if stats["total"] else 0.0
    return {"output_xml": str(Path(xml).resolve()), "stats": stats, "tests": tests}


def merge_rerun(first: dict, rerun: dict) -> dict:
    """Mark tests that failed first but passed on rerun as flaky; final status = rerun status."""
    rr = {t["longname"]: t for t in rerun["tests"]}
    for t in first["tests"]:
        r = rr.get(t["longname"])
        if t["status"] == "FAIL" and r:
            t["first_attempt"] = {"status": "FAIL", "message": t["message"]}
            t["flaky"] = r["status"] == "PASS"
            if r["status"] == "PASS":
                t["status"] = "PASS"
            else:
                t.update({k: r[k] for k in ("message", "failing_keywords", "log_excerpt", "screenshots")})
    tests = first["tests"]
    first["stats"] = {"total": len(tests), "pass": sum(t["status"] == "PASS" for t in tests),
                      "fail": sum(t["status"] == "FAIL" for t in tests),
                      "skip": sum(t["status"] == "SKIP" for t in tests),
                      "flaky": sum(bool(t.get("flaky")) for t in tests)}
    first["stats"]["pass_rate"] = round(first["stats"]["pass"] / len(tests) * 100, 2) if tests else 0.0
    first["rerun_xml"] = rerun["output_xml"]
    return first


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("output_xml")
    ap.add_argument("--rerun")
    ap.add_argument("--write")
    a = ap.parse_args()
    data = summarize(a.output_xml)
    if a.rerun and Path(a.rerun).is_file():
        data = merge_rerun(data, summarize(a.rerun))
    if a.write:
        write_json(a.write, data)
    out(data)


if __name__ == "__main__":
    main()
