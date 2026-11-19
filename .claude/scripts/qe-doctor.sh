#!/usr/bin/env bash
# =============================================================================
# qe-doctor — checks that everything the QE agent harness needs is in place.
#
# Usage:  .claude/scripts/qe-doctor.sh [--online] [--no-color] [--help]
#   --online    also call Jira, Zephyr Scale and GitLab with your tokens, check that the names in
#               qe.config.yaml exist there (issue types, statuses, environments), and check the app URLs
#   --no-color  plain output (e.g. for CI logs)
#
# Env:    QE_PYTHON=/path/to/python   interpreter to check (default: python3 on PATH; activate your
#                                     Robot virtualenv first, because the harness scripts run with it)
# Exit:   0 = no failures (warnings allowed), 1 = at least one failure.
# Secrets are never printed. Works with the bash 3.2 that ships with macOS.
# =============================================================================
set -u

ONLINE=0; COLOR=1
for arg in "$@"; do
  case "$arg" in
    --online) ONLINE=1 ;;
    --no-color) COLOR=0 ;;
    -h|--help) sed -n '3,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)"; exit 2 ;;
  esac
done
[ -t 1 ] || COLOR=0

if [ "$COLOR" = 1 ]; then
  G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; B=$'\033[1m'; D=$'\033[2m'; N=$'\033[0m'
else
  G=""; Y=""; R=""; B=""; D=""; N=""
fi

PASSES=0; WARNS=0; FAILS=0
RESULTS="$(mktemp -t qe-doctor-res.XXXXXX)"; TMP=""
trap 'rm -f "$RESULTS" ${TMP:+"$TMP" "$TMP.err"}' EXIT
CUR_SECTION=""
# Each result is one tab-separated record: section, status, check, fix. The table is drawn at the end.
clean() { printf '%s' "$1" | tr '\t\n' '  '; }
record() { printf '%s\t%s\t%s\t%s\n' "$CUR_SECTION" "$1" "$(clean "$2")" "$(clean "${3:-}")" >> "$RESULTS"; }
pass() { PASSES=$((PASSES+1)); record PASS "$1"; }
warn() { WARNS=$((WARNS+1));  record WARN "$1" "${2:-}"; }
fail() { FAILS=$((FAILS+1));  record FAIL "$1" "${2:-}"; }
info() { record INFO "$1"; }
section() { CUR_SECTION="$1"; }

