#!/usr/bin/env python3
"""CI helper: print the platform, Python and installed package versions, and
add them to the GitHub job summary.

    python scripts/ci_packages.py
"""
from __future__ import annotations

import os
import platform
import sys
from importlib import metadata

PACKAGES = ["fl-studio-mcp", "fastmcp", "mcp", "pydantic", "mido", "python-rtmidi",
            "pyautogui", "librosa", "soundfile", "numpy", "scipy", "torch", "torchcrepe",
            "onnxruntime", "basic-pitch", "pretty-midi", "resampy", "scikit-learn", "setuptools"]


def main() -> int:
    rows = []
    for name in PACKAGES:
        try:
            rows.append((name, metadata.version(name)))
        except metadata.PackageNotFoundError:
            rows.append((name, "not installed"))
    head = "%s, Python %s (%s)" % (platform.platform(), platform.python_version(), platform.machine())
    print(head)
    for name, ver in rows:
        print("  %-16s %s" % (name, ver))
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("### Installed packages\n\n%s\n\n| Package | Version |\n|---|---|\n" % head)
            f.write("\n".join("| %s | %s |" % r for r in rows) + "\n\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
