#!/usr/bin/env python3
"""Offline test: start the real daemon and talk to it over TCP. Works without
FL or MIDI ports; then the daemon must report the problem, not crash.

    python scripts/test_daemon_tcp.py                      # daemon from src/
    python scripts/test_daemon_tcp.py <daemon command>     # an installed daemon
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = 9797                                       # not the default, so it can't clash

_P = _F = 0


def check(label, cond, detail=""):
    global _P, _F
    _P += 1 if cond else 0
    _F += 0 if cond else 1
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", label, ("  -- " + detail) if detail else ""))


def connect(timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            return socket.create_connection(("127.0.0.1", PORT), timeout=10)
        except OSError:
            time.sleep(0.2)
    return None


def main() -> int:
    env = dict(os.environ, FLSTUDIO_MCP_TCP_PORT=str(PORT),
               PYTHONPATH=str(ROOT / "src") + os.pathsep + os.environ.get("PYTHONPATH", ""))
    cmd = sys.argv[1:] or [sys.executable, "-c", "from fl_studio_mcp.daemon import main; main()"]
    print("daemon:", " ".join(cmd))
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        sock = connect()
        check("daemon listens on TCP", sock is not None)
        if sock is None:
            return 1
        f = sock.makefile("rwb")

        def ask(req):
            f.write((json.dumps(req) + "\n").encode())
            f.flush()
            return json.loads(f.readline())

        health = ask({"op": "health"})
        check("health answers with alive flag", "alive" in health, str(health)[:120])
        ping = ask({"op": "call", "cmd": "ping", "params": {}, "timeout": 2})
        check("ping answers ok or a known error",
              ping.get("ok") is True or ping.get("exc") in ("FLNotRunning", "FLPortMissing", "FLTimeout"),
              str(ping)[:120])
        bad = ask({"op": "nope"})
        check("unknown op is an error, not a crash", bad.get("ok") is False)
        check("daemon still running", proc.poll() is None)
        sock.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)

    print("\n%d passed, %d failed" % (_P, _F))
    return 1 if _F else 0


if __name__ == "__main__":
    sys.exit(main())
