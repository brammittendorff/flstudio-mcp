#!/usr/bin/env python3
"""Offline test: loudness (BS.1770 / EBU R128) against the EBU Tech 3341
reference signals, gating, true peak and the per-platform report.

    python scripts/test_loudness.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

from fl_studio_mcp.music import loudness  # noqa: E402

SR = 48000
_P = _F = 0


def check(label, cond, detail=""):
    global _P, _F
    _P += 1 if cond else 0
    _F += 0 if cond else 1
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", label, ("  -- " + detail) if detail else ""))


def sine(db, secs, freq=1000.0, phase=0.0):
    t = np.arange(int(SR * secs)) / SR
    return 10 ** (db / 20) * np.sin(2 * np.pi * freq * t + phase)


def main() -> int:
    # EBU Tech 3341 case 1: stereo 1 kHz sine at -23 dBFS per channel = -23.0 LUFS (+-0.1).
    s = sine(-23, 20)
    r = loudness.measure(np.vstack([s, s]), SR)
    check("EBU 1: -23 dBFS stereo sine reads -23.0 LUFS", abs(r["integrated_lufs"] + 23) <= 0.1,
          str(r["integrated_lufs"]))
    # Case 2: same at -33 dBFS = -33.0 LUFS.
    s = sine(-33, 20)
    r = loudness.measure(np.vstack([s, s]), SR)
    check("EBU 2: -33 dBFS stereo sine reads -33.0 LUFS", abs(r["integrated_lufs"] + 33) <= 0.1,
          str(r["integrated_lufs"]))
    # Case 3: -36 / -23 / -36 dBFS for 10 / 60 / 10 s = -23.0 LUFS (relative gate).
    s = np.concatenate([sine(-36, 10), sine(-23, 60), sine(-36, 10)])
    r = loudness.measure(np.vstack([s, s]), SR)
    check("EBU 3: relative gate drops the quiet parts (-23.0 LUFS)",
          abs(r["integrated_lufs"] + 23) <= 0.1, str(r["integrated_lufs"]))
    # Case 4: -72 / -36 / -23 / -36 / -72 dBFS for 10/10/60/10/10 s = -23.0 LUFS.
    s = np.concatenate([sine(-72, 10), sine(-36, 10), sine(-23, 60), sine(-36, 10), sine(-72, 10)])
    r = loudness.measure(np.vstack([s, s]), SR)
    check("EBU 4: absolute and relative gate together (-23.0 LUFS)",
          abs(r["integrated_lufs"] + 23) <= 0.1, str(r["integrated_lufs"]))
    check("silence has no loudness", loudness.measure(np.zeros((2, SR * 5)), SR)
          ["integrated_lufs"] is None)

    # Inter-sample peak: a sine at SR/4 sampled at 45 degrees peaks between samples.
    s = 0.9 * np.sin(2 * np.pi * (SR / 4) * np.arange(SR) / SR + np.pi / 4)
    r = loudness.measure(s, SR)
    check("true peak is above the sample peak for inter-sample peaks",
          r["true_peak_dbtp"] > r["sample_peak_dbfs"] + 2.5,
          "sample %s dBFS, true %s dBTP" % (r["sample_peak_dbfs"], r["true_peak_dbtp"]))

    loud = loudness.platform_report({"integrated_lufs": -8.0, "true_peak_dbtp": 0.3})
    spotify = next(p for p in loud["platforms"] if p["platform"] == "Spotify")
    check("loud master: Spotify turns it down 6 dB", spotify["gain_change_db"] == -6.0)
    check("loud master: true peak and loudness advice given", len(loud["advice"]) == 2,
          str(loud["advice"]))
    quiet = loudness.platform_report({"integrated_lufs": -20.0, "true_peak_dbtp": -4.0})
    yt = next(p for p in quiet["platforms"] if p["platform"] == "YouTube")
    sp = next(p for p in quiet["platforms"] if p["platform"] == "Spotify")
    check("quiet master: YouTube does not turn it up", yt["gain_change_db"] == 0.0)
    check("quiet master: Spotify turns up only to the -1 dBTP headroom", sp["gain_change_db"] == 3.0,
          str(sp))

    path = Path(tempfile.mkdtemp(prefix="flmcp_lufs_")) / "mix.wav"
    s = sine(-23, 10)
    sf.write(str(path), np.vstack([s, s]).T, SR)
    r = loudness.measure_file(str(path))
    check("measure_file reads a stereo WAV", r["channels"] == 2 and
          abs(r["integrated_lufs"] + 23) <= 0.1 and r["platforms"], str(r["integrated_lufs"]))

    print("\n%d passed, %d failed" % (_P, _F))
    return 1 if _F else 0


if __name__ == "__main__":
    sys.exit(main())
