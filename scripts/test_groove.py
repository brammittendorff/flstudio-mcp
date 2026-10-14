#!/usr/bin/env python3
"""Offline test: swing/humanize (pyscript_gen.groove), and the generated FL
script run against a fake flpianoroll, so new and existing notes match.

    python scripts/test_groove.py
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fl_studio_mcp.pyscript_gen import groove, render_groove_script  # noqa: E402

PPQ = 96
_P = _F = 0


def check(label, cond, detail=""):
    global _P, _F
    _P += 1 if cond else 0
    _F += 0 if cond else 1
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", label, ("  -- " + detail) if detail else ""))


def sixteenths(count, vel=0.8):
    return [(60, i * 0.0625, 0.0625, vel) for i in range(count)]


def run_in_fake_fl(script, notes):
    """Execute a generated groove script against a fake piano roll; return notes."""
    class Note:
        number = time = length = 0
        velocity = 0.0

    class Score:
        def __init__(self):
            self.notes = []
            for pitch, t, length, vel in notes:
                n = Note()
                n.number, n.time, n.length, n.velocity = pitch, int(t * PPQ * 4), length, vel
                self.notes.append(n)
            self.PPQ = PPQ

        @property
        def noteCount(self):
            return len(self.notes)

        def getNote(self, i):
            return self.notes[i]

        def clearNotes(self, *_):
            self.notes = []

        def addNote(self, n):
            self.notes.append(n)

    fake = types.ModuleType("flpianoroll")
    fake.Note, fake.score = Note, Score()
    sys.modules["flpianoroll"] = fake
    exec(compile(script, "MCP_Apply.pyscript", "exec"), {})
    return [(n.number, n.time / (PPQ * 4), n.velocity) for n in fake.score.notes]


def main() -> int:
    plain = sixteenths(4)
    check("no swing, no humanize: unchanged", groove(plain) == plain)

    swung = groove(plain, swing=1.0)
    check("on-beat notes stay", swung[0][1] == 0.0 and swung[2][1] == 0.125)
    check("swing 1.0 moves off-beats to triplet feel (1/12 bar)",
          abs(swung[1][1] - 1 / 12) < 1e-9 and abs(swung[3][1] - 0.125 - 1 / 12) < 1e-9,
          "%.4f, %.4f" % (swung[1][1], swung[3][1]))
    half = groove(plain, swing=0.5)
    check("swing 0.5 moves half as far", abs(half[1][1] - (0.0625 + 1 / 96)) < 1e-9,
          "%.5f" % half[1][1])
    near = groove([(60, 0.07, 0.1, 0.8)], swing=1.0)
    check("slightly late off-beat still swings", abs(near[0][1] - (0.07 + 1 / 48)) < 1e-9)
    off_grid = groove([(60, 0.09, 0.1, 0.8)], swing=1.0)
    check("notes far off the grid are not swung", off_grid[0][1] == 0.09)

    human = groove(sixteenths(16), timing=1 / 64, velocity=0.25, seed=3)
    check("humanize changes timing", any(abs(h[1] - p[1]) > 1e-6 for h, p in zip(human, sixteenths(16))))
    check("timing stays within +-1/64 bar",
          all(abs(h[1] - p[1]) <= 1 / 64 + 1e-9 for h, p in zip(human, sixteenths(16))))
    check("velocity stays within 0.05..1", all(0.05 <= h[3] <= 1.0 for h in human))
    check("same seed gives the same result", human == groove(sixteenths(16), timing=1 / 64,
                                                              velocity=0.25, seed=3))
    check("other seed gives another result", human != groove(sixteenths(16), timing=1 / 64,
                                                              velocity=0.25, seed=4))
    check("first note never moves before 0", groove([(60, 0.0, 0.1, 0.8)], timing=0.5)[0][1] >= 0)

    args = {"swing": 0.7, "grid": 0.0625, "timing": 1 / 128, "velocity": 0.1, "seed": 5}
    script = render_groove_script(**args)
    check("FL script is plain ASCII", script.isascii())
    in_fl = run_in_fake_fl(script, sixteenths(8))
    server = [(p, t, v) for p, t, _, v in groove(sixteenths(8), **args)]
    check("FL script grooves existing notes like the server does new ones",
          all(a[0] == b[0] and abs(a[1] - b[1]) < 1 / (PPQ * 4) and abs(a[2] - b[2]) < 1e-9
              for a, b in zip(in_fl, server)) and len(in_fl) == len(server))

    print("\n%d passed, %d failed" % (_P, _F))
    return 1 if _F else 0


if __name__ == "__main__":
    sys.exit(main())
