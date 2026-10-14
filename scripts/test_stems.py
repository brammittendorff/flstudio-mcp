#!/usr/bin/env python3
"""Offline test: song to MIDI per instrument (music/stems.py). Drum sorting is
tested on synthetic hits; the full Demucs pipeline runs only when the
audio-stems extra is installed (first run downloads the ~80 MB model).

    python scripts/test_stems.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

from fl_studio_mcp.music import stems  # noqa: E402

SR = 44100
BPM = 120.0
_P = _F = 0


def check(label, cond, detail=""):
    global _P, _F
    _P += 1 if cond else 0
    _F += 0 if cond else 1
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", label, ("  -- " + detail) if detail else ""))


def hit(kind, rng):
    t = np.arange(int(0.2 * SR)) / SR
    if kind == "kick":                         # low, falling sine thump
        return np.sin(2 * np.pi * (50 + 80 * np.exp(-t * 30)) * t) * np.exp(-t * 12)
    noise = rng.standard_normal(len(t))
    if kind == "hihat":                        # short, bright noise
        noise = np.diff(np.diff(noise, prepend=0), prepend=0)
        return 0.3 * noise * np.exp(-t * 60)
    body = np.sin(2 * np.pi * 190 * t)         # snare: tone + broad noise
    return 0.5 * (0.5 * body + noise) * np.exp(-t * 25)


def drum_loop():
    """One bar of 8ths at 120 BPM: kick, hat, snare, hat, kick, hat, snare, hat."""
    rng = np.random.default_rng(0)
    pattern = ["kick", "hihat", "snare", "hihat"] * 2
    step = int(SR * 60 / BPM / 2)
    y = np.zeros(step * len(pattern) + SR)
    for i, kind in enumerate(pattern):
        h = hit(kind, rng)
        y[i * step:i * step + len(h)] += h
    return 0.8 * y / np.abs(y).max(), pattern


def main() -> int:
    d = Path(tempfile.mkdtemp(prefix="flmcp_stems_"))
    y, pattern = drum_loop()
    sf.write(str(d / "drums.wav"), y, SR)
    notes = stems.drum_notes(str(d / "drums.wav"), BPM, quantize=0.125)
    want = {"kick": stems.KICK, "snare": stems.SNARE, "hihat": stems.HIHAT}
    got = [n["pitch"] for n in sorted(notes, key=lambda n: n["time_bars"])]
    check("one note per drum hit", len(got) == len(pattern), "%d notes" % len(got))
    check("kick/snare/hi-hat sorted right", got == [want[k] for k in pattern],
          "got %s" % got)
    check("hits land on the 1/8 grid",
          [n["time_bars"] for n in sorted(notes, key=lambda n: n["time_bars"])]
          == [i * 0.125 for i in range(len(pattern))])

    if not stems.stems_available():
        print("  (Demucs not installed: full song-to-MIDI pipeline not run)")
    else:
        t = np.arange(4 * SR) / SR
        bass = 0.3 * np.sin(2 * np.pi * 55 * t)                     # A1
        song = np.tile(y[:SR], 4)[:len(t)] + bass
        sf.write(str(d / "song.wav"), np.vstack([song, song]).T * 0.7, SR)
        r = stems.split_to_midi(str(d / "song.wav"), str(d / "out"), bpm=BPM)
        check("Demucs wrote 4 stems", sorted(r["stems"]) == ["bass", "drums", "other", "vocals"])
        check(".mid written", Path(r["midi_file"]).is_file())
        import mido
        names = [tr.name for tr in mido.MidiFile(r["midi_file"]).tracks[1:]]
        check("one MIDI track per instrument",
              names == ["Drums", "Bass", "Chords (other)", "Vocal melody"], str(names))
        check("drums found in the song", r["tracks"]["drums"]["notes"] > 0)

    print("\n%d passed, %d failed" % (_P, _F))
    return 1 if _F else 0


if __name__ == "__main__":
    sys.exit(main())