# Draws the results as a table that fits the terminal, wrapping long cells. ASCII borders keep the
# column widths right in any terminal and awk version.
render_table() {
  local width
  width="${COLUMNS:-}"; [ -z "$width" ] && width="$(tput cols 2>/dev/null || echo 120)"
  [ "$width" -lt 90 ] 2>/dev/null && width=90
  [ "$width" -gt 180 ] 2>/dev/null && width=180
  awk -F'\t' -v W="$width" -v color="$COLOR" '
    function wrap(s, w, arr,    n, line, i, nw, words, word) {
      n = 0; line = ""
      nw = split(s, words, " ")
      for (i = 1; i <= nw; i++) {
        word = words[i]; if (word == "") continue
        while (length(word) > w) {                       # hard-split very long words (paths, URLs)
          if (line != "") { arr[++n] = line; line = "" }
          arr[++n] = substr(word, 1, w); word = substr(word, w + 1)
        }
        if (line == "") line = word
        else if (length(line) + 1 + length(word) <= w) line = line " " word
        else { arr[++n] = line; line = word }
      }
      if (line != "" || n == 0) arr[++n] = line
      return n
    }
    function pad(s, w) { return s sprintf("%" (w - length(s)) "s", "") }
    function rule(c) { return c repeat("-", SW + 2) c repeat("-", TW + 2) c repeat("-", CW + 2) c repeat("-", FW + 2) c }
    function repeat(ch, n,    out) { out = ""; while (n-- > 0) out = out ch; return out }
    function stat(st,    txt) {
      txt = pad(st, TW)
      if (!color) return txt
      if (st == "PASS") return "\033[32m" txt "\033[0m"
      if (st == "WARN") return "\033[33m" txt "\033[0m"
      if (st == "FAIL") return "\033[31;1m" txt "\033[0m"
      return "\033[2m" txt "\033[0m"
    }
    { sec[NR] = $1; st[NR] = $2; chk[NR] = $3; fix[NR] = $4; if (length($4) > maxfix) maxfix = length($4) }
    END {
      SW = 12; TW = 6
      rest = W - SW - TW - 13
      FW = int(rest * 0.45)                    # the Fix column takes only what it needs (min 12)
      if (maxfix < FW) FW = (maxfix > 12) ? maxfix : 12
      CW = rest - FW
      print rule("+")
      print "| " pad("Section", SW) " | " pad("Status", TW) " | " pad("Check", CW) " | " pad("Fix", FW) " |"
      print rule("+")
      prev = ""
      for (r = 1; r <= NR; r++) {
        if (r > 1 && sec[r] != prev) print rule("+")
        delete a; delete b
        na = wrap(chk[r], CW, a); nb = wrap(fix[r], FW, b)
        nl = (na > nb) ? na : nb
        for (l = 1; l <= nl; l++) {
          scell = (l == 1 && sec[r] != prev) ? sec[r] : ""
          tcell = (l == 1) ? stat(st[r]) : pad("", TW)
          printf "| %s | %s | %s | %s |\n", pad(substr(scell, 1, SW), SW), tcell, pad((l <= na) ? a[l] : "", CW), pad((l <= nb) ? b[l] : "", FW)
        }
        prev = sec[r]
      }
      print rule("+")
    }' "$RESULTS"
}

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HARNESS="$(cd "$SCRIPT_DIR/.." && pwd)"          # <repo>/.claude
ROOT="$(cd "$HARNESS/.." && pwd)"                 # test repo root
PY="${QE_PYTHON:-python3}"

printf "${B}QE agent harness doctor${N}  ${D}(repo: %s)${N}\n" "$(echo "$ROOT" | sed "s#^$HOME#~#")"
printf "${D}Running checks%s...${N}\n" "$([ "$ONLINE" = 1 ] && echo ', including the online ones')"

# --------------------------------------------------------------------------- tools
section "Tools"
if command -v "$PY" >/dev/null 2>&1; then
  PYV="$("$PY" -c 'import sys;print("%d.%d.%d"%sys.version_info[:3])' 2>/dev/null)"
  if "$PY" -c 'import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)' 2>/dev/null; then
    pass "Python $PYV ($(command -v "$PY" | sed "s#^$HOME#~#"))"
  else
    fail "Python $PYV is too old (need 3.9+)" "Install Python 3.9+ or set QE_PYTHON"
  fi
  if [ -z "${VIRTUAL_ENV:-}" ] && [ -z "${QE_PYTHON:-}" ]; then
    info "No virtualenv active. Checking the system python3; activate your Robot venv if you use one."
  fi
else
  fail "Python not found ($PY)" "Install Python 3.9+, or set QE_PYTHON=/path/to/python"
  PY=""
fi

if command -v git >/dev/null 2>&1; then pass "git $(git --version | awk '{print $3}')"; else fail "git not found" "Install git"; fi

if command -v node >/dev/null 2>&1; then
  NODEV="$(node --version | sed 's/^v//')"; NODEMAJ="${NODEV%%.*}"
  if [ "$NODEMAJ" -ge 18 ] 2>/dev/null; then pass "Node.js $NODEV (needed by Browser Library)"
  else fail "Node.js $NODEV is too old for Browser Library (need 18+)" "Install a current Node.js LTS"; fi
else
  fail "Node.js not found (Browser Library needs it)" "Install Node.js LTS, then run: rfbrowser init"
fi

