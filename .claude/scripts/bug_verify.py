#!/usr/bin/env python3
"""Bug verification helper for /qe-bug-verify. All output is JSON on stdout.

  bug_verify.py find BUGKEY [--story KEY]
      Finds the story and bug draft for a filed bug (06-bugs/*.md front matter jira_key, or state.bugs), its
      Zephyr keys, the Robot tests that carry them, and the ORIGINAL failure signature (failing keyword +
      normalised message) from the run the bug was found in. Caches it in state.bug_verification.<BUG>.
      Exit 4: no story workspace references the bug (pass --story).

  bug_verify.py compare BUGKEY --story KEY --results FILE
      Compares a retest run (run_robot.py --out FILE) with the original signature and proposes a verdict:
        verified       every linked test passed on the first attempt
        still_failing  at least one linked test fails the same way as before
        new_failure    a linked test fails, but differently (regression, test defect or env: triage it)
        flaky          passed only on the rerun: inconclusive, not verified
        blocked        a linked test did not run (skipped, missing, blocked-* tag)
      The agent confirms or overrides it with evidence. Saves the proposal in state.bug_verification.<BUG>.

  bug_verify.py record BUGKEY --story KEY --verdict VERDICT --report PATH [--comment-id ID]
      Appends the final (agent-confirmed) verdict to state.bug_verification.<BUG>.history.
"""
from __future__ import annotations

import argparse
import difflib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from common import (STORIES_DIR, die, out, read_front_matter, read_json, repo_root, story_dir, validate_key,
                    write_json)

RUN_REF_RE = re.compile(r"results/((?:run|verify)-\d+)")
SAME_THRESHOLD = 0.8


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalise(msg: str) -> str:
    s = (msg or "").lower()
    s = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<uuid>", s)
    s = re.sub(r"\b[0-9a-f]{16,}\b", "<hex>", s)
    s = re.sub(r"\d+", "#", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:300]


def signature(test: dict) -> dict:
    chain = test.get("failing_keywords") or []
    return {"test": test.get("name"), "status": test.get("status"),
            "deepest_keyword": chain[-1]["keyword"] if chain else None,
            "message": (test.get("message") or "")[:500], "message_norm": normalise(test.get("message") or "")}


def same_failure(a: dict, b: dict) -> tuple[bool, float]:
    ratio = difflib.SequenceMatcher(None, a.get("message_norm", ""), b.get("message_norm", "")).ratio()
    kw_same = (a.get("deepest_keyword") or "") == (b.get("deepest_keyword") or "")
    return (ratio >= SAME_THRESHOLD and kw_same) or ratio >= 0.95, round(ratio, 2)


# --------------------------------------------------------------------------- locate
def locate(bug: str, story: str | None) -> tuple[str, Path | None, dict]:
    stories_root = repo_root() / STORIES_DIR
    candidates = [story_dir(story)] if story else sorted(p for p in stories_root.glob("*") if p.is_dir())
    for sd in candidates:
        for d in sorted((sd / "06-bugs").glob("*.md")):
            try:
                meta, _ = read_front_matter(d)
            except SystemExit:
                continue
            if str(meta.get("jira_key") or "").upper() == bug:
                return sd.name, d, meta
        st_p = sd / "state.json"
        if st_p.is_file():
            for b in read_json(st_p).get("bugs") or []:
                if str(b.get("jira_key") or "").upper() == bug:
                    dp = Path(b["draft"]) if b.get("draft") else None
                    if dp and not dp.is_absolute():
                        dp = repo_root() / dp
                    meta = read_front_matter(dp)[0] if dp and dp.is_file() else {}
                    return sd.name, dp if dp and dp.is_file() else None, meta
    if story:
        return story, None, {}
    die(f"No story workspace in {STORIES_DIR}/ references {bug}. Pass --story <KEY>.", code=4)
    raise AssertionError


def _run_summary(run_dir: Path) -> dict | None:
    xml = run_dir / "output.xml"
    if not xml.is_file():
        return None
    try:
        from robot_summary import merge_rerun, summarize
    except SystemExit:
        return None
    s = summarize(str(xml))
    if (run_dir / "rerun.xml").is_file():
        s = merge_rerun(s, summarize(str(run_dir / "rerun.xml")))
    return s


