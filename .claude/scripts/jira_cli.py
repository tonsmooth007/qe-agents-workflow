#!/usr/bin/env python3
"""Jira Cloud helper (REST v3). All output is JSON on stdout.

Read-only:
  jira_cli.py get-story KEY [--save]           # story + AC as markdown; --save writes .stories/KEY/raw/jira-story.json
  jira_cli.py download-attachments KEY         # -> .stories/KEY/attachments/
  jira_cli.py search-bugs KEY [--text "..."]   # open bugs linked to / mentioning the story (dedupe)
  jira_cli.py issue-id KEY                     # numeric id (needed by Zephyr links)
  jira_cli.py get-issue KEY                    # any issue (e.g. a bug): status, resolution, fix versions, links

Write (REQUIRES human approval — enforced by the approval field in the draft + permission prompt):
  jira_cli.py create-bug --draft .stories/KEY/06-bugs/bug-1.md [--dry-run]
  jira_cli.py add-comment KEY --body-file FILE [--dry-run]
  jira_cli.py post-comment --draft .stories/KEY/08-verify/LOAN-456.md [--dry-run]
      Posts an APPROVED comment draft (front matter: issue, approval: approved, approved_by) to its issue,
      then records comment_id and approval: posted. Refuses (exit 3) unapproved drafts.
"""
from __future__ import annotations

import argparse
import mimetypes
import re
from pathlib import Path

from adf import adf_to_md, md_to_adf
from common import (Http, config, die, env, out, read_front_matter, repo_root, story_dir,
                    validate_key, write_front_matter, write_json)


def client(dry_run: bool = False) -> Http:
    return Http(env("JIRA_BASE_URL") + "/rest/api/3",
                auth=(env("JIRA_EMAIL"), env("JIRA_API_TOKEN")), dry_run=dry_run)


# --------------------------------------------------------------------------- read
AC_HEADING_RE = re.compile(r"^#{1,6}\s*\**\s*acceptance\s+criteria\b.*$", re.I | re.M)
AC_LINE_RE = re.compile(r"^\s*\**acceptance\s+criteria\**\s*:?\s*\**\s*$", re.I | re.M)


def extract_ac_from_description(md: str) -> str | None:
    m = AC_HEADING_RE.search(md) or AC_LINE_RE.search(md)
    if not m:
        return None
    rest = md[m.end():]
    nxt = re.search(r"^#{1,6}\s+\S", rest, re.M)
    return (rest[: nxt.start()] if nxt else rest).strip() or None


def get_story(key: str) -> dict:
    cfg = config()["jira"]
    j = client()
    raw = j.get(f"issue/{key}", params={"expand": "names", "fields": "*all"})
    f = raw["fields"]
    names = raw.get("names", {})
    desc_md = adf_to_md(f.get("description")) if f.get("description") else ""

    ac_field = cfg.get("acceptance_criteria_field")
    ac_md, ac_source = None, None
    if ac_field and f.get(ac_field):
        val = f[ac_field]
        ac_md = adf_to_md(val) if isinstance(val, dict) else str(val)
        ac_source = f"field:{ac_field}"
    if not ac_md:
        ac_md = extract_ac_from_description(desc_md)
        ac_source = "description" if ac_md else None
    if not ac_md:  # try any custom field literally named "Acceptance Criteria"
        for fid, fname in names.items():
            if fname and "acceptance criteria" in fname.lower() and f.get(fid):
                val = f[fid]
                ac_md = adf_to_md(val) if isinstance(val, dict) else str(val)
                ac_source = f"field:{fid} (auto-detected — set jira.acceptance_criteria_field)"
                break

    comments = (f.get("comment") or {}).get("comments", [])
    sp_field = cfg.get("story_points_field")
    return {
        "key": raw["key"],
        "id": raw["id"],
        "url": f"{env('JIRA_BASE_URL')}/browse/{raw['key']}",
        "summary": f.get("summary"),
        "issue_type": (f.get("issuetype") or {}).get("name"),
        "status": (f.get("status") or {}).get("name"),
        "priority": (f.get("priority") or {}).get("name"),
        "assignee": (f.get("assignee") or {}).get("displayName"),
        "reporter": (f.get("reporter") or {}).get("displayName"),
        "labels": f.get("labels", []),
        "components": [c["name"] for c in f.get("components", [])],
        "fix_versions": [v["name"] for v in f.get("fixVersions", [])],
        "sprint": _sprint(f, names),
        "story_points": f.get(sp_field) if sp_field else None,
        "parent": ({"key": f["parent"]["key"], "summary": f["parent"]["fields"].get("summary")}
                   if f.get("parent") else None),
        "description_md": desc_md,
        "acceptance_criteria_md": ac_md,
        "acceptance_criteria_source": ac_source,
        "subtasks": [{"key": s["key"], "summary": s["fields"]["summary"], "status": s["fields"]["status"]["name"]}
                     for s in f.get("subtasks", [])],
        "issue_links": [_link(l) for l in f.get("issuelinks", [])],
        "attachments": [{"id": a["id"], "filename": a["filename"], "mime": a.get("mimeType"),
                         "size": a.get("size"), "url": a["content"]} for a in f.get("attachment", [])],
        "comments": [{"author": (c.get("author") or {}).get("displayName"), "created": c.get("created"),
                      "body_md": adf_to_md(c.get("body"))} for c in comments[-20:]],
    }


