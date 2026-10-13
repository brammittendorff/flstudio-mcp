"""Write a results table to the GitHub Actions job summary, when running there."""
from __future__ import annotations

import os
import platform

_ICON = {"passed": "✅", "failed": "❌", "skipped": "⏭️"}


def pytest_terminal_summary(terminalreporter):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    rows = []
    for outcome in ("failed", "passed", "skipped"):
        for rep in terminalreporter.stats.get(outcome, []):
            if rep.when == "call" or outcome == "skipped":
                rows.append("| %s | `%s` | %.1f s |" % (_ICON[outcome], rep.nodeid.split("::")[-1],
                                                        rep.duration))
    title = os.environ.get("FLMCP_SUMMARY_TITLE", "Tests")
    with open(path, "a", encoding="utf-8") as f:
        f.write("### %s (%s, Python %s)\n\n| | Test | Time |\n|---|---|---|\n%s\n\n"
                % (title, platform.system(), platform.python_version(), "\n".join(rows)))
