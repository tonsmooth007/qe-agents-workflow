#!/usr/bin/env python3
"""Log a playwright-cli browser session in as one RBAC test role, without exposing the credentials.

Used by the exploratory-tester agent. It reads COMS_<ROLE>_USERNAME / COMS_<ROLE>_PASSWORD from the test
repo's root .env (the same file run_robot.py loads), opens <ui_base_url><exploratory.login.path> in the named
playwright-cli session, fills the login form and waits until the app has left the login page. The values only
go to the playwright-cli subprocess: its output is captured and thrown away, and nothing this script prints
contains a username or password. Afterwards the agent keeps driving the same session with
`playwright-cli -s=<session> ...`.

Usage:
  explore_login.py KEY --role ADMIN [--session admin] [--env qa] [--mobile] [--browser chrome] [--dry-run]

Config (.claude/qe.config.yaml):
  exploratory:
    allowed_envs: [qa, uat]
    login:
      path: /login
      username_selector: css=[data-testid="login-username"]
      password_selector: css=[data-testid="login-password"]
      submit_selector:   css=[data-testid="login-submit"]
      success_selector:  css=[data-testid="app-header"]   # optional; otherwise "URL left the login path"
      timeout_ms: 15000

Exit codes: 0 logged in · 1 playwright-cli missing or failed to start · 2 login did not succeed ·
            3 login config missing · 4 environment not allowed · 5 role missing in the root .env
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess

from common import config, die, load_test_repo_env, out, repo_root, validate_key
from test_credentials import roles


def pw_base() -> list[str] | None:
    if shutil.which("playwright-cli"):
        return ["playwright-cli"]
    if shutil.which("npx"):
        probe = subprocess.run(["npx", "--no-install", "playwright", "--version"], capture_output=True, text=True,
                               cwd=repo_root())
        if probe.returncode == 0:
            return ["npx", "--no-install", "playwright", "cli"]
    return None


def sel(s: str) -> str:
    """Robot-style 'css=[data-testid=...]' -> plain CSS for playwright-cli."""
    s = (s or "").strip()
    return s[4:] if s.startswith("css=") else s


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("key")
    ap.add_argument("--role", required=True, help="RBAC role, e.g. ADMIN (reads COMS_<ROLE>_USERNAME/PASSWORD)")
    ap.add_argument("--session", help="playwright-cli session name (default: the role in lower case)")
    ap.add_argument("--env", help="Environment from qe.config.yaml (default: robot.default_env)")
    ap.add_argument("--mobile", action="store_true", help="Open the session with mobile emulation")
    ap.add_argument("--browser", help="chrome | firefox | webkit | msedge")
    ap.add_argument("--dry-run", action="store_true", help="Validate config and role; don't open a browser")
    a = ap.parse_args()

    key = validate_key(a.key)
    role = a.role.strip().upper()
    session = a.session or role.lower()
    cfg = config()
    ex = cfg.get("exploratory") or {}
    env_name = a.env or (cfg.get("robot") or {}).get("default_env", "qa")

    allowed = ex.get("allowed_envs") or ["qa", "uat"]
    if env_name not in allowed:
        die(f"Environment '{env_name}' is not in exploratory.allowed_envs {allowed}.", 4)
    envs = cfg.get("environments") or {}
    if env_name not in envs or not envs[env_name].get("ui_base_url"):
        die(f"environments.{env_name}.ui_base_url is not set in .claude/qe.config.yaml.", 3)

    login = ex.get("login") or {}
    missing_cfg = [k for k in ("path", "username_selector", "password_selector", "submit_selector")
                   if not str(login.get(k) or "").strip() or "TODO" in str(login.get(k))]
    if missing_cfg:
        die("exploratory.login is not configured: " + ", ".join(missing_cfg)
            + ". Take the login form's data-testids from testid_index.py.", 3, missing=missing_cfg)

    env_file = repo_root() / ".env"
    by_name = {r["role"]: r for r in roles(env_file)} if env_file.is_file() else {}
    user_var, pass_var = f"COMS_{role}_USERNAME", f"COMS_{role}_PASSWORD"
    if not by_name.get(role, {}).get("complete"):
        die(f"Credential gap: role {role} is missing or incomplete in the root .env. Add {user_var} and {pass_var}.",
            5, role=role, missing_vars=[user_var, pass_var])

    url = envs[env_name]["ui_base_url"].rstrip("/") + "/" + str(login["path"]).lstrip("/")
    timeout = int(login.get("timeout_ms") or 15000)
    plan = {"story": key, "role": role, "session": session, "env": env_name, "url": url,
            "credentials": {"username": f"%{{{user_var}}}", "password": f"%{{{pass_var}}}"}}
    if a.dry_run:
        out({"ok": True, "dry_run": True, **plan})
        return

    base = pw_base()
    if not base:
        die("playwright-cli not found. Install it (npm install -g @playwright/cli@latest) or add Playwright ≥1.59 "
            "to the repo so `npx --no-install playwright cli` works.", 1)

    env_vars = load_test_repo_env()
    username, password = env_vars.get(user_var, ""), env_vars.get(pass_var, "")

    def pw(*args: str, secret: bool = False) -> subprocess.CompletedProcess:
        # Output is always captured. For secret steps it's never shown, not even on error.
        p = subprocess.run([*base, f"-s={session}", *args], capture_output=True, text=True, cwd=repo_root())
        if p.returncode != 0:
            step = args[0] if secret else " ".join(args[:2])
            detail = "" if secret else (p.stderr or p.stdout)[-500:]
            die(f"playwright-cli {step} failed (rc={p.returncode}).", 2, session=session, detail=detail)
        return p

    open_args = ["open", url]
    if a.mobile:
        open_args.append("--mobile")
    if a.browser:
        open_args.append(f"--browser={a.browser}")
    p = subprocess.run([*base, f"-s={session}", *open_args], capture_output=True, text=True, cwd=repo_root())
    if p.returncode != 0:  # the session may already be open: navigate it instead
        pw("goto", url)

    pw("fill", sel(login["username_selector"]), username, secret=True)
    pw("fill", sel(login["password_selector"]), password, secret=True)
    del username, password
    pw("click", sel(login["submit_selector"]))

    if login.get("success_selector"):
        wait = (f"async page => {{ await page.locator({json.dumps(sel(login['success_selector']))}).first()"
                f".waitFor({{state: 'visible', timeout: {timeout}}}); return page.url(); }}")
    else:
        path = "/" + str(login["path"]).strip("/")
        wait = (f"async page => {{ await page.waitForURL(u => !u.pathname.startsWith({json.dumps(path)}), "
                f"{{timeout: {timeout}}}); return page.url(); }}")
    w = subprocess.run([*base, f"-s={session}", "--raw", "run-code", wait], capture_output=True, text=True,
                       cwd=repo_root())
    if w.returncode != 0:
        die(f"Login as {role} did not succeed within {timeout} ms (still on the login page, or the success element "
            f"never appeared). Check the role's account, or take a snapshot of session '{session}'.", 2,
            session=session, role=role)
    out({"ok": True, **plan, "url_after": w.stdout.strip().strip('"')[:300]})


if __name__ == "__main__":
    main()