def original_signatures(sd: Path, meta: dict, body: str, zkeys: list[str]) -> tuple[str | None, dict, list[str]]:
    warnings = []
    run_ref = meta.get("found_in_run")
    if not run_ref:
        refs = RUN_REF_RE.findall(" ".join(map(str, meta.get("attachments") or [])) + " " + body)
        run_ref = refs[0] if refs else None
    runs = sorted((p for p in (sd / "results").glob("run-*") if p.name.split("-")[1].isdigit()),
                  key=lambda p: int(p.name.split("-")[1]), reverse=True)
    order = ([sd / "results" / Path(run_ref).name] if run_ref else []) + runs
    for rd in order:
        s = _run_summary(rd)
        if s is None:
            continue
        sigs = {}
        for t in s["tests"]:
            for zk in t.get("zephyr_keys") or []:
                if zk in zkeys and t["status"] == "FAIL":
                    sigs[zk] = signature(t)
        if sigs:
            if run_ref and rd.name != Path(run_ref).name:
                warnings.append(f"{run_ref} not readable; used the latest run where the tests failed: {rd.name}")
            return str(rd.relative_to(repo_root())), sigs, warnings
    warnings.append("Original failure not found in results/run-*/output.xml (or robotframework is not importable). "
                    "Verdicts can still be pass/blocked; any failure is reported as new_failure.")
    return None, {}, warnings


def find(bug: str, story: str | None) -> dict:
    story_key, draft, meta = locate(bug, story)
    sd = story_dir(story_key)
    body = draft.read_text(encoding="utf-8") if draft else ""
    zkeys = [str(k).upper() for k in (meta.get("zephyr_keys") or [])]
    st_p = sd / "state.json"
    st = read_json(st_p) if st_p.is_file() else {}
    bv = (st.get("bug_verification") or {}).get(bug) or {}

    if not zkeys:
        zkeys = bv.get("zephyr_keys") or []
    from robot_catalog import tests_catalog
    tests = [t for t in tests_catalog() if set(t["zephyr_keys"]) & set(zkeys)]
    if bv.get("original"):
        orig_run, sigs, warnings = bv["original"].get("run_dir"), bv["original"].get("signatures", {}), []
    else:
        orig_run, sigs, warnings = original_signatures(sd, meta, body, zkeys)
    if not zkeys:
        warnings.append("The bug draft lists no zephyr_keys. Pass them to the agent, or add them to the draft.")
    missing = [k for k in zkeys if not any(k in t["zephyr_keys"] for t in tests)]
    if missing:
        warnings.append(f"No Robot test is tagged with: {', '.join(missing)}")

    if st_p.is_file():
        entry = st.setdefault("bug_verification", {}).setdefault(bug, {})
        entry.update(story=story_key, zephyr_keys=zkeys,
                     draft=str(draft.relative_to(repo_root())) if draft else None)
        if sigs and not entry.get("original"):
            entry["original"] = {"run_dir": orig_run, "signatures": sigs, "captured_at": now()}
        write_json(st_p, st)

    return {"ok": True, "bug": bug, "story": story_key,
            "draft": str(draft.relative_to(repo_root())) if draft else None,
            "title": meta.get("title"), "severity": meta.get("severity"), "zephyr_keys": zkeys,
            "robot_tests": [{"name": t["name"], "file": t["file"], "line": t["line"], "zephyr_keys": t["zephyr_keys"],
                             "blocked": t["blocked"]} for t in tests],
            "original_run": orig_run, "original_signatures": sigs,
            "previous_verifications": bv.get("history", []),
            "include_tags": zkeys,
            "run_command": (f"python3 .claude/scripts/run_robot.py {story_key} --include {' '.join(zkeys)} "
                            f"--run-prefix verify --out verify-{bug}.json [--env <env>]") if zkeys else None,
            "warnings": warnings}