def _sprint(f: dict, names: dict):
    for fid, fname in names.items():
        if fname == "Sprint" and f.get(fid):
            v = f[fid]
            if isinstance(v, list) and v:
                return v[-1].get("name") if isinstance(v[-1], dict) else str(v[-1])
    return None


def _link(l: dict) -> dict:
    if "outwardIssue" in l:
        i, rel = l["outwardIssue"], l["type"]["outward"]
    else:
        i, rel = l["inwardIssue"], l["type"]["inward"]
    return {"relation": rel, "key": i["key"], "summary": i["fields"].get("summary"),
            "type": i["fields"].get("issuetype", {}).get("name"), "status": i["fields"].get("status", {}).get("name")}


def download_attachments(key: str) -> dict:
    j = client()
    story = j.get(f"issue/{key}", params={"fields": "attachment"})
    dest = story_dir(key) / "attachments"
    dest.mkdir(parents=True, exist_ok=True)
    saved = []
    for a in story["fields"].get("attachment", []):
        name = re.sub(r"[^\w.\- ]", "_", a["filename"])
        target = dest / f"{a['id']}_{name}"
        if not target.exists():
            data = j.s.get(a["content"], timeout=120)
            data.raise_for_status()
            target.write_bytes(data.content)
        saved.append({"file": str(target.relative_to(repo_root())), "mime": a.get("mimeType"), "size": a.get("size")})
    return {"story": key, "count": len(saved), "attachments": saved}


def search_bugs(key: str, text: str | None) -> dict:
    cfg = config()["jira"]
    types = {cfg["bug"]["issue_type"], cfg["bug"]["child_issue_type"]}
    type_clause = ", ".join(f'"{t}"' for t in types)
    jql = (f'project = {cfg["project_key"]} AND issuetype in ({type_clause}) AND statusCategory != Done '
           f'AND (issue in linkedIssues("{key}") OR parent = {key}')
    if text:
        safe = text.replace('"', " ")[:120]
        jql += f' OR text ~ "{safe}"'
    jql += ") ORDER BY created DESC"
    res = client().get("search/jql", params={"jql": jql, "maxResults": 50,
                                             "fields": "summary,status,issuetype,created,priority"})
    issues = [{"key": i["key"], "summary": i["fields"]["summary"], "status": i["fields"]["status"]["name"],
               "type": i["fields"]["issuetype"]["name"], "created": i["fields"]["created"]}
              for i in res.get("issues", [])]
    return {"jql": jql, "count": len(issues), "issues": issues}


def get_issue(key: str) -> dict:
    raw = client().get(f"issue/{key}", params={
        "fields": "summary,status,resolution,issuetype,priority,fixVersions,labels,parent,issuelinks,"
                  "updated,resolutiondate,assignee,components"})
    f = raw["fields"]
    status = f.get("status") or {}
    return {
        "key": raw["key"], "id": raw["id"], "url": f"{env('JIRA_BASE_URL')}/browse/{raw['key']}",
        "summary": f.get("summary"), "issue_type": (f.get("issuetype") or {}).get("name"),
        "status": status.get("name"), "status_category": (status.get("statusCategory") or {}).get("key"),
        "resolution": (f.get("resolution") or {}).get("name"), "resolution_date": f.get("resolutiondate"),
        "priority": (f.get("priority") or {}).get("name"),
        "assignee": (f.get("assignee") or {}).get("displayName"),
        "fix_versions": [v["name"] for v in f.get("fixVersions", [])],
        "labels": f.get("labels", []), "components": [c["name"] for c in f.get("components", [])],
        "parent": f["parent"]["key"] if f.get("parent") else None,
        "issue_links": [_link(l) for l in f.get("issuelinks", [])],
        "updated": f.get("updated"),
    }


def issue_id(key: str) -> str:
    return client().get(f"issue/{key}", params={"fields": "summary"})["id"]