PYBIN=""; [ -n "$PY" ] && PYBIN="$(dirname "$(command -v "$PY")")"
if command -v robot >/dev/null 2>&1; then pass "robot CLI on PATH"
elif [ -n "$PYBIN" ] && [ -x "$PYBIN/robot" ]; then
  warn "robot is installed next to $PY but isn't on PATH" "Activate that virtualenv before starting claude, so the agents can run robot"
else fail "robot CLI not found" "pip install -r requirements-qe.txt (inside your venv)"; fi

if command -v claude >/dev/null 2>&1; then
  pass "Claude Code $(claude --version 2>/dev/null | head -1)"
else
  warn "Claude Code CLI (claude) not on PATH" "Fine if you use the desktop app or IDE extension"
fi

# --------------------------------------------------------------------------- python packages
section "Packages"
if [ -n "$PY" ]; then
  check_pkg() { # module, pip name, level(fail|warn), purpose
    local ver
    if ver="$("$PY" -c "import importlib, importlib.metadata as m
mod = importlib.import_module('$1')
try: print(m.version('$2'))
except Exception: print(getattr(mod, '__version__', 'installed'))" 2>/dev/null)"; then
      pass "$2 $ver"
    elif [ "$3" = fail ]; then fail "$2 missing ($4)" "pip install -r requirements-qe.txt"
    else warn "$2 missing ($4)" "pip install -r requirements-qe.txt"; fi
  }
  check_pkg requests       requests                     fail "REST clients"
  check_pkg yaml           PyYAML                       fail "reads qe.config.yaml"
  check_pkg dotenv         python-dotenv                warn "a built-in .env parser is used without it"
  check_pkg robot          robotframework               fail "test execution and results parsing"
  check_pkg Browser        robotframework-browser       fail "UI tests"
  check_pkg RequestsLibrary robotframework-requests     fail "API tests"

  BROWSER_STATE="$("$PY" - <<'EOF' 2>/dev/null
import os
try:
    import Browser
except Exception:
    print("nolib"); raise SystemExit
w = os.path.join(os.path.dirname(Browser.__file__), "wrapper", "node_modules")
if not os.path.isdir(w):
    print("noinit"); raise SystemExit
lb = os.path.join(w, "playwright-core", ".local-browsers")
print("ok" if os.path.isdir(lb) and os.listdir(lb) else "nobrowsers")
EOF
)"
  case "$BROWSER_STATE" in
    ok)         pass "Browser Library initialised (Playwright + browsers installed)" ;;
    noinit)     fail "Browser Library not initialised" "Run: rfbrowser init" ;;
    nobrowsers) warn "Browser Library node deps present, but couldn't confirm the Playwright browsers" "If UI tests fail to launch, run: rfbrowser init" ;;
    *)          : ;;  # library missing, already reported
  esac
else
  fail "Skipped (no Python)"
fi

# --------------------------------------------------------------------------- harness files
section "Harness"
missing=""
for a in jira-user-story requirement-traceability zephyr-test-case robot-automation triage bug pull-request; do
  [ -f "$HARNESS/agents/$a.md" ] || missing="$missing $a"
done
[ -z "$missing" ] && pass "7 agents in .claude/agents/" || fail "Missing agents:$missing"

[ -f "$HARNESS/skills/qe-manager/SKILL.md" ] && pass "QE Manager skill" || fail "Missing .claude/skills/qe-manager/SKILL.md"

missing=""
for c in qe-story qe-trace qe-testcases qe-automate qe-triage qe-sync-results qe-bugs qe-pr qe-status; do
  [ -f "$HARNESS/commands/$c.md" ] || missing="$missing $c"
done
[ -z "$missing" ] && pass "Phase commands in .claude/commands/" || fail "Missing commands:$missing"

missing=""
for s in common.py adf.py story_state.py jira_cli.py zephyr_cli.py gitlab_cli.py trace_score.py testid_index.py run_robot.py robot_summary.py; do
  [ -f "$HARNESS/scripts/$s" ] || missing="$missing $s"
done
[ -z "$missing" ] && pass "Helper scripts in .claude/scripts/" || fail "Missing scripts:$missing"

