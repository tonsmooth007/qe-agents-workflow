#!/usr/bin/env python3
"""Catalog of this repo's Robot tests and data-testid locators, parsed from the .robot/.resource text.

Plain-text parsing, no Robot Framework import, so it also works for files that don't pass a dry-run yet.
Used by impact_map.py, testid_drift.py and bug_verify.py.

  tests:    name, file:line, tags (own [Tags] + Test Tags/Force Tags from the file and __init__.robot files),
            zephyr_keys, story_keys, resources (Resource imports), ui/api
  locators: every data-testid used in tests/resources: file:line, variable name (if it is a variable
            definition), the testid, and the match operator (= exact, ^= prefix, *= contains, $= suffix)

Usage:
  robot_catalog.py [--tests-only | --locators-only] [--zephyr KEY ...]
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import STORY_KEY_RE, config, out, repo_root

SEP_RE = re.compile(r"(?:\t|\s{2,}|\s\|\s)")
SECTION_RE = re.compile(r"^\*+\s*([A-Za-z ]+?)\s*\*+")
VAR_DEF_RE = re.compile(r"^([$@&]\{[^}]+\})\s*=?\s*(?:\t|\s{2,})(.*)$")
TESTID_RE = re.compile(r"""data-testid\s*([\^*$]?=)\s*\\?["']([^"'\\]+)\\?["']""")
SKIP_DIRS = {".git", ".stories", "results", "node_modules", ".venv", "venv", "__pycache__", ".claude"}


def zephyr_re() -> re.Pattern:
    proj = config().get("zephyr", {}).get("project_key") or "[A-Z][A-Z0-9_]+"
    return re.compile(rf"^{proj}-T\d+$", re.I)


def _cells(line: str) -> list[str]:
    return [c for c in SEP_RE.split(line.strip()) if c and c != "|"]


def robot_files(exts: tuple[str, ...] = (".robot", ".resource")) -> list[Path]:
    root = repo_root()
    files = []
    for p in root.rglob("*"):
        if p.suffix in exts and p.is_file() and not any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            files.append(p)
    return sorted(files)


def _parse(path: Path) -> dict:
    """Return settings tags, resource imports and tests of one file."""
    section, tests, file_tags, default_tags, resources = None, [], [], [], []
    current, cont_target = None, None
    for i, raw in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = SECTION_RE.match(raw)
        if m:
            name = m.group(1).strip().lower()
            section = ("settings" if name.startswith("setting") else
                       "tests" if name.startswith(("test case", "task")) else
                       "keywords" if name.startswith("keyword") else
                       "variables" if name.startswith("variable") else name)
            current, cont_target = None, None
            continue
        cells = _cells(raw)
        if not cells:
            continue
        if cells[0] == "..." and cont_target is not None:
            cont_target.extend(cells[1:])
            continue
        cont_target = None
        if section == "settings":
            key = cells[0].lower()
            if key in ("test tags", "force tags"):
                file_tags.extend(cells[1:]); cont_target = file_tags
            elif key == "default tags":
                default_tags.extend(cells[1:]); cont_target = default_tags
            elif key == "resource" and len(cells) > 1:
                resources.append(cells[1])
        elif section == "tests":
            if not raw[0].isspace():
                current = {"name": cells[0], "line": i, "own_tags": None}
                tests.append(current)
                rest = cells[1:]
                if rest and rest[0].lower() == "[tags]":
                    current["own_tags"] = rest[1:]; cont_target = current["own_tags"]
            elif current is not None and cells[0].lower() == "[tags]":
                current["own_tags"] = (current["own_tags"] or []) + cells[1:]
                cont_target = current["own_tags"]
    return {"file_tags": file_tags, "default_tags": default_tags, "resources": resources, "tests": tests}


def _init_tags(path: Path, cache: dict) -> list[str]:
    """Test Tags / Force Tags from __init__.robot files in this directory and its parents (up to the root)."""
    root, tags = repo_root(), []
    d = path.parent
    while True:
        init = d / "__init__.robot"
        if init.is_file():
            if init not in cache:
                cache[init] = _parse(init)["file_tags"]
            tags = cache[init] + tags
        if d == root or root not in d.parents:
            break
        d = d.parent
    return tags


def tests_catalog() -> list[dict]:
    root, zre, cache = repo_root(), zephyr_re(), {}
    result = []
    for f in robot_files((".robot",)):
        if f.name == "__init__.robot":
            continue
        parsed = _parse(f)
        inherited = _init_tags(f, cache) + parsed["file_tags"]
        for t in parsed["tests"]:
            own = t["own_tags"] if t["own_tags"] is not None else parsed["default_tags"]
            tags = list(dict.fromkeys(inherited + own))
            low = {x.lower() for x in tags}
            result.append({
                "name": t["name"], "file": str(f.relative_to(root)), "line": t["line"], "tags": tags,
                "zephyr_keys": [x.upper() for x in tags if zre.match(x)],
                "story_keys": [x.upper() for x in tags if STORY_KEY_RE.match(x.upper()) and not zre.match(x)],
                "layer": "ui" if "ui" in low else "api" if "api" in low else None,
                "blocked": sorted(x for x in low if x.startswith("blocked-")),
                "resources": parsed["resources"],
            })
    return result


def locator_usages() -> list[dict]:
    root, result = repo_root(), []
    for f in robot_files():
        for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if "data-testid" not in line:
                continue
            vm = VAR_DEF_RE.match(line.strip())
            for m in TESTID_RE.finditer(line):
                result.append({"file": str(f.relative_to(root)), "line": i, "testid": m.group(2),
                               "op": m.group(1), "dynamic": "${" in m.group(2),
                               "variable": vm.group(1) if vm else None, "text": line.strip()[:200]})
    return result


def suites_using(resource_file: str, catalog: list[dict]) -> set[str]:
    """Robot suite files that import the given resource file (by file name), directly or via another resource."""
    root = repo_root()
    target_names = {Path(resource_file).name}
    # follow resource → resource imports a few levels deep
    res_files = robot_files((".resource",))
    for _ in range(3):
        added = False
        for rf in res_files:
            if rf.name in target_names:
                continue
            if any(Path(r).name in target_names for r in _parse(rf)["resources"]):
                target_names.add(rf.name); added = True
        if not added:
            break
    return {t["file"] for t in catalog if any(Path(r.replace("${CURDIR}", "")).name in target_names
                                                for r in t["resources"])} | (
        {str(Path(resource_file))} if resource_file.endswith(".robot") else set())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tests-only", action="store_true")
    ap.add_argument("--locators-only", action="store_true")
    ap.add_argument("--zephyr", nargs="*", help="Only tests carrying these Zephyr keys")
    a = ap.parse_args()
    res: dict = {}
    if not a.locators_only:
        tests = tests_catalog()
        if a.zephyr:
            want = {k.upper() for k in a.zephyr}
            tests = [t for t in tests if want & set(t["zephyr_keys"])]
        res["tests"] = tests
        res["test_count"] = len(tests)
    if not a.tests_only:
        res["locators"] = locator_usages()
    out(res)


if __name__ == "__main__":
    main()
