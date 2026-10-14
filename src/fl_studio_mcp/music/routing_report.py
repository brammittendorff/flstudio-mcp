"""What feeds what in the mixer, and common routing mistakes. Pure: works on
the controller's channel routing summary and per-track routing lists.
"""
from __future__ import annotations

MASTER = 0


def _reaches_master(track, routes, seen=None):
    """True if audio from ``track`` arrives at the Master by any path."""
    if track == MASTER:
        return True
    seen = seen or set()
    if track in seen:
        return False
    seen.add(track)
    return any(_reaches_master(d, routes, seen) for d in routes.get(track, []))


def routing_report(channels, routing):
    """channels: [{channel, name, target_mixer_track}], routing: [{i, name,
    routes_to: [{dst}]}]. Returns {feeds, findings, summary}."""
    names = {r["i"]: r.get("name") or "Insert %d" % r["i"] for r in routing}
    routes = {r["i"]: [d["dst"] for d in r.get("routes_to", [])] for r in routing}
    by_track = {}
    for c in channels:
        t = c.get("target_mixer_track")
        if isinstance(t, int):
            by_track.setdefault(t, []).append(c)

    feeds = []
    for r in routing:
        i = r["i"]
        sources = [{"channel": c["channel"], "name": c.get("name")} for c in by_track.get(i, [])]
        sends_in = [s for s, dsts in routes.items() if i in dsts and s != i]
        if i == MASTER or sources or sends_in:
            feeds.append({"track": i, "name": names.get(i), "channels": sources,
                          "from_tracks": [{"track": s, "name": names.get(s)} for s in sends_in],
                          "to_tracks": [{"track": d, "name": names.get(d)}
                                        for d in routes.get(i, [])]})

    findings = []
    direct = [c for c in by_track.get(MASTER, [])]
    if direct:
        findings.append({
            "type": "channel_on_master", "severity": "suggestion",
            "channels": [{"channel": c["channel"], "name": c.get("name")} for c in direct],
            "why": "These channels go straight to the Master, so they can't get their own "
                   "EQ, compression or level. Give each its own mixer insert."})
    for track, chans in sorted(by_track.items()):
        if track != MASTER and len(chans) > 1:
            findings.append({
                "type": "shared_insert", "severity": "info", "track": track,
                "name": names.get(track),
                "channels": [{"channel": c["channel"], "name": c.get("name")} for c in chans],
                "why": "Several channels share this insert: fine for a bus, but they can't "
                       "be processed separately."})
    for i, dsts in sorted(routes.items()):
        if i == MASTER:
            continue
        has_input = bool(by_track.get(i)) or any(i in d for s, d in routes.items() if s != i)
        if has_input and not _reaches_master(i, routes):
            findings.append({
                "type": "dead_end", "severity": "problem", "track": i, "name": names.get(i),
                "why": "This track receives audio but nothing reaches the Master from it, "
                       "so it is silent in the mix."})
        if MASTER in dsts:
            via = [d for d in dsts if d != MASTER and _reaches_master(d, routes, {i})]
            if via:
                findings.append({
                    "type": "double_path_to_master", "severity": "problem", "track": i,
                    "name": names.get(i),
                    "also_via": [{"track": d, "name": names.get(d)} for d in via],
                    "why": "This track goes to the Master directly AND through another "
                           "track, so it is heard twice (louder, possible phasing). Turn "
                           "off one of the two paths, or use the other as a send."})

    order = {"problem": 0, "suggestion": 1, "info": 2}
    findings.sort(key=lambda f: order[f["severity"]])
    return {"feeds": feeds, "findings": findings,
            "summary": {"problems": sum(f["severity"] == "problem" for f in findings),
                        "suggestions": sum(f["severity"] == "suggestion" for f in findings),
                        "channels_on_master": len(direct)}}
