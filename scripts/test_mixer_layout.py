#!/usr/bin/env python3
"""Offline test: routing report + "own insert per channel" (fl_organize_mixer),
run end to end through the real MCP tools and controller handlers against a
fake FL mixer, including the undo. No FL needed.

    python scripts/test_mixer_layout.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fl_studio_mcp import safety  # noqa: E402
from fl_studio_mcp.music.mixer_layout import free_inserts, plan_layout  # noqa: E402

_P = _F = 0


def check(label, cond, detail=""):
    global _P, _F
    _P += 1 if cond else 0
    _F += 0 if cond else 1
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", label, ("  -- " + detail) if detail else ""))


class FakeFL:
    """A small project: 3 stems on the Master, a vocal on insert 1 sending to
    the Master and to bus 2 (which goes to the Master), inserts 3-6 empty."""
    def __init__(self, new_api=True):
        self.names = ["Master", "Vocal", "Vocal bus", "Insert 3", "Insert 4", "My FX", "Insert 6"]
        self.routes = {1: {0, 2}, 2: {0}, 3: {0}, 4: {0}, 5: {0}, 6: {0}}
        self.chan_names = ["Drums", "Bass", "Vocal", "Keys"]
        self.targets = [0, 0, 1, 0]
        self.selected, self.active = None, None
        self.new_api = new_api

    def modules(self):
        mixer, channels = types.ModuleType("mixer"), types.ModuleType("channels")
        mixer.trackCount = lambda: len(self.names)
        mixer.getTrackName = lambda i: self.names[i]
        mixer.setTrackName = lambda i, n: self.names.__setitem__(i, n)
        mixer.getRouteSendActive = lambda s, d: d in self.routes.get(s, set())
        mixer.getTrackPan = lambda i: 0.0
        mixer.isTrackMuted = mixer.isTrackSolo = lambda i: False
        mixer.getTrackColor = lambda i: 0
        mixer.getTrackVolume = lambda i: 0.8
        if self.new_api:
            mixer.linkChannelToTrack = lambda c, t: self.targets.__setitem__(c, t)
        else:
            mixer.setActiveTrack = lambda t: setattr(self, "active", t)
            mixer.linkTrackToChannel = lambda mode: self.targets.__setitem__(self.selected, self.active)
        channels.channelCount = lambda: len(self.chan_names)
        channels.getChannelName = lambda i: self.chan_names[i]
        channels.getTargetFxTrack = lambda i: self.targets[i]
        channels.selectOneChannel = lambda i: setattr(self, "selected", i)
        return {"mixer": mixer, "channels": channels}


def load_controller(fake):
    for name in ["device", "general", "midi", "patterns", "playlist", "plugins",
                 "transport", "ui", "arrangement", "utils"]:
        sys.modules[name] = types.ModuleType(name)
    sys.modules.update(fake.modules())
    path = ROOT / "fl_controller" / "FLStudioMCP" / "device_FLStudioMCP.py"
    spec = importlib.util.spec_from_file_location("device_FLStudioMCP_%d" % id(fake), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeBridge:
    def __init__(self, dev):
        self.dev = dev

    def call(self, command, params=None, timeout=None):
        return json.loads(json.dumps(self.dev._dispatch(command, params or {})))


def call_tool(server, name, args):
    res = asyncio.run(server.call_tool(name, args))
    data = getattr(res, "structured_content", None)
    if data is None:
        data = json.loads(res.content[0].text)
    return data.get("result", data) if isinstance(data, dict) and set(data) == {"result"} else data


def run(new_api):
    from fl_studio_mcp.server import build_server
    fake = FakeFL(new_api)
    bridge = FakeBridge(load_controller(fake))
    for name, mod in list(sys.modules.items()):              # every tool talks to the fake
        if name.startswith("fl_studio_mcp.tools.") and hasattr(mod, "get_bridge"):
            mod.get_bridge = lambda: bridge
    server = build_server()

    report = call_tool(server, "fl_routing_report", {})
    kinds = [f["type"] for f in report["findings"]]
    check("report: vocal heard twice", "double_path_to_master" in kinds, str(kinds))
    check("report: 3 channels on the Master", report["summary"]["channels_on_master"] == 3)

    plan = call_tool(server, "fl_organize_mixer", {})
    moves = [(m["name"], m["track"]) for m in plan["moves"]]
    check("plan only: nothing changed", not plan["applied"] and fake.targets == [0, 0, 1, 0])
    check("plan skips the named 'My FX' insert",
          moves == [("Drums", 3), ("Bass", 4), ("Keys", 6)], str(moves))

    done = call_tool(server, "fl_organize_mixer", {"apply": True})
    check("apply routes the channels (%s API)" % ("new" if new_api else "old"),
          done["ok"] and fake.targets == [3, 4, 1, 6], str(fake.targets))
    check("apply names the inserts", fake.names[3:7] == ["Drums", "Bass", "My FX", "Keys"],
          str(fake.names))

    call_tool(server, "fl_rollback_last_change", {})
    check("one undo restores routing and names",
          fake.targets == [0, 0, 1, 0] and fake.names[3:7] == ["Insert 3", "Insert 4", "My FX",
                                                              "Insert 6"],
          "%s %s" % (fake.targets, fake.names))


def main() -> int:
    routing = [{"i": 0, "name": "Master"}, {"i": 1, "name": "Insert 1", "routes_to": [{"dst": 0}]},
               {"i": 2, "name": "Insert 2", "routes_to": [{"dst": 0}]},
               {"i": 3, "name": "Reverb", "routes_to": [{"dst": 0}]}]
    chans = [{"channel": 0, "name": "Kick", "target_mixer_track": 0},
             {"channel": 1, "name": "Snare", "target_mixer_track": 2}]
    check("free inserts skip used and named ones", free_inserts(chans, routing) == [1])
    p = plan_layout(chans + [{"channel": 2, "name": "Hat", "target_mixer_track": 0}], routing)
    check("runs out of inserts gracefully", len(p["moves"]) == 1 and len(p["skipped"]) == 1, str(p))
    check("only= limits the plan", plan_layout(chans, routing, only={5})["moves"] == [])

    tmp = Path(tempfile.mkdtemp(prefix="flmcp_mix_"))            # not the user's undo log
    safety._DIR, safety._PATH = tmp, tmp / "changelog.jsonl"
    safety._log = safety.ChangeLog()
    run(new_api=True)
    run(new_api=False)

    print("\n%d passed, %d failed" % (_P, _F))
    return 1 if _F else 0


if __name__ == "__main__":
    sys.exit(main())
