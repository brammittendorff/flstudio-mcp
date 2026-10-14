#!/usr/bin/env python3
"""Offline test: routing report (what feeds what, routing mistakes).

    python scripts/test_routing_report.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fl_studio_mcp.music.routing_report import routing_report  # noqa: E402

_P = _F = 0


def check(label, cond, detail=""):
    global _P, _F
    _P += 1 if cond else 0
    _F += 0 if cond else 1
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", label, ("  -- " + detail) if detail else ""))


def route(i, name, *dsts):
    return {"i": i, "name": name, "routes_to": [{"dst": d} for d in dsts]}


def chan(i, name, track):
    return {"channel": i, "name": name, "target_mixer_track": track}


def kinds(report):
    return [f["type"] for f in report["findings"]]


def main() -> int:
    clean = routing_report(
        [chan(0, "Kick", 1), chan(1, "Snare", 2)],
        [route(0, "Master"), route(1, "Kick", 0), route(2, "Snare", 0)])
    check("clean project has no findings", clean["findings"] == [], str(kinds(clean)))
    master = next(f for f in clean["feeds"] if f["track"] == 0)
    check("Master is fed by both tracks",
          sorted(t["track"] for t in master["from_tracks"]) == [1, 2])

    # Like the stems project: stems straight to the Master.
    stems = routing_report(
        [chan(0, "Drums", 0), chan(1, "Bass", 0), chan(2, "Vocals", 3)],
        [route(0, "Master"), route(3, "Vocals", 0)])
    f = stems["findings"][0]
    check("channels on the Master are flagged",
          f["type"] == "channel_on_master" and [c["name"] for c in f["channels"]] == ["Drums", "Bass"])

    # Like Lead Vocals #2: to the Master and to Insert 10, which also goes to the Master.
    double = routing_report(
        [chan(0, "Lead", 5)],
        [route(0, "Master"), route(5, "Lead", 0, 10), route(10, "Vocal bus", 0)])
    check("double path to the Master is a problem", kinds(double) == ["double_path_to_master"])
    check("names the other path", double["findings"][0]["also_via"][0]["track"] == 10)

    # A send to a reverb that does NOT go to the Master is not a double path.
    send = routing_report(
        [chan(0, "Lead", 5)],
        [route(0, "Master"), route(5, "Lead", 0, 11), route(11, "Dead reverb")])
    check("send to a track that never reaches the Master is no double path",
          "double_path_to_master" not in kinds(send))

    dead = routing_report([chan(0, "Pad", 7)], [route(0, "Master"), route(7, "Pad")])
    check("track that routes nowhere is a dead end", kinds(dead) == ["dead_end"])
    chain = routing_report([chan(0, "Pad", 7)],
                           [route(0, "Master"), route(7, "Pad", 8), route(8, "Bus")])
    check("dead end found through a chain", kinds(chain) == ["dead_end", "dead_end"])
    unused = routing_report([], [route(0, "Master"), route(9, "Unused")])
    check("unused track without input is not a dead end", unused["findings"] == [])

    shared = routing_report([chan(0, "Hat", 4), chan(1, "Ride", 4)],
                            [route(0, "Master"), route(4, "Cymbals", 0)])
    check("shared insert is only info", kinds(shared) == ["shared_insert"] and
          shared["findings"][0]["severity"] == "info")

    loop = routing_report([chan(0, "A", 1)], [route(0, "Master"), route(1, "A", 2), route(2, "B", 1)])
    check("routing loop does not hang and is a dead end", "dead_end" in kinds(loop))
    check("problems sorted first", kinds(routing_report(
        [chan(0, "Drums", 0), chan(1, "Pad", 7)], [route(0, "Master"), route(7, "Pad")]))[0]
        == "dead_end")

    print("\n%d passed, %d failed" % (_P, _F))
    return 1 if _F else 0


if __name__ == "__main__":
    sys.exit(main())
