#!/usr/bin/env python3
"""
WorkPilot v2 - Dev environment manager
Works on Windows / macOS / Linux with Python 3.8+

Usage:
    python dev.py start          Start all dev services
    python dev.py stop           Stop all dev services
    python dev.py restart        Restart backend container
    python dev.py status         Show service status
    python dev.py logs [svc]     Tail logs  (default: backend)
    python dev.py pull-models    Pull Ollama models (first run)
    python dev.py psql           Open PostgreSQL shell

Ports when running:
    postgres  :5432
    ollama    :11434
    backend   :8000   (FastAPI hot-reload, Swagger -> http://localhost:8000/docs)
    frontend  :5173   (Vite dev server)
"""

import os
import sys
import shutil
import signal
import subprocess
import platform
import time
from pathlib import Path

# ── paths ─────────────────────────────────────────────────────────

ROOT     = Path(__file__).parent.resolve()
FRONTEND = ROOT / "frontend"
PID_FILE = ROOT / ".frontend.pid"
LOG_FILE = ROOT / ".frontend.log"
ENV_FILE = ROOT / "backend" / ".env"
ENV_EXAMPLE = ROOT / "backend" / ".env.example"

IS_WINDOWS = platform.system() == "Windows"

# ── color output (ANSI, works on Windows 10+ and all Unix) ────────

def _ansi(code):
    # On older Windows cmd.exe ANSI may not work; just skip colors there.
    if IS_WINDOWS and "WT_SESSION" not in os.environ and "TERM" not in os.environ:
        return ""
    return f"\033[{code}m"

CYAN   = _ansi("36");  GREEN  = _ansi("32");  YELLOW = _ansi("33")
RED    = _ansi("31");  WHITE  = _ansi("1;37"); GRAY   = _ansi("90")
RESET  = _ansi("0")

def step(msg):  print(f"  {CYAN}>>{RESET} {msg}")
def ok(msg):    print(f"  {GREEN}OK{RESET} {msg}")
def warn(msg):  print(f"  {YELLOW}!!{RESET} {msg}")
def err(msg):   print(f"  {RED}XX{RESET} {msg}",  file=sys.stderr)
def title(msg): print(f"\n{WHITE}{msg}{RESET}")
def rule():     print(f"  {GRAY}{'-'*50}{RESET}")

# ── subprocess helpers ────────────────────────────────────────────

def run(*cmd, check=True, capture=False, cwd=ROOT):
    """Run a command, streaming output to the terminal by default."""
    kwargs = dict(cwd=cwd)
    if capture:
        kwargs["capture_output"] = True
        kwargs["text"] = True
    result = subprocess.run(list(cmd), **kwargs)
    if check and result.returncode != 0 and not capture:
        sys.exit(result.returncode)
    return result

def dc(*args, check=True, capture=False):
    """Run docker compose (auto-loads override.yml) from ROOT."""
    return run("docker", "compose", *args, check=check, capture=capture, cwd=ROOT)

# ── guards ────────────────────────────────────────────────────────

def assert_docker():
    if not shutil.which("docker"):
        err("docker not found - install Docker Desktop first")
        sys.exit(1)
    r = subprocess.run(["docker", "info"], capture_output=True)
    if r.returncode != 0:
        err("Docker is not running - start Docker Desktop first")
        sys.exit(1)

def assert_node():
    if not shutil.which("node"):
        err("node not found - install Node.js 18+ first")
        sys.exit(1)

def assert_env():
    if not ENV_FILE.exists():
        warn(f"backend/.env not found - copying from .env.example ...")
        shutil.copy(ENV_EXAMPLE, ENV_FILE)
        warn("Edit backend/.env (set JWT_SECRET_KEY + POSTGRES_PASSWORD) then re-run")
        sys.exit(1)

# ── frontend process management ───────────────────────────────────

def _read_pid():
    try:
        return int(PID_FILE.read_text().strip())
    except Exception:
        return None

def _pid_alive(pid):
    if pid is None:
        return False
    try:
        os.kill(pid, 0)   # signal 0 = existence check
        return True
    except (ProcessLookupError, PermissionError):
        return False

def start_frontend():
    pid = _read_pid()
    if _pid_alive(pid):
        warn(f"Frontend already running (PID {pid})")
        return

    PID_FILE.unlink(missing_ok=True)

    node_modules = FRONTEND / "node_modules"
    if not node_modules.exists():
        step("Installing frontend deps (npm install) ...")
        run("npm", "install", "--silent", cwd=FRONTEND)

    step("Starting Vite dev server ...")

    if IS_WINDOWS:
        # Open a new console window; process lives independently
        proc = subprocess.Popen(
            ["cmd", "/k", "npm run dev"],
            cwd=FRONTEND,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
    else:
        # Background process, redirect output to log file
        log = open(LOG_FILE, "w")
        proc = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=FRONTEND,
            stdout=log,
            stderr=log,
            start_new_session=True,   # detach from parent session
        )

    PID_FILE.write_text(str(proc.pid))
    ok(f"Frontend started (PID {proc.pid}) -> http://localhost:5173")
    if not IS_WINDOWS:
        print(f"  {GRAY}Frontend log: tail -f {LOG_FILE}{RESET}")