missing=""
for t in story.md traceability.json test-cases.json automation.md triage-report.md bug-draft.md mr-draft.md; do
  [ -f "$HARNESS/templates/$t" ] || missing="$missing $t"
done
[ -z "$missing" ] && pass "Templates in .claude/templates/" || fail "Missing templates:$missing"

[ -f "$HARNESS/settings.json" ] && pass ".claude/settings.json (permissions)" || fail "Missing .claude/settings.json" "Without it there are no ask/deny rules on external writes"
[ -f "$ROOT/CLAUDE.md" ] && pass "CLAUDE.md at the repo root" || fail "Missing CLAUDE.md at the repo root" "Claude Code loads project instructions from there"
[ -f "$HARNESS/qe.config.yaml" ] && pass ".claude/qe.config.yaml" || fail "Missing .claude/qe.config.yaml"

# --------------------------------------------------------------------------- git
section "Git"
if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  pass "Git repository (branch: $(git -C "$ROOT" branch --show-current 2>/dev/null))"
  if git -C "$ROOT" remote get-url origin >/dev/null 2>&1; then
    pass "Remote 'origin' is set"
  else
    fail "No 'origin' remote" "The PR phase pushes to origin. Run: git remote add origin <gitlab url>"
  fi
  for p in .claude/.env .stories/ .claude/settings.local.json; do
    probe="$p"; [ "${p%/}" != "$p" ] && probe="${p}probe"
    if git -C "$ROOT" check-ignore -q "$probe" 2>/dev/null; then pass "$p is git-ignored"
    else fail "$p is NOT git-ignored" "Append the harness .gitignore entries to the repo's .gitignore"; fi
  done
else
  fail "$ROOT is not a git repository" "Copy the harness into the root of your Robot Framework test repo"
fi

# --------------------------------------------------------------------------- config, secrets, repos (+ online)
if [ -n "$PY" ]; then
  TMP="$(mktemp -t qe-doctor.XXXXXX)"
  "$PY" - "$ROOT" "$ONLINE" > "$TMP" 2>"$TMP.err" <<'EOF'
import json, os, sys
from pathlib import Path

root, online = Path(sys.argv[1]), sys.argv[2] == "1"
harness = root / ".claude"

def emit(st, msg, hint=""):
    print(f"{st}|{msg}|{hint}".replace("\n", " "))
    sys.stdout.flush()

def section(name):
    emit("SECTION", name)

# ---- config
section("Config")
try:
    import yaml
except ImportError:
    emit("FAIL", "PyYAML missing, so the config can't be checked", "pip install -r requirements-qe.txt")
    raise SystemExit
try:
    cfg = yaml.safe_load((harness / "qe.config.yaml").read_text()) or {}
    emit("PASS", "Config parses")
except FileNotFoundError:
    raise SystemExit
except Exception as e:
    emit("FAIL", f"Config does not parse: {e}")
    raise SystemExit

for path in ("jira.project_key", "zephyr.project_key", "gitlab.project_path", "traceability.threshold"):
    cur = cfg
    for part in path.split("."):
        cur = cur.get(part) if isinstance(cur, dict) else None
    emit("PASS" if cur not in (None, "") else "FAIL", f"{path} = {cur}" if cur not in (None, "") else f"{path} is not set")

if not (cfg.get("jira") or {}).get("acceptance_criteria_field"):
    emit("INFO", "jira.acceptance_criteria_field is null, so ACs are parsed from the description heading")

envs = cfg.get("environments") or {}
if not envs:
    emit("FAIL", "No environments configured")
for name, e in envs.items():
    urls = [e.get("ui_base_url", ""), e.get("api_base_url", "")]
    if not all(urls):
        emit("FAIL", f"environments.{name} is missing ui_base_url or api_base_url")
    elif any("example.com" in u for u in urls):
        emit("WARN", f"environments.{name} still has the example.com placeholder URLs", "Set your real UI/API base URLs")
    else:
        emit("PASS", f"environments.{name}: {urls[0]}")