# --------------------------------------------------------------------------- compare
def compare(bug: str, story: str, results_file: str) -> dict:
    sd = story_dir(story)
    rp = Path(results_file)
    if not rp.is_absolute():
        rp = (repo_root() / rp) if (repo_root() / rp).is_file() else sd / rp
    if not rp.is_file():
        die(f"Results file not found: {rp}")
    res = read_json(rp)
    st_p = sd / "state.json"
    st = read_json(st_p) if st_p.is_file() else {}
    bv = (st.get("bug_verification") or {}).get(bug) or {}
    zkeys = bv.get("zephyr_keys") or []
    if not zkeys:
        die(f"No Zephyr keys recorded for {bug}. Run: bug_verify.py find {bug} --story {story}")
    sigs = (bv.get("original") or {}).get("signatures") or {}

    per_key = []
    for zk in zkeys:
        runs = [t for t in res.get("tests", []) if zk in (t.get("zephyr_keys") or [])]
        if not runs:
            per_key.append({"zephyr_key": zk, "verdict": "blocked", "reason": "no test with this tag ran"})
            continue
        for t in runs:
            row = {"zephyr_key": zk, "test": t["name"], "status": t["status"], "flaky": bool(t.get("flaky"))}
            if t["status"] == "SKIP" or any(str(x).lower().startswith("blocked-") for x in t.get("tags", [])):
                row.update(verdict="blocked", reason=t.get("message") or "skipped / blocked tag")
            elif t["status"] == "PASS" and t.get("flaky"):
                row.update(verdict="flaky", reason="failed on the first attempt, passed on rerun",
                           first_attempt=(t.get("first_attempt") or {}).get("message", "")[:300])
            elif t["status"] == "PASS":
                row.update(verdict="pass")
            else:
                now_sig = signature(t)
                orig = sigs.get(zk)
                if orig:
                    same, ratio = same_failure(orig, now_sig)
                    row.update(verdict="still_failing" if same else "new_failure", similarity=ratio,
                               original={"deepest_keyword": orig.get("deepest_keyword"), "message": orig.get("message")})
                else:
                    row.update(verdict="new_failure", reason="no original signature to compare with")
                row["now"] = {"deepest_keyword": now_sig["deepest_keyword"], "message": now_sig["message"],
                              "screenshots": t.get("screenshots", [])}
            per_key.append(row)

    verdicts = {r["verdict"] for r in per_key}
    overall = next(v for v in ("still_failing", "new_failure", "blocked", "flaky", "verified")
                   if v in verdicts or (v == "verified" and verdicts <= {"pass"}))
    proposal = {"at": now(), "results": str(rp.relative_to(repo_root())), "run_dir": res.get("run_dir"),
                "env": res.get("environment"), "proposed_verdict": overall,
                "counts": {v: sum(r["verdict"] == v for r in per_key) for v in sorted(verdicts)}}
    if st_p.is_file():
        entry = st.setdefault("bug_verification", {}).setdefault(bug, {})
        entry["last_proposal"] = proposal
        write_json(st_p, st)
    return {"ok": True, "bug": bug, "story": story, **proposal, "per_test": per_key}


VERDICTS = {"verified", "still_failing", "new_failure", "flaky", "blocked", "not_deployed"}


def record(bug: str, story: str, verdict: str, report: str, comment_id: str | None) -> dict:
    if verdict not in VERDICTS:
        die(f"Unknown verdict {verdict}. Valid: {sorted(VERDICTS)}")
    st_p = story_dir(story) / "state.json"
    if not st_p.is_file():
        die(f"No state for {story}.")
    st = read_json(st_p)
    entry = st.setdefault("bug_verification", {}).setdefault(bug, {})
    last = entry.get("last_proposal") or {}
    item = {"at": now(), "verdict": verdict, "proposed": last.get("proposed_verdict"), "env": last.get("env"),
            "run_dir": last.get("run_dir"), "report": report, "comment_id": comment_id}
    entry.setdefault("history", []).append(item)
    entry["verdict"] = verdict
    write_json(st_p, st)
    return {"ok": True, "bug": bug, **item}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("find"); f.add_argument("bug"); f.add_argument("--story")
    c = sub.add_parser("compare"); c.add_argument("bug"); c.add_argument("--story", required=True)
    c.add_argument("--results", required=True)
    r = sub.add_parser("record"); r.add_argument("bug"); r.add_argument("--story", required=True)
    r.add_argument("--verdict", required=True); r.add_argument("--report", required=True)
    r.add_argument("--comment-id")
    a = ap.parse_args()
    bug = validate_key(a.bug)
    if a.cmd == "find":
        out(find(bug, validate_key(a.story) if a.story else None))
    elif a.cmd == "compare":
        out(compare(bug, validate_key(a.story), a.results))
    else:
        out(record(bug, validate_key(a.story), a.verdict, a.report, a.comment_id))


if __name__ == "__main__":
    sys.exit(main())
