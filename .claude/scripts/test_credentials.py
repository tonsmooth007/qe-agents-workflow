#!/usr/bin/env python3
"""List the RBAC test roles defined in the test repo's root .env, WITHOUT revealing any values.

The application uses role-based access control. Test credentials live in <repo root>/.env (the test repo's own
file, not .claude/.env), one pair per role:

    COMS_<ROLE>_USERNAME=...
    COMS_<ROLE>_PASSWORD=...

e.g. COMS_ADMIN_*, COMS_UNDERWRITER_*, COMS_LOAN_OFFICER_*. Robot tests use them as
%{COMS_<ROLE>_USERNAME} / %{COMS_<ROLE>_PASSWORD}, and run_robot.py loads this file into every Robot run.

Usage:
  test_credentials.py                      # roles found + whether each pair is complete
  test_credentials.py --require ADMIN UNDERWRITER
                                           # exit 5 if any required role is missing or incomplete

Output never contains usernames or passwords, only variable names and a set/empty flag.
"""
from __future__ import annotations

import argparse
import re
import sys

from common import out, repo_root

PAIR_RE = re.compile(r"^COMS_([A-Z0-9_]+?)_(USERNAME|PASSWORD)$")


def parse_env_keys(path) -> dict[str, bool]:
    """KEY -> has a non-empty value. Values themselves are never kept."""
    keys: dict[str, bool] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if k.startswith("export "):
            k = k[len("export "):].strip()
        keys[k] = bool(v.strip().strip('"').strip("'"))
    return keys


def roles(path) -> list[dict]:
    found: dict[str, dict] = {}
    for k, has_value in parse_env_keys(path).items():
        m = PAIR_RE.match(k)
        if not m:
            continue
        role, kind = m.group(1), m.group(2).lower()
        r = found.setdefault(role, {"role": role, "username_var": f"COMS_{role}_USERNAME",
                                    "password_var": f"COMS_{role}_PASSWORD", "username": "missing", "password": "missing"})
        r[kind] = "set" if has_value else "empty"
    for r in found.values():
        r["complete"] = r["username"] == "set" and r["password"] == "set"
        r["robot"] = {"username": f"%{{{r['username_var']}}}", "password": f"%{{{r['password_var']}}}"}
    return sorted(found.values(), key=lambda r: r["role"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--require", nargs="*", default=[], help="Role names that must exist with both values set")
    a = ap.parse_args()
    env_file = repo_root() / ".env"
    if not env_file.is_file():
        out({"ok": False, "env_file": ".env", "error": "No .env in the test repo root, so no role credentials",
             "roles": [], "missing_required": [r.upper() for r in a.require]})
        sys.exit(5 if a.require else 1)
    rs = roles(env_file)
    by_name = {r["role"]: r for r in rs}
    missing = [r.upper() for r in a.require if not by_name.get(r.upper(), {}).get("complete")]
    out({"ok": not missing, "env_file": ".env", "roles": rs,
         "incomplete": [r["role"] for r in rs if not r["complete"]], "missing_required": missing})
    sys.exit(5 if missing else 0)


if __name__ == "__main__":
    main()
