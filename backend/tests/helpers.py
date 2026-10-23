import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent


@contextmanager
def running_mcp_server(db: Path, seed: bool = True):
    """Start the real HouseLedger MCP server process on a free port.

    With seed=True the database gets the sample expenses; otherwise only the predefined
    members. Yields the MCP URL (http://127.0.0.1:<port>/mcp) and stops the server afterwards.
    """
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, "-m", "houseledger.mcp_server", "--port", str(port), "--db", str(db),
         *(["--seed"] if seed else [])],
        cwd=BACKEND, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/health", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("MCP server did not start")
        yield base + "/mcp"
    finally:
        proc.terminate()
        proc.wait(timeout=10)
