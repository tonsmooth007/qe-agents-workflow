#!/usr/bin/env python3
"""Locator drift check for /qe-heal: data-testid locators used in this repo that no longer exist in the frontend.

  testid_drift.py check [--key KEY] [--scope STORYKEY ...] [--no-history]
      1. Collects every data-testid used in tests/ and resources/ (robot_catalog.py), optionally only the ones
         used by the tests of the --scope stories (their suites and the resources those suites import).
      2. Indexes the frontend repo(s) as they are checked out now (testid_index.py).
      3. Each locator is `ok`, `missing`, or `unverifiable` (the frontend builds some ids from JS expressions).
      4. For each missing id, reads the frontend git history (read-only `git log -S` / `git show`) to find the
         commit that removed it, and proposes replacements: testids added in the same file in that commit
         (`renamed_in_commit`), else current ids with a similar name (`similar_name`). The agent confirms them
         by reading the component.
      Writes .stories/<KEY>/heal/drift.json with --key, else .stories/_heal/<id>/drift.json.
"""
from __future__ import annotations

import argparse
import difflib
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from common import STORIES_DIR, config, out, repo_root, resolve_path, story_dir, validate_key, write_json


def git(path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True)


def frontend_index() -> tuple[list[dict], list[dict]]:
    from testid_index import scan_repo
    entries, repos = [], []
    for r in config().get("application_repos", {}).get("frontend", []) or []:
        root = resolve_path(r["path"])
        info = {"name": r["name"], "path": str(root), "src_dirs": r.get("src_dirs", ["src"])}
        if not root.is_dir():
            info["error"] = "repo path not found"
        else:
            e, _ = scan_repo(r["name"], root, info["src_dirs"])
            entries += e
            h = git(root, "rev-parse", "--short", "HEAD")
            b = git(root, "branch", "--show-current")
            info.update(head=h.stdout.strip(), branch=b.stdout.strip())
        repos.append(info)
    return entries, repos


def scoped_usages(usages: list[dict], scope: list[str] | None) -> tuple[list[dict], list[str]]:
    if not scope:
        return usages, []
    from robot_catalog import _parse, robot_files, tests_catalog
    want = {s.upper() for s in scope}
    tests = [t for t in tests_catalog() if want & set(t["story_keys"])]
    files = {t["file"] for t in tests}
    res_names = {Path(r).name for t in tests for r in t["resources"]}
    for _ in range(3):  # resources imported by those resources
        before = len(res_names)
        for rf in robot_files((".resource",)):
            if rf.name in res_names:
                res_names |= {Path(r).name for r in _parse(rf)["resources"]}
        if len(res_names) == before:
            break
    return [u for u in usages if u["file"] in files or Path(u["file"]).name in res_names], sorted(files)


def last_seen(repo: dict, tid: str) -> dict | None:
    root = Path(repo["path"])
    for needle in (f'data-testid="{tid}"', f"data-testid='{tid}'", f'"{tid}"', f"'{tid}'", f"`{tid}`"):
        r = git(root, "log", "-n", "1", "--format=%H|%h|%ad|%s", "--date=short", "-S", needle, "--",
                *repo["src_dirs"])
        line = r.stdout.strip()
        if r.returncode == 0 and line:
            full, short, date, subject = (line.split("|", 3) + ["", "", "", ""])[:4]
            return {"repo": repo["name"], "commit": short, "full": full, "date": date, "subject": subject[:200],
                    "needle": needle}
    return None


def renamed_candidates(repo: dict, seen: dict, tid: str) -> tuple[list[dict], list[str]]:
    from impact_map import parse_diff, testids_in
    r = git(Path(repo["path"]), "show", "--format=", "--no-color", "--no-ext-diff", "-M", "--unified=0", seen["full"])
    if r.returncode != 0:
        return [], []
    cands, files = [], []
    for f in parse_diff(r.stdout):
        if tid in testids_in(f["removed"]):
            files.append(f["path"])
            for new in testids_in(f["added"]) - testids_in(f["removed"]):
                cands.append({"testid": new, "file": f["path"],
                              "score": round(difflib.SequenceMatcher(None, tid, new).ratio(), 2)})
    return sorted(cands, key=lambda c: -c["score"]), files


