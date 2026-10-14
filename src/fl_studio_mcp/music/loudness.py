"""Loudness per ITU-R BS.1770-4 / EBU R128: integrated LUFS, true peak, and
what each streaming service would do with the track. Pure numpy/scipy.
"""
from __future__ import annotations

import math

# (name, integrated LUFS target, turns quiet tracks up too)
PLATFORMS = [
    ("Spotify", -14.0, True),
    ("YouTube", -14.0, False),
    ("Apple Music", -16.0, True),
    ("Amazon Music", -14.0, True),
    ("Tidal", -14.0, False),
    ("Deezer", -15.0, False),
]
TRUE_PEAK_LIMIT = -1.0          # dBTP; above this, lossy encoding can clip


def _k_weighting(sr):
    """BS.1770 pre-filter (high shelf) and RLB high-pass as two biquads."""
    f0, gain_db, q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    k = math.tan(math.pi * f0 / sr)
    vh = 10 ** (gain_db / 20)
    vb = vh ** 0.4996667741545416
    a0 = 1 + k / q + k * k
    shelf = ([(vh + vb * k / q + k * k) / a0, 2 * (k * k - vh) / a0, (vh - vb * k / q + k * k) / a0],
             [1.0, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0])
    f0, q = 38.13547087602444, 0.5003270373238773
    k = math.tan(math.pi * f0 / sr)
    a0 = 1 + k / q + k * k
    highpass = ([1.0, -2.0, 1.0], [1.0, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0])
    return shelf, highpass


def _block_loudness(blocks):
    return -0.691 + 10 * math.log10(blocks) if blocks > 0 else -math.inf


def measure(samples, sr):
    """samples: array (n,) or (channels, n), float -1..1. Returns a dict."""
    import numpy as np
    from scipy.signal import lfilter, resample_poly

    x = np.atleast_2d(np.asarray(samples, dtype=float))
    if x.shape[0] > x.shape[1]:
        x = x.T
    shelf, highpass = _k_weighting(sr)
    weighted = lfilter(*highpass, lfilter(*shelf, x, axis=1), axis=1)

    size, hop = int(round(0.4 * sr)), int(round(0.1 * sr))
    starts = range(0, max(weighted.shape[1] - size, 0) + 1, hop)
    power = [float(np.sum(np.mean(weighted[:, s:s + size] ** 2, axis=1))) for s in starts]
    gated = [p for p in power if _block_loudness(p) > -70.0]               # absolute gate
    integrated = -math.inf
    if gated:
        relative = _block_loudness(sum(gated) / len(gated)) - 10.0         # relative gate
        kept = [p for p in gated if _block_loudness(p) > relative]
        integrated = _block_loudness(sum(kept) / len(kept))

    short = int(round(3.0 * sr))
    short_term = [_block_loudness(float(np.sum(np.mean(weighted[:, s:s + short] ** 2, axis=1))))
                  for s in range(0, max(weighted.shape[1] - short, 0) + 1, hop)]

    peak = float(np.max(np.abs(x))) if x.size else 0.0
    true_peak = float(np.max(np.abs(resample_poly(x, 4, 1, axis=1)))) if x.size else 0.0

    def db(v):
        return round(20 * math.log10(v), 2) if v > 0 else None

    return {"integrated_lufs": round(integrated, 2) if integrated > -math.inf else None,
            "short_term_max_lufs": round(max(short_term), 2) if short_term and
            max(short_term) > -math.inf else None,
            "sample_peak_dbfs": db(peak), "true_peak_dbtp": db(max(true_peak, peak)),
            "duration_sec": round(x.shape[1] / sr, 2), "channels": int(x.shape[0])}


def platform_report(result):
    """What each service would do with a track of this loudness."""
    lufs, tp = result.get("integrated_lufs"), result.get("true_peak_dbtp")
    rows = []
    for name, target, boosts in PLATFORMS:
        if lufs is None:
            continue
        change = round(target - lufs, 1)
        if change > 0 and not boosts:
            change, note = 0.0, "plays as is (quieter than the target; not turned up)"
        elif change > 0:
            # Turning up is limited by headroom: the true peak can't pass -1 dBTP.
            room = round(TRUE_PEAK_LIMIT - tp, 1) if tp is not None else change
            change = min(change, max(room, 0.0))
            note = "turned up %.1f dB" % change
        elif change < 0:
            note = "turned down %.1f dB" % -change
        else:
            note = "plays as is"
        rows.append({"platform": name, "target_lufs": target, "gain_change_db": change,
                     "note": note})
    advice = []
    if tp is not None and tp > TRUE_PEAK_LIMIT:
        advice.append("True peak %.1f dBTP is above %.0f dBTP: lossy encoding (MP3/AAC/Opus) "
                      "can clip. Lower the limiter ceiling to -1 dBTP." % (tp, TRUE_PEAK_LIMIT))
    if lufs is not None and lufs > -9:
        advice.append("Very loud master (%.1f LUFS): most services will turn it down 5 dB or "
                      "more, so the extra loudness only costs dynamics." % lufs)
    if lufs is not None and lufs < -18:
        advice.append("Quiet master (%.1f LUFS): services that don't turn tracks up will play "
                      "it quieter than others." % lufs)
    return {"platforms": rows, "advice": advice}


def measure_file(path):
    """Load an audio file (WAV/FLAC; MP3 needs ffmpeg) and measure it."""
    import librosa

    y, sr = librosa.load(path, sr=None, mono=False)
    result = measure(y, sr)
    result.update(platform_report(result))
    result["path"] = str(path)
    return result