# --------------------------------------------------------------------------- write
def create_bug(draft_path: str, dry_run: bool) -> dict:
    p = Path(draft_path)
    if not p.is_absolute():
        p = repo_root() / p
    meta, body = read_front_matter(p)

    # ---- Human-in-the-loop guard -------------------------------------------
    if meta.get("jira_key"):
        die(f"Draft already filed as {meta['jira_key']}.")
    # --dry-run is allowed on unapproved drafts so the payload can be previewed.
    if not dry_run and (meta.get("approval") != "approved" or not meta.get("approved_by")):
        die("Bug draft is not approved. A human must approve it first "
            "(front matter: approval: approved, approved_by: <name>).", code=3)

    cfg = config()["jira"]
    bcfg = cfg["bug"]
    story = validate_key(meta["story"])
    mode = meta.get("link_mode") or bcfg.get("default_link_mode", "relates")
    j = client(dry_run)
    fields: dict = {
        "project": {"key": cfg["project_key"]},
        "summary": meta["title"][:254],
        "description": md_to_adf(body),
        "labels": sorted(set(bcfg.get("labels", []) + (meta.get("labels") or []))),
        "priority": {"name": meta.get("priority") or bcfg.get("default_priority", "Medium")},
        **(bcfg.get("extra_fields") or {}),
    }
    if mode == "child":
        fields["issuetype"] = {"name": bcfg["child_issue_type"]}
        fields["parent"] = {"key": story}
    else:
        fields["issuetype"] = {"name": bcfg["issue_type"]}
    if bcfg.get("copy_components_from_story", True) and not dry_run:
        comps = client().get(f"issue/{story}", params={"fields": "components"})["fields"].get("components", [])
        if comps:
            fields["components"] = [{"id": c["id"]} for c in comps]

    created = j.post("issue", json={"fields": fields})
    bug_key = created.get("key", "DRY-RUN")

    if mode != "child":
        j.post("issueLink", json={"type": {"name": bcfg.get("relates_link_type", "Relates")},
                                  "inwardIssue": {"key": bug_key}, "outwardIssue": {"key": story}})

    attached = []
    for att in meta.get("attachments") or []:
        ap = (repo_root() / att) if not Path(att).is_absolute() else Path(att)
        if not ap.is_file():
            continue
        mime = mimetypes.guess_type(ap.name)[0] or "application/octet-stream"
        with open(ap, "rb") as fh:
            j.post(f"issue/{bug_key}/attachments", headers={"X-Atlassian-Token": "no-check"},
                   files={"file": (ap.name, fh, mime)})
        attached.append(str(att))

    result = {"ok": True, "dry_run": dry_run, "bug_key": bug_key, "link_mode": mode, "story": story,
              "url": f"{env('JIRA_BASE_URL')}/browse/{bug_key}", "attachments": attached}
    if not dry_run:
        meta.update(jira_key=bug_key, approval="filed", jira_url=result["url"])
        write_front_matter(p, meta, body)
    return result


def add_comment(key: str, body_file: str, dry_run: bool) -> dict:
    body = Path(body_file).read_text(encoding="utf-8")
    res = client(dry_run).post(f"issue/{key}/comment", json={"body": md_to_adf(body)})
    return {"ok": True, "dry_run": dry_run, "comment_id": res.get("id")}


def post_comment(draft_path: str, dry_run: bool) -> dict:
    """Post the body of an approved comment draft (e.g. a bug verification result) to its issue."""
    p = Path(draft_path)
    if not p.is_absolute():
        p = repo_root() / p
    meta, body = read_front_matter(p)
    if meta.get("comment_id"):
        die(f"Draft already posted as comment {meta['comment_id']} on {meta.get('issue')}.")
    if not dry_run and (meta.get("approval") != "approved" or not meta.get("approved_by")):
        die("Comment draft is not approved. A human must approve it first "
            "(front matter: approval: approved, approved_by: <name>).", code=3)
    issue = validate_key(meta.get("issue") or "")
    text = re.sub(r"<!--.*?-->", "", body, flags=re.S).strip()  # template guidance comments are not posted
    if not text:
        die(f"{p} has an empty body.")
    res = client(dry_run).post(f"issue/{issue}/comment", json={"body": md_to_adf(text)})
    result = {"ok": True, "dry_run": dry_run, "issue": issue, "comment_id": res.get("id")}
    if not dry_run:
        meta.update(approval="posted", comment_id=res.get("id"))
        write_front_matter(p, meta, body)
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("get-story"); g.add_argument("key"); g.add_argument("--save", action="store_true")
    sub.add_parser("download-attachments").add_argument("key")
    sb = sub.add_parser("search-bugs"); sb.add_argument("key"); sb.add_argument("--text")
    sub.add_parser("issue-id").add_argument("key")
    sub.add_parser("get-issue").add_argument("key")
    pc = sub.add_parser("post-comment"); pc.add_argument("--draft", required=True)
    pc.add_argument("--dry-run", action="store_true")
    cb = sub.add_parser("create-bug"); cb.add_argument("--draft", required=True); cb.add_argument("--dry-run", action="store_true")
    cm = sub.add_parser("add-comment"); cm.add_argument("key"); cm.add_argument("--body-file", required=True)
    cm.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.cmd == "get-story":
        key = validate_key(a.key)
        data = get_story(key)
        if a.save:
            write_json(story_dir(key) / "raw" / "jira-story.json", data)
        out(data)
    elif a.cmd == "download-attachments":
        out(download_attachments(validate_key(a.key)))
    elif a.cmd == "search-bugs":
        out(search_bugs(validate_key(a.key), a.text))
    elif a.cmd == "issue-id":
        out({"key": a.key, "id": issue_id(validate_key(a.key))})
    elif a.cmd == "create-bug":
        out(create_bug(a.draft, a.dry_run))
    elif a.cmd == "get-issue":
        out(get_issue(validate_key(a.key)))
    elif a.cmd == "post-comment":
        out(post_comment(a.draft, a.dry_run))
    elif a.cmd == "add-comment":
        out(add_comment(validate_key(a.key), a.body_file, a.dry_run))


if __name__ == "__main__":
    main()
