"""Plan giving each channel that plays straight into the Master its own mixer
insert, named after the channel. Pure: only plans, the tool applies it.
"""
from __future__ import annotations

import re

MASTER = 0
_DEFAULT_NAME = re.compile(r"^\s*(insert\s*\d+)?\s*$", re.IGNORECASE)


def free_inserts(channels, routing):
    """Inserts that are safe to take: default name, no channel on them,
    nothing routed into them, not the Master (in mixer order)."""
    used = {c.get("target_mixer_track") for c in channels}
    fed = {d["dst"] for r in routing for d in r.get("routes_to", []) if d["dst"] != r["i"]}
    return [r["i"] for r in routing
            if r["i"] != MASTER and r["i"] not in used and r["i"] not in fed
            and _DEFAULT_NAME.match(r.get("name") or "")]


def plan_layout(channels, routing, only=None):
    """channels: [{channel, name, target_mixer_track}], routing: [{i, name,
    routes_to}]. only: optional channel indexes to limit the plan to.
    Returns {moves: [{channel, name, track, track_name_before}], skipped}."""
    names = {r["i"]: r.get("name") or "" for r in routing}
    todo = [c for c in channels if c.get("target_mixer_track") == MASTER
            and (only is None or c["channel"] in only)]
    free = free_inserts(channels, routing)
    moves, skipped = [], []
    for c in todo:
        if not free:
            skipped.append({"channel": c["channel"], "name": c.get("name"),
                            "why": "no free mixer insert left"})
            continue
        track = free.pop(0)
        moves.append({"channel": c["channel"], "name": c.get("name"), "track": track,
                      "track_name_before": names.get(track, "")})
    return {"moves": moves, "skipped": skipped}
