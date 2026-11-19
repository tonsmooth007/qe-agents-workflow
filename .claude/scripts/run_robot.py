#!/usr/bin/env python3
"""Run the Robot suites for a story, re-run failures once, and write .stories/KEY/05-results.json.

Usage:
  run_robot.py KEY [--env qa] [--paths tests/ui tests/api] [--include TAG ...] [--no-rerun]
  run_robot.py KEY --dryrun          # syntax/keyword check only (used by robot-automation agent)
  run_robot.py KEY --include LOAN-T101 LOAN-T102 --run-prefix verify --out verify-LOAN-456.json
                                     # subset run (bug verification, impact, heal): results/verify-N/ and a
                                     # separate summary file, so the story's 05-results.json is left alone

Selection defaults to tests tagged with the story key. Each run goes to
.stories/KEY/results/run-N/. Robot's own exit code (= number of failed tests) is
NOT treated as an error; only usage/data errors (rc >= 252) are.

The test repo's root .env (RBAC role credentials COMS_<ROLE>_USERNAME / COMS_<ROLE>_PASSWORD) is loaded into
every Robot run, so tests can use %{COMS_<ROLE>_USERNAME}. Variables already exported in the shell win.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys

from common import config, die, load_test_repo_env as test_repo_env, out, repo_root, story_dir, validate_key, write_json


RUN_PREFIX_RE = re.compile(r"^[a-z][a-z0-9]{0,15}$")
OUT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}\.json$")


def next_run_dir(key: str, dryrun: bool, prefix: str = "run"):
    base = story_dir(key) / "results"
    base.mkdir(parents=True, exist_ok=True)
    if dryrun:
        d = base / "dryrun"
        d.mkdir(exist_ok=True)
        return d
    nums = [int(p.name.rsplit("-", 1)[1]) for p in base.glob(f"{prefix}-*") if p.name.rsplit("-", 1)[1].isdigit()]
    n = 1 + max(nums or [0])
    d = base / f"{prefix}-{n}"
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
    ap.add_argument("--run-prefix", default="run",
                    help="Run folder prefix under .stories/KEY/results/ (default run → run-N)")
    ap.add_argument("--out", default="05-results.json",
                    help="Summary file name in .stories/KEY/ (default 05-results.json, the story's main results)")
    a = ap.parse_args()
    key = validate_key(a.key)
    if not RUN_PREFIX_RE.match(a.run_prefix):
        die("--run-prefix must be lowercase letters/digits, e.g. verify, impact, heal.")
    if not OUT_NAME_RE.match(a.out):
        die("--out must be a plain .json file name (it is written inside .stories/KEY/).")
    cfg = config()
    env_name = a.env or cfg.get("robot", {}).get("default_env", "qa")
    tr = cfg.get("test_repo", {})
    paths = a.paths or [d for d in (tr.get("ui_suites_dir", "tests/ui"), tr.get("api_suites_dir", "tests/api"))
                        if (repo_root() / d).is_dir() and any((repo_root() / d).rglob("*.robot"))] or ["tests"]
    includes = a.include or [key]
    outdir = next_run_dir(key, a.dryrun, a.run_prefix)

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
                    "dryrun": a.dryrun, "robot_rc": rc, "rerun_rc": rerun_rc, "includes": includes,
                    "log_html": str((outdir / "log.html").relative_to(repo_root()))})
    results_file = story_dir(key) / a.out
    if not a.dryrun:
        write_json(results_file, summary)
    brief = {k: summary[k] for k in ("story", "environment", "run_dir", "dryrun", "stats", "log_html")}
    brief["results_file"] = None if a.dryrun else str(results_file.relative_to(repo_root()))
    brief["failed_tests"] = [{"name": t["name"], "message": t["message"][:300], "flaky": t.get("flaky", False)}
                             for t in summary["tests"] if t["status"] == "FAIL" or t.get("flaky")]
    out(brief)


if __name__ == "__main__":
    main()
