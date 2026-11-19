#!/usr/bin/env python3
"""Create (or switch back to) the story's git branch in this test repo. Run it before any automation work.

Branch name: <gitlab.branch_prefix><KEY>-<slug>, e.g. qe/LOAN-123-loan-amount-limits. The slug comes from
--slug, else from the story summary in .stories/<KEY>/raw/jira-story.json. Once a branch is recorded in
state.json, that name is always reused.

Behaviour:
  - Already on the story branch   → stay there (uncommitted work on it is fine, e.g. a fix loop)
  - Story branch exists locally   → switch to it (never resets it)
  - Story branch exists on origin → check it out, tracking origin
  - Otherwise                     → fetch, then branch from the latest origin/<gitlab.target_branch>
  - Uncommitted changes while on another branch → refuse (exit 4); nothing is stashed or discarded

Usage:
  story_branch.py KEY [--slug SLUG] [--no-fetch]
  story_branch.py KEY --check          # exit 0 if on the story branch, 4 if not (used by the PR agent)
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone

from common import config, die, out, read_json, repo_root, story_dir, validate_key, write_json


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", *args], cwd=repo_root(), capture_output=True, text=True)
    if check and r.returncode != 0:
        die(f"git {' '.join(args)} failed", stderr=r.stderr.strip()[:1000])
    return r


def slugify(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:max_len].rstrip("-") or "automation"


def branch_name(key: str, slug: str | None, st: dict) -> str:
    if st.get("branch"):
        return st["branch"]
    prefix = config().get("gitlab", {}).get("branch_prefix", "qe/")
    if not slug:
        raw = story_dir(key) / "raw" / "jira-story.json"
        slug = slugify(read_json(raw).get("summary", "")) if raw.is_file() else "automation"
    return f"{prefix}{key}-{slugify(slug)}"


def dirty_files() -> list[str]:
    return [l for l in git("status", "--porcelain").stdout.splitlines() if l.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("key")
    ap.add_argument("--slug", help="Short description for the branch name (default: story summary)")
    ap.add_argument("--no-fetch", action="store_true", help="Don't fetch origin first (offline)")
    ap.add_argument("--check", action="store_true", help="Only verify that the story branch is checked out")
    a = ap.parse_args()
    key = validate_key(a.key)

    if git("rev-parse", "--is-inside-work-tree", check=False).returncode != 0:
        die(f"{repo_root()} is not a git repository.")
    state_p = story_dir(key) / "state.json"
    st = read_json(state_p) if state_p.is_file() else {}
    target = config().get("gitlab", {}).get("target_branch", "main")
    current = git("branch", "--show-current").stdout.strip()

    if a.check:
        want = st.get("branch")
        ok = bool(want) and current == want
        out({"ok": ok, "story_branch": want, "current_branch": current})
        sys.exit(0 if ok else 4)

    branch = branch_name(key, a.slug, st)
    if branch in (target, "main", "master", "develop"):
        die(f"Refusing to use '{branch}' as a story branch.")

    if current == branch:
        action, base = "already_on_branch", None
    else:
        dirty = dirty_files()
        if dirty:
            die(f"Uncommitted changes on '{current}'. Commit or stash them before switching to the story "
                f"branch. Nothing was changed.", code=4, current_branch=current, files=dirty[:30])
        fetched = False
        if not a.no_fetch and git("remote", "get-url", "origin", check=False).returncode == 0:
            fetched = git("fetch", "--quiet", "origin", check=False).returncode == 0
        local_exists = git("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0
        remote_exists = git("rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}", check=False).returncode == 0
        if local_exists:
            git("switch", branch)
            action, base = "switched_to_existing", None
        elif remote_exists:
            git("switch", "--track", "-c", branch, f"origin/{branch}")
            action, base = "checked_out_from_origin", f"origin/{branch}"
        else:
            base = f"origin/{target}" if git("rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{target}",
                                            check=False).returncode == 0 else target
            if git("rev-parse", "--verify", "--quiet", base, check=False).returncode != 0:
                die(f"Base branch '{target}' not found locally or on origin.")
            git("switch", "--no-track", "-c", branch, base)
            action = "created"
        if not fetched and action == "created":
            print(f'{{"warning": "origin was not fetched; branched from the last known {base}"}}', file=sys.stderr)

    head = git("rev-parse", "--short", "HEAD").stdout.strip()
    if state_p.is_file():
        st["branch"] = branch
        st.setdefault("branch_info", {})
        if action == "created":
            st["branch_info"] = {"base": base, "base_sha": head,
                                 "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        write_json(state_p, st)
    out({"ok": True, "story": key, "branch": branch, "action": action, "base": base, "head": head,
         "target_branch": target, "uncommitted_changes": len(dirty_files())})


if __name__ == "__main__":
    main()
