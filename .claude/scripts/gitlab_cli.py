#!/usr/bin/env python3
"""GitLab helper (REST v4) for the test repo. All output is JSON on stdout.

Read-only:
  gitlab_cli.py mr-status --branch BRANCH          # existing open MR for the branch, if any

Write (REQUIRES human approval — enforced by the draft's approval field + permission prompt):
  gitlab_cli.py create-mr --draft .stories/KEY/07-mr.md [--dry-run]
      Branch must already be pushed (git push -u origin <branch>).
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from urllib.parse import quote

from common import Http, config, die, env, out, read_front_matter, repo_root, write_front_matter


def client(dry_run: bool = False) -> Http:
    return Http(env("GITLAB_URL") + "/api/v4", headers={"PRIVATE-TOKEN": env("GITLAB_TOKEN")}, dry_run=dry_run)


def project() -> str:
    return quote(config()["gitlab"]["project_path"], safe="")


def mr_for_branch(branch: str) -> dict | None:
    res = client().get(f"projects/{project()}/merge_requests", params={"source_branch": branch, "state": "opened"})
    return res[0] if res else None


def remote_has_branch(branch: str) -> bool:
    r = subprocess.run(["git", "ls-remote", "--heads", "origin", branch], cwd=repo_root(),
                       capture_output=True, text=True)
    return r.returncode == 0 and bool(r.stdout.strip())


def create_mr(draft: str, dry_run: bool) -> dict:
    p = Path(draft)
    if not p.is_absolute():
        p = repo_root() / p
    meta, body = read_front_matter(p)
    if meta.get("mr_url"):
        die(f"MR already created: {meta['mr_url']}")
    if not dry_run and (meta.get("approval") != "approved" or not meta.get("approved_by")):
        die("MR draft is not approved. A human must approve it first "
            "(front matter: approval: approved, approved_by: <name>).", code=3)
    cfg = config()["gitlab"]
    branch = meta["source_branch"]
    if not dry_run:
        if not remote_has_branch(branch):
            die(f"Branch {branch} is not on origin. Push it first (git push -u origin {branch}).")
        existing = mr_for_branch(branch)
        if existing:
            meta.update(mr_url=existing["web_url"], approval="submitted")
            write_front_matter(p, meta, body)
            return {"ok": True, "existing": True, "mr_url": existing["web_url"], "iid": existing["iid"]}
    payload = {
        "source_branch": branch,
        "target_branch": meta.get("target_branch") or cfg.get("target_branch", "main"),
        "title": meta["title"],
        "description": body.strip(),
        "labels": ",".join(sorted(set((cfg.get("labels") or []) + (meta.get("labels") or [])))),
        "remove_source_branch": bool(cfg.get("remove_source_branch", True)),
    }
    if meta.get("draft_mr"):
        payload["title"] = "Draft: " + payload["title"]
    res = client(dry_run).post(f"projects/{project()}/merge_requests", json=payload)
    url = res.get("web_url", "DRY-RUN")
    if not dry_run:
        meta.update(mr_url=url, approval="submitted")
        write_front_matter(p, meta, body)
    return {"ok": True, "dry_run": dry_run, "mr_url": url, "iid": res.get("iid")}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("mr-status").add_argument("--branch", required=True)
    c = sub.add_parser("create-mr"); c.add_argument("--draft", required=True); c.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.cmd == "mr-status":
        mr = mr_for_branch(a.branch)
        out({"branch": a.branch, "open_mr": bool(mr), "mr_url": mr and mr["web_url"],
             "pipeline": mr and (mr.get("head_pipeline") or {}).get("status")})
    elif a.cmd == "create-mr":
        out(create_mr(a.draft, a.dry_run))


if __name__ == "__main__":
    main()