default_env = (cfg.get("robot") or {}).get("default_env")
if default_env and default_env not in envs:
    emit("FAIL", f"robot.default_env '{default_env}' is not in environments")
extra = set(((cfg.get("zephyr") or {}).get("environment_map") or {})) - set(envs)
if extra:
    emit("WARN", f"zephyr.environment_map has unknown environments: {sorted(extra)}")

tr = cfg.get("test_repo") or {}
for k in ("ui_suites_dir", "api_suites_dir", "resources_dir"):
    d = tr.get(k)
    if d and (root / d).is_dir():
        emit("PASS", f"test_repo.{k}: {d}")
    elif d:
        emit("WARN", f"test_repo.{k}: {d} does not exist yet", "Fix the path, or let robot-automation create it")

# ---- application repos
section("App repos")
repos = cfg.get("application_repos") or {}
resolved = []
for kind in ("frontend", "backend"):
    for r in repos.get(kind) or []:
        p = Path(r.get("path", "")).expanduser()
        p = p if p.is_absolute() else (root / p).resolve()
        label = f"{kind}: {r.get('name')} ({r.get('stack')})"
        shown = os.path.relpath(p, root) if str(p).startswith(str(root.parent)) else str(p).replace(str(Path.home()), "~")
        if not p.is_dir():
            emit("FAIL", f"{label} not found at {shown}", "Clone it there or fix application_repos in qe.config.yaml")
            continue
        resolved.append(p)
        bad = [s for s in r.get("src_dirs") or [] if not (p / s).is_dir()]
        if bad:
            emit("WARN", f"{label}: src_dirs not found: {bad}")
        elif not (p / ".git").exists():
            emit("WARN", f"{label} at {shown} is not a git clone", "Traceability records the git SHA it analysed")
        else:
            emit("PASS", f"{label} at {shown}")
        if kind == "frontend":
            count = 0
            for s in r.get("src_dirs") or ["src"]:
                for dirpath, dirnames, files in os.walk(p / s):
                    dirnames[:] = [d for d in dirnames if d not in ("node_modules", "build", "dist", ".git", "coverage")]
                    for f in files:
                        if f.endswith((".js", ".jsx", ".ts", ".tsx")):
                            try:
                                count += (Path(dirpath) / f).read_text(errors="ignore").count("data-testid")
                            except OSError:
                                pass
            if count:
                emit("PASS", f"{r.get('name')}: {count} data-testid attributes found")
            else:
                emit("WARN", f"{r.get('name')}: no data-testid found", "UI locators come only from data-testid, so expect locator gaps")
if not resolved:
    emit("FAIL", "No application repos are reachable")

local = harness / "settings.local.json"
if not local.is_file():
    emit("FAIL", ".claude/settings.local.json is missing, so Claude Code can't read the app repos",
         "cp .claude/settings.local.json.example .claude/settings.local.json and list the repo paths")
else:
    try:
        dirs = json.loads(local.read_text()).get("permissions", {}).get("additionalDirectories", [])
        allowed = []
        for d in dirs:
            dp = Path(d).expanduser()
            allowed.append((dp if dp.is_absolute() else (root / dp)).resolve())
        missing = [os.path.relpath(p, root) for p in resolved if not any(p == a or a in p.parents for a in allowed)]
        if missing:
            emit("FAIL", f"Not in additionalDirectories: {missing}", "Add them to .claude/settings.local.json")
        else:
            emit("PASS", "All app repos are listed in .claude/settings.local.json additionalDirectories")
    except Exception as e:
        emit("FAIL", f".claude/settings.local.json is not valid JSON: {e}")

# ---- secrets
section("Secrets")
env_file = harness / ".env"
vals = {}
if not env_file.is_file():
    emit("FAIL", ".claude/.env not found", "cp .claude/.env.example .claude/.env and fill it in")
else:
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    if (root / ".env").is_file():
        emit("WARN", "A .env exists at the repo root and is IGNORED; only .claude/.env is loaded")
