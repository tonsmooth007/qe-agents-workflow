#!/usr/bin/env python3
"""Index every data-testid in the frontend repo(s) listed in .claude/qe.config.yaml.

Finds:  data-testid="x" | data-testid='x' | data-testid={"x"} | data-testid={`x-${id}`} (dynamic)
        and getByTestId('x') usages in frontend unit tests (confirms the id is real).

Usage:
  testid_index.py [--filter TEXT ...] [--file-filter TEXT] [--write PATH]
  e.g. testid_index.py --filter loan-amount term --file-filter LoanApplication
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import config, out, resolve_path, write_json

EXTS = {".js", ".jsx", ".ts", ".tsx"}
SKIP_DIRS = {"node_modules", "build", "dist", "coverage", ".next", ".git", "storybook-static"}
ATTR_RE = re.compile(r"""data-testid\s*=\s*(?:"([^"]+)"|'([^']+)'|\{\s*["']([^"']+)["']\s*\}|\{\s*`([^`]+)`\s*\}|\{([^}]+)\})""")
TEST_USE_RE = re.compile(r"""(?:getBy|queryBy|findBy|getAllBy|queryAllBy|findAllBy)TestId\(\s*["'`]([^"'`]+)["'`]""")
COMPONENT_RE = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:function|const|class)\s+([A-Z]\w*)")


def scan_repo(name: str, root: Path, src_dirs: list[str]) -> tuple[list[dict], dict[str, list[str]]]:
    entries, test_uses = [], {}
    for sd in src_dirs or ["src"]:
        base = root / sd
        if not base.is_dir():
            continue
        for f in base.rglob("*"):
            if f.suffix not in EXTS or any(p in SKIP_DIRS for p in f.parts):
                continue
            try:
                lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            is_test = bool(re.search(r"\.(test|spec)\.[jt]sx?$", f.name)) or "__tests__" in f.parts
            component = None
            for i, line in enumerate(lines, 1):
                cm = COMPONENT_RE.match(line)
                if cm:
                    component = cm.group(1)
                if is_test:
                    for m in TEST_USE_RE.finditer(line):
                        test_uses.setdefault(m.group(1), []).append(f"{f.relative_to(root)}:{i}")
                    continue
                for m in ATTR_RE.finditer(line):
                    static = m.group(1) or m.group(2) or m.group(3)
                    tmpl = m.group(4)
                    expr = m.group(5)
                    if static:
                        tid, kind = static, "static"
                    elif tmpl:
                        tid, kind = tmpl, ("template" if "${" in tmpl else "static")
                    else:
                        tid, kind = expr.strip(), "expression"
                    entries.append({"testid": tid, "kind": kind, "repo": name, "component": component,
                                    "file": str(f.relative_to(root)), "line": i,
                                    "selector": _selector(tid, kind), "note": _NOTES[kind]})
    return entries, test_uses


_NOTES = {
    "static": None,
    "template": "dynamic id: build the exact id in a keyword argument; prefix selector shown matches all instances",
    "expression": "id comes from a JS expression/prop: read the component (and its callers) to resolve the value",
}


def _selector(tid: str, kind: str) -> str | None:
    if kind == "static":
        return f'css=[data-testid="{tid}"]'
    if kind == "template":
        prefix = tid.split("${")[0]
        return f'css=[data-testid^="{prefix}"]' if prefix else None
    return None  # expression -> agent must read the component to resolve


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--filter", nargs="*", help="Keep test ids containing any of these substrings")
    ap.add_argument("--file-filter", help="Keep entries whose file path contains this text")
    ap.add_argument("--write")
    a = ap.parse_args()
    repos = config().get("application_repos", {}).get("frontend", [])
    all_entries, all_uses, missing = [], {}, []
    for r in repos:
        root = resolve_path(r["path"])
        if not root.is_dir():
            missing.append(str(root))
            continue
        e, u = scan_repo(r["name"], root, r.get("src_dirs", ["src"]))
        all_entries += e
        for k, v in u.items():
            all_uses.setdefault(k, []).extend(v)
    for e in all_entries:
        e["used_in_unit_tests"] = e["testid"] in all_uses
    if a.filter:
        f = [x.lower() for x in a.filter]
        all_entries = [e for e in all_entries if any(x in e["testid"].lower() for x in f)]
    if a.file_filter:
        all_entries = [e for e in all_entries if a.file_filter.lower() in e["file"].lower()]
    result = {"count": len(all_entries), "missing_repos": missing, "testids": all_entries}
    if a.write:
        write_json(a.write, result)
    out(result)


if __name__ == "__main__":
    main()