def check(key: str | None, scope: list[str] | None, history: bool) -> dict:
    from impact_map import locator_hits
    from robot_catalog import locator_usages
    usages, scope_files = scoped_usages(locator_usages(), scope)
    entries, repos = frontend_index()
    ids = {e["testid"] for e in entries if e["kind"] in ("static", "template")}
    static_ids = sorted({e["testid"] for e in entries if e["kind"] == "static"})
    expr_count = sum(e["kind"] == "expression" for e in entries)
    where = {}
    for e in entries:
        where.setdefault(e["testid"], f"{e['repo']}/{e['file']}:{e['line']}")

    by_locator: dict[tuple[str, str], dict] = {}
    for u in usages:
        k = (u["testid"], u["op"])
        item = by_locator.setdefault(k, {"testid": u["testid"], "op": u["op"], "dynamic": u["dynamic"], "usages": []})
        item["usages"].append({"file": u["file"], "line": u["line"], "variable": u["variable"]})

    ok, missing, unverifiable = [], [], []
    live_repos = [r for r in repos if not r.get("error")]
    for item in by_locator.values():
        if locator_hits(item["testid"], item["op"], ids):
            item["status"] = "ok"
            item["found_at"] = next((where[t] for t in ids if locator_hits(item["testid"], item["op"], {t})), None)
            ok.append(item)
            continue
        if expr_count and item["dynamic"]:
            item["status"] = "unverifiable"
            item["note"] = "dynamic locator and the frontend builds some ids from JS expressions: read the component"
            unverifiable.append(item)
            continue
        item["status"] = "missing"
        item["candidates"], item["last_seen"] = [], None
        base = item["testid"].split("${")[0]
        if history and base:
            for repo in live_repos:
                seen = last_seen(repo, base if item["dynamic"] else item["testid"])
                if seen:
                    cands, files = renamed_candidates(repo, seen, item["testid"])
                    seen["files"] = files
                    item["last_seen"] = seen
                    hi = float((config().get("heal") or {}).get("high_confidence_score", 0.6))
                    item["candidates"] = [{**c, "source": "renamed_in_commit", "exists_now": c["testid"] in ids,
                                           "confidence": "high" if c["score"] >= hi and c["testid"] in ids else "low",
                                           "current_location": where.get(c["testid"])} for c in cands[:5]]
                    break
        if not item["candidates"]:
            for c in difflib.get_close_matches(base or item["testid"], static_ids, n=3, cutoff=0.6):
                item["candidates"].append({"testid": c, "source": "similar_name", "exists_now": True, "confidence": "low",
                                           "score": round(difflib.SequenceMatcher(None, item["testid"], c).ratio(), 2),
                                           "current_location": where.get(c)})
        if expr_count:
            item["note"] = "the frontend also builds ids from JS expressions; confirm in the component before healing"
        missing.append(item)

    from robot_catalog import tests_catalog
    affected = set()
    if missing:
        from robot_catalog import suites_using
        cat = tests_catalog()
        for m in missing:
            for u in m["usages"]:
                suites = {u["file"]} if u["file"].endswith(".robot") else suites_using(u["file"], cat)
                m.setdefault("affected_suites", [])
                m["affected_suites"] = sorted(set(m["affected_suites"]) | suites)
                affected |= suites
    aid = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = (story_dir(key) / "heal" / "drift.json") if key else (repo_root() / STORIES_DIR / "_heal" / aid / "drift.json")
    result = {"ok": True, "id": aid, "key": key, "scope": scope or "all",
              "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "frontend_repos": repos, "frontend_testids": len(entries), "expression_ids": expr_count,
              "counts": {"locators": len(by_locator), "ok": len(ok), "missing": len(missing),
                         "unverifiable": len(unverifiable)},
              "missing": missing, "unverifiable": unverifiable,
              "affected_suites": sorted(affected), "scope_suites": scope_files,
              "ok_locators": [{"testid": i["testid"], "op": i["op"], "found_at": i.get("found_at")} for i in ok]}
    write_json(dest, result)
    result["written"] = str(dest.relative_to(repo_root()))
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--key", help="Jira key the heal work is done under (writes .stories/KEY/heal/drift.json)")
    c.add_argument("--scope", nargs="*", help="Only locators used by these stories' tests")
    c.add_argument("--no-history", action="store_true", help="Skip the frontend git history lookup")
    a = ap.parse_args()
    out(check(validate_key(a.key) if a.key else None, [validate_key(s) for s in a.scope] if a.scope else None,
              not a.no_history))


if __name__ == "__main__":
    main()