for k in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "ZEPHYR_API_TOKEN", "GITLAB_URL", "GITLAB_TOKEN"):
    v = vals.get(k) or os.environ.get(k, "")
    if not v:
        emit("FAIL", f"{k} is empty")
    elif "your-company" in v:
        emit("FAIL", f"{k} still has the placeholder value")
    else:
        emit("PASS", f"{k} is set")
for k in ("QE_TEST_USER", "QE_TEST_PASSWORD"):
    emit("PASS" if (vals.get(k) or os.environ.get(k)) else "WARN", f"{k} is {'set' if (vals.get(k) or os.environ.get(k)) else 'empty (needed if your Robot tests log in with it)'}")

if not online:
    raise SystemExit

# ---- online checks
section("Connectivity")
try:
    import requests
except ImportError:
    emit("FAIL", "requests is missing, so the online checks were skipped")
    raise SystemExit
from urllib.parse import quote
g = lambda k: vals.get(k) or os.environ.get(k, "")

def get(url, **kw):
    try:
        r = requests.get(url, timeout=15, **kw)
        return r.status_code, (r.json() if "json" in r.headers.get("Content-Type", "") else None)
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e).split('(Caused by')[0][:110]}"

def why(code, body):
    return f"HTTP {code}" if code else f"connection error, {body}"

jira = g("JIRA_BASE_URL").rstrip("/"); auth = (g("JIRA_EMAIL"), g("JIRA_API_TOKEN"))
code, body = get(f"{jira}/rest/api/3/myself", auth=auth)
if code == 200:
    emit("PASS", f"Jira auth OK (as {body.get('displayName')})")
    jk = cfg["jira"]["project_key"]
    code, proj = get(f"{jira}/rest/api/3/project/{jk}", auth=auth)
    if code == 200:
        types = {t["name"] for t in proj.get("issueTypes", [])}
        emit("PASS", f"Jira project {jk} found")
        b = cfg["jira"].get("bug") or {}
        for key in ("issue_type", "child_issue_type"):
            name = b.get(key)
            if name:
                emit("PASS" if name in types else "FAIL", f"jira.bug.{key} '{name}' " + ("exists" if name in types else f"not in project issue types {sorted(types)}"))
    else:
        emit("FAIL", f"Jira project {jk} not accessible (HTTP {code})")
else:
    emit("FAIL", f"Jira auth failed ({why(code, body)})", "Check JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN")

z = (cfg.get("zephyr") or {}); zb = z.get("base_url", "https://api.zephyrscale.smartbear.com/v2").rstrip("/")
zh = {"Authorization": f"Bearer {g('ZEPHYR_API_TOKEN')}"}
code, body = get(f"{zb}/projects/{z.get('project_key')}", headers=zh)
if code == 200:
    emit("PASS", f"Zephyr Scale auth OK, project {z.get('project_key')} found")
    code, st = get(f"{zb}/statuses", headers=zh, params={"projectKey": z.get("project_key"), "statusType": "TEST_EXECUTION", "maxResults": 100})
    if code == 200:
        names = {s.get("name") for s in st.get("values", [])}
        wanted = set((z.get("status_map") or {}).values()) | {z.get("blocked_status", "Blocked")}
        miss = sorted(w for w in wanted if w not in names)
        emit("FAIL" if miss else "PASS", f"Zephyr execution statuses missing: {miss}" if miss else "Zephyr execution statuses in status_map/blocked_status exist",
             f"Available: {sorted(names)}" if miss else "")
    code, st = get(f"{zb}/statuses", headers=zh, params={"projectKey": z.get("project_key"), "statusType": "TEST_CASE", "maxResults": 100})
    if code == 200:
        names = {s.get("name") for s in st.get("values", [])}
        dflt = z.get("default_status", "Draft")
        emit("PASS" if dflt in names else "FAIL", f"Zephyr test case status '{dflt}' " + ("exists" if dflt in names else f"not found; available: {sorted(names)}"))
    emap = z.get("environment_map") or {}
    if emap:
        code, ev = get(f"{zb}/environments", headers=zh, params={"projectKey": z.get("project_key"), "maxResults": 100})
        if code == 200:
            names = {e.get("name") for e in ev.get("values", [])}
            miss = sorted(v for v in emap.values() if v not in names)
            emit("FAIL" if miss else "PASS", f"Zephyr environments missing: {miss}" if miss else "Zephyr environments in environment_map exist",
                 "Create them in Zephyr project settings, or remove them from environment_map" if miss else "")
