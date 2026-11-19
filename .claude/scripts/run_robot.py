#!/usr/bin/env python3
"""Run the Robot suites for a story, re-run failures once, and write .stories/KEY/05-results.json.

Usage:
  run_robot.py KEY [--env qa] [--paths tests/ui tests/api] [--include TAG ...] [--no-rerun]
  run_robot.py KEY --dryrun          # syntax/keyword check only (used by robot-automation agent)

Selection defaults to tests tagged with the story key. Each run goes to
.stories/KEY/results/run-N/. Robot's own exit code (= number of failed tests) is
NOT treated as an error; only usage/data errors (rc >= 252) are.

The test repo's root .env (RBAC role credentials COMS_<ROLE>_USERNAME / COMS_<ROLE>_PASSWORD) is loaded into
every Robot run, so tests can use %{COMS_<ROLE>_USERNAME}. Variables already exported in the shell win.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

from common import config, die, out, repo_root, story_dir, validate_key, write_json


def next_run_dir(key: str, dryrun: bool):
    base = story_dir(key) / "results"
    base.mkdir(parents=True, exist_ok=True)
    if dryrun:
        d = base / "dryrun"
        d.mkdir(exist_ok=True)
        return d
    n = 1 + max([int(p.name.split("-")[1]) for p in base.glob("run-*") if p.name.split("-")[1].isdigit()] or [0])
    d = base / f"run-{n}"
    d.mkdir()
    return d


def base_args(env_name: str) -> list[str]:
    cfg = config()
    args = [a.replace("${env}", env_name) for a in cfg.get("robot", {}).get("run_args", [])]
    envs = cfg.get("environments", {})
    if env_name not in envs:
        die(f"Environment '{env_name}' not in .claude/qe.config.yaml environments: {list(envs)}")
    for k, v in envs[env_name].items():
        args += ["--variable", f"{k.upper()}:{v}"]
    return args


def test_repo_env() -> dict:
    """Environment for Robot: this process's env plus the test repo's root .env (RBAC role credentials
    COMS_<ROLE>_USERNAME/PASSWORD, used in tests as %{...}). Variables already exported in the shell win."""
    env = dict(os.environ)
    path = repo_root() / ".env"
    if not path.is_file():
        return env
    try:
        from dotenv import dotenv_values
        values = {k: v for k, v in dotenv_values(path).items() if v is not None}
    except ImportError:
        values = {}
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                if k.startswith("export "):
                    k = k[len("export "):].strip()
                values[k] = v.strip().strip('"').strip("'")
    for k, v in values.items():
        env.setdefault(k, v)
    return env


def run(cmd: list[str]) -> int:
    print("$ " + " ".join(cmd), file=sys.stderr)   # args only; credential values never go on the command line
    # Robot console output -> stderr so stdout stays pure JSON
    return subprocess.run(cmd, cwd=repo_root(), stdout=sys.stderr, env=test_repo_env()).returncode


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("key")
    ap.add_argument("--env")
    ap.add_argument("--paths", nargs="*")
    ap.add_argument("--include", nargs="*", help="Tags to include (default: the story key)")
    ap.add_argument("--no-rerun", action="store_true")
    ap.add_argument("--dryrun", action="store_true")
    a = ap.parse_args()
    key = validate_key(a.key)
    cfg = config()
    env_name = a.env or cfg.get("robot", {}).get("default_env", "qa")
    tr = cfg.get("test_repo", {})
    paths = a.paths or [d for d in (tr.get("ui_suites_dir", "tests/ui"), tr.get("api_suites_dir", "tests/api"))
                        if (repo_root() / d).is_dir() and any((repo_root() / d).rglob("*.robot"))] or ["tests"]
    includes = a.include or [key]
    outdir = next_run_dir(key, a.dryrun)

    cmd = ["robot", "--outputdir", str(outdir)]
    for t in includes:
        cmd += ["--include", t]
    cmd += base_args(env_name)
    if a.dryrun:
        cmd.append("--dryrun")
    cmd += paths
    rc = run(cmd)
    if rc >= 252:
        die(f"Robot failed to run (rc={rc}). Check suite paths/options/syntax, and that tests are tagged "
            f"with {includes}.", rc=rc, outdir=str(outdir), paths=paths)

    from robot_summary import merge_rerun, summarize

    output_xml = outdir / "output.xml"
    summary = summarize(str(output_xml))
    rerun_rc = None
    if not a.dryrun and not a.no_rerun and cfg.get("robot", {}).get("rerun_failed", True) and summary["stats"]["fail"]:
        rerun_xml = outdir / "rerun.xml"
        rcmd = ["robot", "--outputdir", str(outdir), "--output", "rerun.xml", "--log", "rerun-log.html",
                "--report", "NONE", "--rerunfailed", str(output_xml)] + base_args(env_name) + paths
        rerun_rc = run(rcmd)
        if rerun_xml.is_file():
            summary = merge_rerun(summary, summarize(str(rerun_xml)))

    summary.update({"story": key, "environment": env_name, "run_dir": str(outdir.relative_to(repo_root())),
                    "dryrun": a.dryrun, "robot_rc": rc, "rerun_rc": rerun_rc,
                    "log_html": str((outdir / "log.html").relative_to(repo_root()))})
    if not a.dryrun:
        write_json(story_dir(key) / "05-results.json", summary)
    brief = {k: summary[k] for k in ("story", "environment", "run_dir", "dryrun", "stats", "log_html")}
    brief["failed_tests"] = [{"name": t["name"], "message": t["message"][:300], "flaky": t.get("flaky", False)}
                             for t in summary["tests"] if t["status"] == "FAIL" or t.get("flaky")]
    out(brief)


if __name__ == "__main__":
    main()
