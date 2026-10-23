#!/usr/bin/env python3
"""Start FairShare: the MCP server, the simulated Alexa+ orchestrator, and the screen.

Usage (from the project root, on Windows, macOS or Linux):

    python run.py                 # start everything and open the browser
    python run.py --seed          # also add seeded, fictional sample expenses
    python run.py --reset         # wipe the ledger first (members only, zero balances)
    python run.py --reset --seed  # wipe, then add the sample expenses
    python run.py --no-browser    # don't open a browser window
    python run.py --build         # force a rebuild of the screen

Needs uv (https://docs.astral.sh/uv/) and Node.js with npm. Uses only the Python standard
library, so any Python 3.9+ can run it. Press Ctrl+C to stop everything.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
SIMULATOR = ROOT / "simulator"
IS_WINDOWS = os.name == "nt"
VENV_PYTHON = BACKEND / ".venv" / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the FairShare demo.")
    parser.add_argument("--seed", action="store_true", help="add seeded, fictional sample expenses")
    parser.add_argument("--reset", action="store_true", help="wipe the ledger before starting")
    parser.add_argument("--build", action="store_true", help="force a rebuild of the screen")
    parser.add_argument("--no-browser", action="store_true", help="don't open the browser")
    parser.add_argument("--mcp-port", type=int, default=8010, help="MCP server port (default 8010)")
    parser.add_argument("--port", type=int, default=8001, help="orchestrator and screen port (default 8001)")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # ₹ in logs on Windows consoles

    # Stop the servers on Ctrl+C, and also when this script is terminated or sent Ctrl+Break.
    signal.signal(signal.SIGTERM, _interrupt)
    if IS_WINDOWS:
        signal.signal(signal.SIGBREAK, _interrupt)

    uv = require("uv", "Install uv: https://docs.astral.sh/uv/getting-started/installation/")
    npm = require("npm", "Install Node.js 20.19+ or 22.12+ (includes npm): https://nodejs.org/")
    for port in (args.mcp_port, args.port):
        if port_in_use(port):
            return fail(f"Port {port} is already in use. Stop whatever is using it, or pass "
                        f"--mcp-port / --port to choose another.")

    step("Installing backend packages (uv sync)")
    run([uv, "sync"], cwd=BACKEND)

    if args.reset or args.seed:
        seed_args = ["-m", "houseledger.seed"]
        if args.reset:
            seed_args.append("--reset")
        if not args.seed:
            seed_args.append("--empty")
        step("Resetting the ledger" if args.reset else "Adding sample expenses")
        run([str(VENV_PYTHON), *seed_args], cwd=BACKEND)

    build_screen(npm, force=args.build)

    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1",
           "MCP_URL": f"http://127.0.0.1:{args.mcp_port}/mcp"}
    services: list[Service] = []
    try:
        step(f"Starting the MCP server on port {args.mcp_port}")
        mcp = Service("mcp", [str(VENV_PYTHON), "-m", "houseledger.mcp_server", "--port", str(args.mcp_port)],
                      BACKEND, env)
        services.append(mcp)
        mcp.wait_until_ready(f"http://127.0.0.1:{args.mcp_port}/health")

        step(f"Starting the orchestrator on port {args.port}")
        orchestrator = Service("alexa", [str(VENV_PYTHON), "-m", "orchestrator.app", "--port", str(args.port)],
                               BACKEND, env)
        services.append(orchestrator)
        orchestrator.wait_until_ready(f"http://127.0.0.1:{args.port}/api/config")

        url = f"http://127.0.0.1:{args.port}"
        print(f"\n  FairShare is running:\n"
              f"    Simulator (UI):   {url}\n"
              f"    MCP endpoint:     http://127.0.0.1:{args.mcp_port}/mcp\n"
              f"  Press Ctrl+C to stop.\n", flush=True)
        if not args.no_browser:
            open_in_new_window(url)

        while all(s.alive() for s in services):
            time.sleep(0.5)
        crashed = next(s for s in services if not s.alive())
        return fail(f"The {crashed.name} process stopped unexpectedly (exit code {crashed.proc.returncode}).")
    except StartupError as err:
        return fail(str(err))
    except KeyboardInterrupt:
        print("\nStopping…", flush=True)
        return 0
    finally:
        for service in reversed(services):
            service.stop()


# --------------------------------------------------------------------------- helpers


class StartupError(Exception):
    pass


def _interrupt(*_) -> None:
    raise KeyboardInterrupt


class Service:
    """A child process whose output is printed with a [name] prefix."""

    def __init__(self, name: str, command: list[str], cwd: Path, env: dict[str, str]):
        self.name = name
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0
        self.proc = subprocess.Popen(
            command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=flags, start_new_session=not IS_WINDOWS,
        )
        threading.Thread(target=self._echo, daemon=True).start()

    def _echo(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            print(f"[{self.name}] {line.rstrip()}", flush=True)

    def alive(self) -> bool:
        return self.proc.poll() is None

    def wait_until_ready(self, url: str, timeout: float = 60) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.alive():
                raise StartupError(f"The {self.name} process exited during startup (see the [{self.name}] log above).")
            try:
                with urllib.request.urlopen(url, timeout=2):
                    return
            except OSError:
                time.sleep(0.3)
        raise StartupError(f"The {self.name} process didn't become ready at {url} within {timeout:.0f}s.")

    def stop(self) -> None:
        if not self.alive():
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()


def build_screen(npm: str, force: bool) -> None:
    """Install and build the simulator only when something changed."""
    lock = SIMULATOR / "package-lock.json"
    installed_marker = SIMULATOR / "node_modules" / ".package-lock.json"
    if not installed_marker.exists() or newer(lock, installed_marker):
        step("Installing screen packages (npm install)")
        run([npm, "install"], cwd=SIMULATOR)

    built = SIMULATOR / "dist" / "index.html"
    sources = [SIMULATOR / "index.html", SIMULATOR / "vite.config.ts", lock,
               *(p for p in (SIMULATOR / "src").rglob("*") if p.is_file()),
               *(p for p in (SIMULATOR / "public").rglob("*") if p.is_file())]
    if force or not built.exists() or any(newer(src, built) for src in sources):
        step("Building the screen (npm run build)")
        run([npm, "run", "build"], cwd=SIMULATOR)
    else:
        step("Screen is up to date")


def open_in_new_window(url: str) -> None:
    """Open the UI in a new browser window.

    Prefers Chrome or Edge (the browsers where the simulator's microphone works), launched with
    --new-window. Otherwise asks the default browser for a new window, which some browsers
    open as a tab instead.
    """
    browser = find_chromium_browser()
    if browser:
        subprocess.Popen([browser, "--new-window", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=not IS_WINDOWS)
    else:
        webbrowser.open_new(url)


def find_chromium_browser() -> str | None:
    if sys.platform == "darwin":
        candidates = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                      "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                      "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    elif IS_WINDOWS:
        roots = [os.environ.get(v) for v in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
        candidates = [str(Path(root) / rel) for root in roots if root
                      for rel in ("Google/Chrome/Application/chrome.exe", "Microsoft/Edge/Application/msedge.exe")]
    else:
        candidates = [shutil.which(name) or "" for name in
                      ("google-chrome", "google-chrome-stable", "microsoft-edge", "chromium", "chromium-browser")]
    return next((c for c in candidates if c and Path(c).is_file()), None)


def newer(a: Path, b: Path) -> bool:
    return a.exists() and b.exists() and a.stat().st_mtime > b.stat().st_mtime


def port_in_use(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def require(tool: str, hint: str) -> str:
    path = shutil.which(tool)  # finds npm.cmd / uv.exe on Windows too
    if path is None:
        raise SystemExit(f"Error: '{tool}' was not found on PATH. {hint}")
    return path


def run(command: list[str], cwd: Path) -> None:
    result = subprocess.run(command, cwd=cwd, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if result.returncode != 0:
        shown = " ".join([Path(command[0]).stem, *command[1:]])
        raise SystemExit(f"Error: '{shown}' failed with exit code {result.returncode}.")


def step(message: str) -> None:
    print(f"==> {message}", flush=True)


def fail(message: str) -> int:
    print(f"Error: {message}", file=sys.stderr, flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