else:
    emit("FAIL", f"Zephyr Scale not accessible ({why(code, body)})", "Check ZEPHYR_API_TOKEN and zephyr.project_key")

gl = g("GITLAB_URL").rstrip("/"); gh = {"PRIVATE-TOKEN": g("GITLAB_TOKEN")}
code, body = get(f"{gl}/api/v4/user", headers=gh)
if code == 200:
    emit("PASS", f"GitLab auth OK (as {body.get('username')})")
    pp = (cfg.get("gitlab") or {}).get("project_path", "")
    code, proj = get(f"{gl}/api/v4/projects/{quote(pp, safe='')}", headers=gh)
    if code == 200:
        emit("PASS", f"GitLab project {pp} found")
        tb = (cfg.get("gitlab") or {}).get("target_branch", "main")
        code, _ = get(f"{gl}/api/v4/projects/{quote(pp, safe='')}/repository/branches/{quote(tb, safe='')}", headers=gh)
        emit("PASS" if code == 200 else "FAIL", f"Target branch '{tb}' " + ("exists" if code == 200 else "not found"))
    else:
        emit("FAIL", f"GitLab project {pp} not accessible (HTTP {code})", "Check gitlab.project_path and the token scope (api)")
else:
    emit("FAIL", f"GitLab auth failed ({why(code, body)})", "Check GITLAB_URL / GITLAB_TOKEN")

section("App URLs")
checked = 0
for name, e in envs.items():
    for k in ("ui_base_url", "api_base_url"):
        u = e.get(k)
        if not u or "example.com" in u:
            continue
        checked += 1
        try:
            r = requests.get(u, timeout=10, allow_redirects=True)
            emit("PASS" if r.status_code < 500 else "WARN", f"{name}.{k} reachable (HTTP {r.status_code})")
        except Exception as ex:
            emit("WARN", f"{name}.{k} not reachable: {type(ex).__name__}", "VPN? The environment may be down")
if not checked:
    emit("INFO", "No real app URLs configured yet (only placeholders), so nothing to check")
EOF
  PYRC=$?
  while IFS='|' read -r st msg hint; do
    case "$st" in
      SECTION) section "$msg" ;;
      PASS) pass "$msg" ;;
      WARN) warn "$msg" "$hint" ;;
      FAIL) fail "$msg" "$hint" ;;
      INFO) info "$msg" ;;
    esac
  done < "$TMP"
  if [ "$PYRC" -ne 0 ]; then
    fail "The config/secrets checks crashed (exit $PYRC)" "$(tail -1 "$TMP.err")"
  fi
fi

# --------------------------------------------------------------------------- table + summary
echo
render_table
printf "\n${B}Summary:${N} ${G}%d passed${N}, ${Y}%d warnings${N}, ${R}%d failed${N}\n" "$PASSES" "$WARNS" "$FAILS"
if [ "$FAILS" -gt 0 ]; then
  printf "${R}Fix the failures above before running /qe-manager.${N}\n"; exit 1
elif [ "$WARNS" -gt 0 ]; then
  printf "${Y}Ready, but review the warnings.${N}\n"
else
  printf "${G}All good. Ready for /qe-manager <KEY>.${N}\n"
fi
[ "$ONLINE" = 0 ] && printf "${D}Tip: run with --online to also check Jira, Zephyr, GitLab and the app URLs.${N}\n"
exit 0
