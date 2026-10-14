"""Song to MIDI per instrument: split with Demucs (drums, bass, other, vocals),
then transcribe each stem with the tool that fits it, into one multi-track .mid.

Heavy (torch); every import is lazy so the server starts without the extra.
"""
from __future__ import annotations

import contextlib
import os
import sys

# General MIDI drum notes
KICK, SNARE, HIHAT = 36, 38, 42
MODEL = "htdemucs"


def stems_available() -> bool:
    try:
        import demucs  # noqa: F401
        import torch  # noqa: F401
        return True
    except Exception:
        return False


def separate(path, out_dir):
    """Split an audio file into stems with Demucs. Returns ({stem: wav_path}, sr)."""
    import librosa
    import numpy as np
    import soundfile as sf
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    with contextlib.redirect_stdout(sys.stderr):           # keep the MCP channel clean
        model = get_model(MODEL)
    model.eval()
    y, sr = librosa.load(path, sr=model.samplerate, mono=False)
    y = np.atleast_2d(y)
    if y.shape[0] == 1:
        y = np.vstack([y, y])
    wav = torch.tensor(y[:2], dtype=torch.float32)
    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8
    with torch.no_grad(), contextlib.redirect_stdout(sys.stderr):
        out = apply_model(model, ((wav - mean) / std)[None], device="cpu", progress=False)[0]
    out = out * std + mean

    os.makedirs(out_dir, exist_ok=True)
    paths = {}
    for name, src in zip(model.sources, out):
        paths[name] = os.path.join(out_dir, "%s.wav" % name)
        sf.write(paths[name], src.numpy().T, sr)
    return paths, sr


def drum_notes(path, bpm, quantize=1 / 16.0):
    """Drum stem to kick/snare/hi-hat notes (bars), by onset and spectrum."""
    import librosa
    import numpy as np

    y, sr = librosa.load(path, sr=22050, mono=True)
    pad = int(0.05 * sr)                       # lets a hit at 0.0 s be detected
    y = np.concatenate([np.zeros(pad), y])
    env = librosa.onset.onset_strength(y=y, sr=sr)
    onsets = librosa.onset.onset_detect(onset_envelope=env, sr=sr, units="samples",
                                        backtrack=True)
    peak = float(env.max()) or 1.0
    barlen = 4.0 * 60.0 / bpm
    win = int(0.06 * sr)
    freqs = np.fft.rfftfreq(win, 1.0 / sr)
    notes, last_start, last_rms = [], None, 0.0
    for start in onsets:
        seg = y[start:start + win]
        if len(seg) < win:
            seg = np.pad(seg, (0, win - len(seg)))
        rms = float(np.sqrt(np.mean(seg ** 2)))
        # A much quieter onset right after a hit is its tail (e.g. a kick's pitch sweep).
        if last_start is not None and start - last_start < 0.15 * sr and rms < 0.35 * last_rms:
            continue
        last_start, last_rms = start, rms
        spec = np.abs(np.fft.rfft(seg * np.hanning(win))) ** 2
        total = float(spec.sum()) or 1.0
        low = float(spec[freqs < 150].sum()) / total       # kick: almost all sub/low
        body = float(spec[freqs < 1000].sum()) / total     # snare has a body, a hi-hat hasn't
        pitch = KICK if low > 0.45 else SNARE if body > 0.1 else HIHAT
        frame = int(librosa.samples_to_frames(start))
        t = max(0.0, (start - pad) / sr / barlen)
        if quantize:
            t = round(round(t / quantize) * quantize, 6)
        strength = float(env[min(frame, len(env) - 1)]) / peak
        notes.append({"pitch": pitch, "time_bars": t, "length_bars": quantize or 0.0625,
                      "velocity": round(min(1.0, 0.3 + 0.7 * strength), 3)})
    return notes


def _tempo(path):
    import librosa
    import numpy as np

    y, sr = librosa.load(path, sr=22050, mono=True, duration=120)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(np.atleast_1d(tempo).ravel()[0])
    return bpm / 2.0 if bpm > 180.0 else bpm


def split_to_midi(path, out_dir, bpm=None):
    """Song -> stems -> one multi-track .mid. Returns a summary dict."""
    from ..tools.audio import audio_extract_chords, audio_extract_melody, chords_available
    from .midi_export import write_midi

    stems, _sr = separate(path, out_dir)
    bpm = float(bpm) if bpm else _tempo(path)

    def to_spec(notes):
        return [{"pitch": n["pitch"], "start_bars": n["time_bars"],
                 "length_bars": n["length_bars"], "velocity": n["velocity"]} for n in notes]

    tracks, summary = [], {}
    drums = drum_notes(stems["drums"], bpm)
    tracks.append({"name": "Drums", "channel": 9, "notes": to_spec(drums)})
    summary["drums"] = {"notes": len(drums),
                        "kick": sum(n["pitch"] == KICK for n in drums),
                        "snare": sum(n["pitch"] == SNARE for n in drums),
                        "hihat": sum(n["pitch"] == HIHAT for n in drums)}

    if chords_available():
        bass = audio_extract_chords(stems["bass"], bpm, include_notes=True, max_notes=100000,
                                    min_freq=30.0, max_freq=400.0)
        tracks.append({"name": "Bass", "channel": 1, "notes": to_spec(bass["bridge_notes"])})
        summary["bass"] = {"notes": bass["note_count"]}
        other = audio_extract_chords(stems["other"], bpm, include_notes=True, max_notes=100000)
        tracks.append({"name": "Chords (other)", "channel": 2,
                       "notes": to_spec(other["bridge_notes"])})
        summary["other"] = {"notes": other["note_count"],
                            "progression": other["progression"][:64]}
    else:
        summary["bass"] = summary["other"] = {"skipped": "audio-chords extra not installed"}

    vocals = audio_extract_melody(stems["vocals"], bpm)
    tracks.append({"name": "Vocal melody", "channel": 3, "notes": to_spec(vocals["bridge_notes"])})
    summary["vocals"] = {"notes": vocals["kept_count"], "engine": vocals["engine"]}

    base = os.path.splitext(os.path.basename(path))[0]
    midi = os.path.join(out_dir, "%s_stems.mid" % base)
    write_midi(tracks, bpm, midi)
    return {"path": str(path), "bpm_used": round(bpm, 1), "stems": stems, "midi_file": midi,
            "tracks": summary,
            "quality": ("Drums, bass and vocals usually separate cleanly; 'other' (keys, "
                        "synths, guitar together) is the weakest stem. Drum hits are sorted "
                        "into kick/snare/hi-hat by spectrum only. Review before using.")}
