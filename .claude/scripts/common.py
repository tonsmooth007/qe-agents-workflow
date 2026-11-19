"""Shared helpers for the QE harness scripts: config, env, HTTP, output, story paths."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML missing. Run: pip install -r requirements-qe.txt")

HARNESS_DIR = ".claude"
STORIES_DIR = ".stories"  # per-story workspace at <repo root>/.stories/ (git-ignored)
CONFIG_NAME = "qe.config.yaml"  # lives in <repo root>/.claude/
STORY_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")


# --------------------------------------------------------------------------- paths/config
def repo_root() -> Path:
    """Test repo root = the directory containing .claude/qe.config.yaml.

    Walks up from CWD first, then from this file (.claude/scripts/). .stories/, tests/ and every
    relative path in the config are resolved against this root, not against .claude/.
    """
    for start in (Path.cwd(), Path(__file__).resolve().parent):
        for d in [start, *start.parents]:
            if (d / HARNESS_DIR / CONFIG_NAME).is_file():
                return d
    sys.exit(f"Could not find {HARNESS_DIR}/{CONFIG_NAME} in CWD or its parents.")


def harness_dir() -> Path:
    return repo_root() / HARNESS_DIR


_CONFIG: dict | None = None


def config() -> dict:
    global _CONFIG
    if _CONFIG is None:
        root = repo_root()
        with open(root / HARNESS_DIR / CONFIG_NAME, encoding="utf-8") as fh:
            _CONFIG = yaml.safe_load(fh) or {}
        _load_env(root)
    return _CONFIG


def resolve_path(p: str) -> Path:
    path = Path(p).expanduser()
    return path if path.is_absolute() else (repo_root() / path).resolve()


def _load_env(root: Path) -> None:
    env_file = root / HARNESS_DIR / ".env"  # <repo root>/.claude/.env
    if not env_file.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_file, override=False)
    except ImportError:  # minimal fallback parser
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_test_repo_env() -> dict:
    """This process's env plus the test repo's ROOT .env (RBAC role credentials COMS_<ROLE>_USERNAME/PASSWORD).

    Used by run_robot.py (tests read them as %{...}) and explore_login.py. Variables already exported in the
    shell win. Callers must never print or log the values.
    """
    env_vars = dict(os.environ)
    path = repo_root() / ".env"
    if not path.is_file():
        return env_vars
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
        env_vars.setdefault(k, v)
    return env_vars


def env(name: str, required: bool = True) -> str:
    config()  # ensure .env loaded
    val = os.environ.get(name, "")
    if required and not val:
        die(f"Environment variable {name} is not set (see .claude/.env.example; copy it to .claude/.env).")
    return val


def validate_key(key: str) -> str:
    key = key.strip().upper()
    if not STORY_KEY_RE.match(key):
        die(f"'{key}' does not look like a Jira key (e.g. LOAN-123).")
    return key


def story_dir(key: str, create: bool = True) -> Path:
    d = repo_root() / STORIES_DIR / validate_key(key)
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------------------------------- output
def out(data: Any) -> None:
    """Print JSON to stdout (the contract every script follows)."""
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def die(msg: str, code: int = 1, **extra: Any) -> None:
    print(json.dumps({"ok": False, "error": msg, **extra}, indent=2), file=sys.stderr)
    sys.exit(code)


def read_json(path: Path | str) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path | str, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


# --------------------------------------------------------------------------- front matter
FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.S)


def read_front_matter(path: Path | str) -> tuple[dict, str]:
    text = Path(path).read_text(encoding="utf-8")
    m = FM_RE.match(text)
    if not m:
        die(f"{path} has no YAML front matter (--- ... ---).")
    return (yaml.safe_load(m.group(1)) or {}), m.group(2)


def write_front_matter(path: Path | str, meta: dict, body: str) -> None:
    fm = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip()
    Path(path).write_text(f"---\n{fm}\n---\n{body}", encoding="utf-8")


# --------------------------------------------------------------------------- HTTP
class Http:
    """Thin requests wrapper with retries, JSON errors and --dry-run support."""

    def __init__(self, base_url: str, headers: dict | None = None, auth: Any = None, dry_run: bool = False):
        import requests

        self.base = base_url.rstrip("/")
        self.s = requests.Session()
        self.s.headers.update({"Accept": "application/json", **(headers or {})})
        if auth:
            self.s.auth = auth
        self.dry_run = dry_run

    def url(self, path: str) -> str:
        return path if path.startswith("http") else f"{self.base}/{path.lstrip('/')}"

    def request(self, method: str, path: str, *, write: bool | None = None, **kw: Any) -> Any:
        is_write = write if write is not None else method.upper() not in ("GET", "HEAD")
        if self.dry_run and is_write:
            body = kw.get("json") or kw.get("data") or ("<multipart>" if "files" in kw else None)
            print(json.dumps({"dry_run": True, "method": method, "url": self.url(path), "body": body},
                             indent=2, default=str), file=sys.stderr)
            return {"dry_run": True}
        last = None
        for attempt in range(4):
            resp = self.s.request(method, self.url(path), timeout=60, **kw)
            if resp.status_code in (429, 502, 503, 504):
                wait = float(resp.headers.get("Retry-After", 2 ** attempt))
                time.sleep(min(wait, 30))
                last = resp
                continue
            if resp.status_code >= 400:
                die(f"{method} {self.url(path)} -> HTTP {resp.status_code}", detail=_safe_body(resp))
            if not resp.content:
                return {}
            ctype = resp.headers.get("Content-Type", "")
            return resp.json() if "json" in ctype else resp.content
        die(f"{method} {self.url(path)} kept failing", detail=_safe_body(last) if last is not None else None)

    def get(self, path: str, **kw: Any) -> Any:
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw: Any) -> Any:
        return self.request("POST", path, **kw)

    def put(self, path: str, **kw: Any) -> Any:
        return self.request("PUT", path, **kw)


def _safe_body(resp: Any) -> Any:
    try:
        return resp.json()
    except Exception:
        return (resp.text or "")[:2000]
