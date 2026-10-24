"""The planner's browser flows (tests/browser): templates, four-eyes, packs, Claude drafts, roles,
reviewer notes, demo mode, the scenario, the audit log, lessons and the navigation (fd-core's shell:
queues, views, the search palette, keys and the drawer), in Chromium against the mock
of the platform's capabilities. Skipped without node and the pinned Playwright in
tests/browser/node_modules."""
from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
B = ROOT / "tests" / "browser"
pytestmark = pytest.mark.skipif(shutil.which("node") is None or not (B / "node_modules" / "playwright").exists(),
                                reason="needs node and Playwright in tests/browser (npm install there)")


@pytest.fixture(scope="module")
def served():
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_app.py")], check=True, capture_output=True)
    subprocess.run(["sh", str(B / "build.sh")], check=True, capture_output=True)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(B / "dev")],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    yield f"http://127.0.0.1:{port}"
    srv.terminate()


@pytest.mark.parametrize("flow", ["flow.mjs", "lessons_flow.mjs", "nav_flow.mjs", "clocks_flow.mjs", "monitor_flow.mjs"])
def test_browser_flow(served, flow, tmp_path):
    r = subprocess.run(["node", str(B / flow), served, str(tmp_path / "shot")], cwd=B, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, (r.stdout[-3000:], r.stderr[-3000:])
