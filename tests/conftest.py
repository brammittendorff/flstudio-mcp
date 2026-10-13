"""On GitHub Actions: annotate each failed test and write a results table to
the job summary."""
from __future__ import annotations

import os
import platform

_ICON = {"passed": "✅", "failed": "❌", "skipped": "⏭️"}


def _reason(rep):
    crash = getattr(rep.longrepr, "reprcrash", None)
    text = crash.message if crash else str(rep.longrepr)
    return text.splitlines()[0][:300] if text else "failed"


def pytest_runtest_logreport(report):
    if report.failed and os.environ.get("GITHUB_ACTIONS"):
        name = report.nodeid.split("::")[-1]
        print("\n::error title=%s failed::%s" % (name, _reason(report)), flush=True)


def pytest_terminal_summary(terminalreporter):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    rows = []
    for outcome in ("failed", "passed", "skipped"):
        for rep in terminalreporter.stats.get(outcome, []):
            if rep.when == "call" or outcome == "skipped":
                note = _reason(rep) if outcome != "passed" else ""
                rows.append("| %s | `%s` | %.1f s | %s |" % (
                    _ICON[outcome], rep.nodeid.split("::")[-1], rep.duration,
                    note.replace("|", "\\|")))
    title = os.environ.get("FLMCP_SUMMARY_TITLE", "Tests")
    with open(path, "a", encoding="utf-8") as f:
        f.write("### %s (%s, Python %s)\n\n| | Test | Time | Reason |\n|---|---|---|---|\n%s\n\n"
                % (title, platform.system(), platform.python_version(), "\n".join(rows)))