def stop_frontend():
    pid = _read_pid()
    if pid is None:
        warn("No frontend PID file - skipping")
        return
    if not _pid_alive(pid):
        warn(f"Frontend process (PID {pid}) already gone")
        PID_FILE.unlink(missing_ok=True)
        return

    try:
        if IS_WINDOWS:
            # Kill the whole process tree (cmd + node children)
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           capture_output=True)
        else:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        ok(f"Frontend stopped (PID {pid})")
    except Exception as e:
        warn(f"Could not stop PID {pid}: {e}")
    finally:
        PID_FILE.unlink(missing_ok=True)

def frontend_status():
    pid = _read_pid()
    if pid is None:
        return "not running"
    if _pid_alive(pid):
        return f"running (PID {pid})"
    return "exited (stale pid file)"

# ── backend health check ──────────────────────────────────────────

def wait_for_backend(timeout=90):
    step("Waiting for backend health check ...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = dc("ps", "-q", "backend", capture=True, check=False)
        cid = r.stdout.strip()
        if cid:
            h = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Health.Status}}", cid],
                capture_output=True, text=True
            )
            if h.stdout.strip() == "healthy":
                return True
        elapsed = int(time.time() - deadline + timeout)
        print(f"    {elapsed}s ...", end="\r", flush=True)
        time.sleep(3)
    print()
    return False

# ── actions ───────────────────────────────────────────────────────

ACTION  = sys.argv[1].lower() if len(sys.argv) > 1 else "start"
SERVICE = sys.argv[2]         if len(sys.argv) > 2 else "backend"

if ACTION == "start":
    title("WorkPilot - starting dev environment")
    rule()
    assert_docker()
    assert_node()
    assert_env()

    step("Starting postgres / ollama / backend ...")
    dc("up", "-d", "postgres", "ollama", "backend")

    if wait_for_backend():
        ok("Backend ready -> http://localhost:8000/docs")
    else:
        warn("Health check timed out - run 'python dev.py logs' to investigate")

    start_frontend()

    rule()
    ok("Dev environment is up!")
    print(f"  Frontend  -> {WHITE}http://localhost:5173{RESET}")
    print(f"  Swagger   -> {WHITE}http://localhost:8000/docs{RESET}")
    print(f"  Stop      -> {GRAY}python dev.py stop{RESET}")
    rule()

elif ACTION == "stop":
    title("WorkPilot - stopping")
    rule()
    stop_frontend()
    step("Stopping Docker services ...")
    dc("stop", "backend", "postgres", "ollama")
    ok("Stopped (volumes preserved)")
    print(f"  {GRAY}Wipe all data: docker compose down -v{RESET}")
    rule()

elif ACTION == "restart":
    title("WorkPilot - restarting backend")
    assert_docker()
    step("Restarting backend ...")
    dc("restart", "backend")
    ok("Backend restarted  (logs: python dev.py logs)")

elif ACTION == "status":
    title("WorkPilot - status")
    rule()
    assert_docker()
    print(f"\n{WHITE}Docker services:{RESET}")
    dc("ps", "--format", "table {{.Service}}\t{{.Status}}\t{{.Ports}}")
    print(f"\n{WHITE}Frontend:{RESET}")
    print(f"  {CYAN}{frontend_status()}{RESET}")
    rule()

elif ACTION == "logs":
    assert_docker()
    if SERVICE == "frontend":
        if LOG_FILE.exists():
            run("tail", "-f", str(LOG_FILE))
        else:
            err(f"No frontend log file ({LOG_FILE})")
            sys.exit(1)
    else:
        print(f"{CYAN}Tailing {SERVICE}  (Ctrl+C to exit){RESET}")
        dc("logs", "-f", "--tail=100", SERVICE)

elif ACTION == "pull-models":
    title("WorkPilot - pulling Ollama models")
    rule()
    assert_docker()
    dc("up", "-d", "ollama")
    time.sleep(3)
    step("Pulling nomic-embed-text ...")
    dc("exec", "ollama", "ollama", "pull", "nomic-embed-text")
    step("Pulling qwen2.5:7b ...")
    dc("exec", "ollama", "ollama", "pull", "qwen2.5:7b")
    ok("Models ready")
    rule()

elif ACTION == "psql":
    assert_docker()
    step(r"Opening psql  (\q to exit) ...")
    dc("exec", "postgres", "psql", "-U", "workpilot", "-d", "workpilot")

else:
    print("Usage: python dev.py [start|stop|restart|status|logs|pull-models|psql]")
    sys.exit(1)

