#!/usr/bin/env python3
"""Change-impact analysis for /qe-impact: which stories, ACs, Zephyr test cases and Robot tests does a change in
the application repos touch? All output is JSON on stdout.

  impact_map.py analyze (--range A..B | --repo NAME=A..B ...) [--only NAME ...] [--context N]
      Diffs the application repos (read-only `git diff`, nothing is fetched or checked out) and maps the changes:
        1. traceability evidence: every .stories/*/02-traceability.json evidence entry (repo, file, line) and
           discovered endpoint/route/migration in a changed file. "line" when the evidence line is inside a
           changed hunk (± --context lines, default impact.line_context), "file" otherwise.
        2. data-testids: testids removed, added or touched in the frontend diff, matched against the locators
           used in this repo's tests/resources (removed = the test will break → /qe-heal).
        3. ACs → test cases (03-test-cases.json ac_ids) → Robot tests (tags), across every story.
      Changed source files that no traceability evidence covers are listed as `unmapped_changes`.
      Writes .stories/_impact/<id>/impact.json and prints it.

  impact_map.py show <id>          # re-print a saved analysis

--range applies to every application repo; --repo NAME=RANGE overrides it for one repo. Ranges use refs that
already exist locally (e.g. origin/main..origin/feature/x, v1.4.0..v1.5.0, abc123..def456).
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from common import STORIES_DIR, config, die, out, read_json, repo_root, resolve_path, write_json

RANGE_RE = re.compile(r"^[A-Za-z0-9_./~^@{}\-]+(\.\.\.?[A-Za-z0-9_./~^@{}\-]+)?$")
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
SKIP_PARTS = {"node_modules", "build", "dist", "target", "vendor", "coverage", ".git"}
NON_SOURCE_RE = re.compile(r"(\.md|\.txt|\.png|\.jpe?g|\.svg|\.lock|package-lock\.json|yarn\.lock|go\.sum)$", re.I)
TEST_FILE_RE = re.compile(r"(\.(test|spec)\.[jt]sx?$|_test\.go$|/src/test/|__tests__/)")


def now_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def impact_root() -> Path:
    return repo_root() / STORIES_DIR / "_impact"


# --------------------------------------------------------------------------- repos + diff
def app_repos() -> list[dict]:
    ar = config().get("application_repos", {})
    repos = []
    for layer in ("frontend", "backend"):
        for r in ar.get(layer, []) or []:
            repos.append({**r, "layer": layer})
    return repos


def git(path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True)


def parse_diff(text: str) -> list[dict]:
    files, cur = [], None
    for line in text.splitlines():
        if line.startswith("diff --git "):
            cur = {"old": None, "new": None, "hunks": [], "added": [], "removed": []}
            files.append(cur)
        elif cur is None:
            continue
        elif line.startswith("--- "):
            cur["old"] = None if line[4:] == "/dev/null" else line[4:].removeprefix("a/")
        elif line.startswith("+++ "):
            cur["new"] = None if line[4:] == "/dev/null" else line[4:].removeprefix("b/")
        elif line.startswith("rename from "):
            cur["old"] = line[len("rename from "):]
        elif line.startswith("rename to "):
            cur["new"] = line[len("rename to "):]
        elif line.startswith("@@"):
            m = HUNK_RE.match(line)
            if m:
                os_, oc, ns, nc = int(m.group(1)), int(m.group(2) or 1), int(m.group(3)), int(m.group(4) or 1)
                cur["hunks"].append({"old": [os_, os_ + max(oc, 1) - 1], "new": [ns, ns + max(nc, 1) - 1]})
        elif line.startswith("+") and not line.startswith("+++"):
            cur["added"].append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            cur["removed"].append(line[1:])
    for f in files:
        f["path"] = f["new"] or f["old"]
        f["status"] = "added" if not f["old"] else "deleted" if not f["new"] else (
            "renamed" if f["old"] != f["new"] else "modified")
    return [f for f in files if f["path"] and not any(p in SKIP_PARTS for p in Path(f["path"]).parts)]


def diff_repo(repo: dict, rng: str) -> dict:
    path = resolve_path(repo["path"])
    if not path.is_dir():
        return {"repo": repo["name"], "range": rng, "error": f"repo path not found: {path}"}
    if not RANGE_RE.match(rng) or rng.startswith("-"):
        die(f"Invalid range '{rng}' for {repo['name']}. Use A..B with existing refs.")
    for ref in re.split(r"\.\.\.?", rng):
        if ref and git(path, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode != 0:
            return {"repo": repo["name"], "range": rng,
                    "error": f"ref '{ref}' not found locally (fetch it yourself first; the harness never fetches app repos)"}
    r = git(path, "diff", "--no-color", "--no-ext-diff", "-M", "--unified=0", rng, "--")
    if r.returncode != 0:
        return {"repo": repo["name"], "range": rng, "error": r.stderr.strip()[:500]}
    log = git(path, "log", "--oneline", "--no-decorate", "-n", "50", rng.replace("...", ".."))
    return {"repo": repo["name"], "layer": repo["layer"], "range": rng, "files": parse_diff(r.stdout),
            "commits": log.stdout.strip().splitlines() if log.returncode == 0 else []}


# --------------------------------------------------------------------------- matching helpers
def ignored(path: str) -> bool:
    globs = (config().get("impact") or {}).get("ignore_globs") or []
    return any(fnmatch.fnmatch(path, g) or fnmatch.fnmatch(path, g.removeprefix("**/")) for g in globs)


def path_matches(changed: str, evidence_file: str) -> bool:
    """Evidence paths may be abbreviated with "..." (e.g. src/main/java/.../LoanRequestDto.java)."""
    ev = (evidence_file or "").strip().split(":")[0]
    if not ev:
        return False
    if "..." in ev or "…" in ev:
        parts = [p.strip("/") for p in re.split(r"\.\.\.|…", ev) if p.strip("/")]
        if not parts:
            return False
        if len(parts) == 1:
            return changed.endswith(parts[0])
        return changed.startswith(parts[0]) and changed.endswith(parts[-1])
    return changed == ev or changed.endswith("/" + ev) or ev.endswith("/" + changed)


def line_of(evidence_file: str, line) -> int | None:
    if isinstance(line, int):
        return line
    m = re.search(r":(\d+)$", str(evidence_file or ""))
    return int(m.group(1)) if m else (int(line) if str(line or "").isdigit() else None)


def in_hunks(f: dict, line: int | None, ctx: int) -> bool:
    if line is None:
        return False
    return any(h[side][0] - ctx <= line <= h[side][1] + ctx for h in f["hunks"] for side in ("old", "new"))


def load_stories() -> dict:
    stories = {}
    root = repo_root() / STORIES_DIR
    for sd in sorted(p for p in root.glob("*") if p.is_dir() and not p.name.startswith("_")):
        tr = sd / "02-traceability.json"
        tc = sd / "03-test-cases.json"
        stories[sd.name] = {"trace": read_json(tr) if tr.is_file() else None,
                            "cases": (read_json(tc).get("test_cases") or []) if tc.is_file() else []}
    return stories


def evidence_items(trace: dict) -> list[dict]:
    items = []
    for c in trace.get("criteria") or []:
        for e in c.get("evidence") or []:
            items.append({"kind": "ac_evidence", "ac": c.get("id"), "ac_status": c.get("status"),
                          "repo": e.get("repo"), "file": e.get("file"), "line": line_of(e.get("file"), e.get("line")),
                          "what": e.get("what")})
    disc = trace.get("discovered") or {}
    for ep in disc.get("api_endpoints") or []:
        items.append({"kind": "endpoint", "ac": None, "repo": ep.get("service"), "file": ep.get("file"),
                      "line": line_of(ep.get("file"), None), "what": f"{ep.get('method')} {ep.get('path')}"})
    for rt in disc.get("ui_routes") or []:
        items.append({"kind": "ui_route", "ac": None, "repo": None, "file": rt.get("file"),
                      "line": line_of(rt.get("file"), None), "what": f"route {rt.get('path')} ({rt.get('component')})"})
    for db in disc.get("db_changes") or []:
        items.append({"kind": "db_change", "ac": None, "repo": None, "file": db.get("file"), "line": None,
                      "what": db.get("what")})
    return items


def testids_in(lines: list[str]) -> set[str]:
    from testid_index import ATTR_RE
    ids = set()
    for l in lines:
        for m in ATTR_RE.finditer(l):
            tid = m.group(1) or m.group(2) or m.group(3) or m.group(4)
            if tid:
                ids.add(tid)
    return ids


def locator_hits(usage_tid: str, op: str, ids: set[str]) -> bool:
    """Does a locator used in the tests (data-testid<op>"usage_tid") match any of the given frontend testids?
    Robot variables (${x}) and React template literals (${x}) both make the id dynamic: compare prefixes."""
    dyn, base = "${" in usage_tid, usage_tid.split("${")[0]
    for tid in ids:
        t_dyn, tbase = "${" in tid, tid.split("${")[0]
        if op == "*=":
            hit = usage_tid in tid
        elif op == "$=":
            hit = tid.endswith(usage_tid)
        elif op == "=" and not dyn and not t_dyn:
            hit = tid == usage_tid
        elif op == "=" and not dyn:  # exact usage of an id the frontend builds dynamically
            hit = bool(tbase) and usage_tid.startswith(tbase)
        else:  # prefix selector, or a dynamic id in the test
            hit = bool(base) and (tid.startswith(base) or (t_dyn and bool(tbase) and base.startswith(tbase)))
        if hit:
            return True
    return False


# --------------------------------------------------------------------------- analyze
def analyze(default_range: str | None, overrides: list[str], only: list[str] | None, ctx: int | None) -> dict:
    if ctx is None:
        ctx = int((config().get("impact") or {}).get("line_context", 3))
    per_repo = {}
    for o in overrides or []:
        if "=" not in o:
            die(f"--repo expects NAME=RANGE, got '{o}'")
        n, r = o.split("=", 1)
        per_repo[n.strip()] = r.strip()
    repos = [r for r in app_repos() if not only or r["name"] in only]
    if not default_range and not per_repo:
        die("Give --range A..B (all repos) or --repo NAME=A..B.")
    diffs = []
    for r in repos:
        rng = per_repo.get(r["name"], default_range)
        if rng:
            diffs.append(diff_repo(r, rng))

    from robot_catalog import locator_usages, suites_using, tests_catalog
    catalog = tests_catalog()
    by_zkey: dict[str, list[dict]] = {}
    for t in catalog:
        for zk in t["zephyr_keys"]:
            by_zkey.setdefault(zk, []).append(t)
    stories = load_stories()

    impacted: dict[str, dict] = {}
    covered_files: set[tuple[str, str]] = set()

    def story_entry(key: str) -> dict:
        return impacted.setdefault(key, {"story": key, "acs": {}, "hits": [], "zephyr_keys": set(),
                                         "robot_tests": {}, "risk": "low"})

    # 1. traceability evidence
    for d in diffs:
        for f in d.get("files", []):
            for key, s in stories.items():
                if not s["trace"]:
                    continue
                for ev in evidence_items(s["trace"]):
                    if ev["repo"] and ev["repo"] != d["repo"]:
                        continue
                    if not (path_matches(f["path"], ev["file"]) or (f["old"] and path_matches(f["old"], ev["file"]))):
                        continue
                    covered_files.add((d["repo"], f["path"]))
                    strength = "line" if in_hunks(f, ev["line"], ctx) else "file"
                    e = story_entry(key)
                    e["hits"].append({"repo": d["repo"], "changed_file": f["path"], "change": f["status"],
                                      "evidence": f"{ev['file']}" + (f":{ev['line']}" if ev["line"] else ""),
                                      "kind": ev["kind"], "ac": ev["ac"], "what": ev["what"], "strength": strength})
                    if ev["ac"]:
                        a = e["acs"].setdefault(ev["ac"], {"strength": "file", "status": ev.get("ac_status")})
                        if strength == "line":
                            a["strength"] = "line"

    # 2. data-testid changes in frontend diffs
    removed_ids, added_ids, touched_ids = set(), set(), set()
    for d in diffs:
        if d.get("layer") != "frontend":
            continue
        for f in d.get("files", []):
            rem, add = testids_in(f["removed"]), testids_in(f["added"])
            removed_ids |= rem - add
            added_ids |= add - rem
            touched_ids |= rem & add
    removed_ids -= added_ids  # moved between files = not removed
    locator_impacts = []
    if removed_ids or touched_ids:
        for u in locator_usages():
            kind = ("removed" if locator_hits(u["testid"], u["op"], removed_ids) else
                    "touched" if locator_hits(u["testid"], u["op"], touched_ids) else None)
            if not kind:
                continue
            suites = {u["file"]} if u["file"].endswith(".robot") else suites_using(u["file"], catalog)
            tests = [t for t in catalog if t["file"] in suites]
            locator_impacts.append({**u, "change": kind, "suites": sorted(suites),
                                    "tests": [f"{t['file']}::{t['name']}" for t in tests]})
            for t in tests:
                for sk in t["story_keys"] or ["(untagged)"]:
                    e = story_entry(sk)
                    e["robot_tests"][f"{t['file']}::{t['name']}"] = t
                    e["zephyr_keys"] |= set(t["zephyr_keys"])
                    hit = {"kind": f"testid_{kind}", "testid": u["testid"], "locator": f"{u['file']}:{u['line']}",
                           "strength": "locator"}
                    if hit not in e["hits"]:
                        e["hits"].append(hit)

    # 3. ACs → test cases → Robot tests, and risk
    for key, e in impacted.items():
        for tc in stories.get(key, {}).get("cases", []):
            if set(tc.get("ac_ids") or []) & set(e["acs"]) and tc.get("zephyr_key"):
                e["zephyr_keys"].add(tc["zephyr_key"])
        story_level = any(h["kind"] in ("endpoint", "ui_route", "db_change") for h in e["hits"]) and not e["acs"]
        if story_level:  # evidence without an AC (endpoint/route/migration): the whole story is in scope
            e["zephyr_keys"] |= {tc["zephyr_key"] for tc in stories.get(key, {}).get("cases", []) if tc.get("zephyr_key")}
        for zk in e["zephyr_keys"]:
            for t in by_zkey.get(zk, []):
                e["robot_tests"][f"{t['file']}::{t['name']}"] = t
        strengths = {h["strength"] for h in e["hits"]}
        e["risk"] = ("high" if "line" in strengths or any(h["kind"] == "testid_removed" for h in e["hits"])
                     else "medium" if "file" in strengths else "low")

    unmapped = []
    for d in diffs:
        for f in d.get("files", []):
            if (d["repo"], f["path"]) in covered_files or NON_SOURCE_RE.search(f["path"]) or ignored(f["path"]):
                continue
            unmapped.append({"repo": d["repo"], "file": f["path"], "change": f["status"],
                             "is_app_test": bool(TEST_FILE_RE.search("/" + f["path"])),
                             "lines_changed": len(f["added"]) + len(f["removed"])})

    aid = now_id()
    stories_out = []
    for key, e in sorted(impacted.items(), key=lambda kv: ({"high": 0, "medium": 1, "low": 2}[kv[1]["risk"]], kv[0])):
        zkeys = sorted(e["zephyr_keys"])
        tests = sorted(e["robot_tests"].values(), key=lambda t: (t["file"], t["line"]))
        stories_out.append({
            "story": key, "risk": e["risk"], "acs": e["acs"], "zephyr_keys": zkeys,
            "robot_tests": [{"name": t["name"], "file": t["file"], "line": t["line"], "zephyr_keys": t["zephyr_keys"],
                             "blocked": t["blocked"]} for t in tests],
            "hits": e["hits"][:50], "hit_count": len(e["hits"]),
            "has_workspace": key in stories,
            "run_command": (f"python3 .claude/scripts/run_robot.py {key} --include {' '.join(zkeys)} "
                            f"--run-prefix impact --out impact-{aid}.json [--env <env>]")
            if zkeys and key in stories else None,
        })
    all_z = sorted({z for s in stories_out for z in s["zephyr_keys"]})
    result = {
        "ok": True, "id": aid, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repos": [{k: d.get(k) for k in ("repo", "range", "error")} | {"files_changed": len(d.get("files", [])),
                                                                       "commits": d.get("commits", [])[:20]}
                  for d in diffs],
        "stories_without_traceability": sorted(k for k, s in stories.items() if not s["trace"]),
        "impacted_stories": stories_out,
        "testids": {"removed": sorted(removed_ids), "added": sorted(added_ids), "touched": sorted(touched_ids)},
        "locator_impacts": locator_impacts,
        "unmapped_changes": unmapped,
        "selection": {"zephyr_keys": all_z, "robot_include_args": " ".join(f"--include {z}" for z in all_z),
                      "test_count": len({(t["file"], t["name"]) for s in stories_out for t in s["robot_tests"]})},
    }
    write_json(impact_root() / aid / "impact.json", result)
    result["written"] = str((impact_root() / aid / "impact.json").relative_to(repo_root()))
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    an = sub.add_parser("analyze")
    an.add_argument("--range", help="A..B applied to every application repo")
    an.add_argument("--repo", nargs="*", default=[], help="NAME=A..B per repo (overrides --range)")
    an.add_argument("--only", nargs="*", help="Only these application repo names")
    an.add_argument("--context", type=int, default=None, help="Lines around a hunk that still count as a line hit")
    sh = sub.add_parser("show"); sh.add_argument("id")
    a = ap.parse_args()
    if a.cmd == "analyze":
        out(analyze(a.range, a.repo, a.only, a.context))
    else:
        if not re.match(r"^\d{8}-\d{6}$", a.id):
            die("id looks like 20261119-153000")
        p = impact_root() / a.id / "impact.json"
        if not p.is_file():
            die(f"No analysis {a.id} in {impact_root()}")
        out(read_json(p))


if __name__ == "__main__":
    main()
