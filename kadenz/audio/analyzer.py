"""Stage [1] Audio Analyzer: song file -> music_map.

The music map is the timing skeleton every later stage builds on:
tempo, beats, downbeats, a loudness curve and labelled sections.
No AI is involved; everything here is classic signal processing with librosa.
"""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path

import librosa
import numpy as np

MUSIC_MAP_VERSION = "0.1"

SR = 22050          # analysis sample rate; plenty for rhythm and loudness
HOP = 512           # ~23 ms per analysis frame at 22.05 kHz
BEATS_PER_BAR = 4   # 4/4 time; almost all montage music is in 4/4
BARS_PER_PHRASE = 4  # sections are built from 4-bar phrases (16 beats)
ENERGY_RATE = 10    # samples per second in the exported energy curve


def analyze(song_path: str | Path) -> dict:
    """Analyse a song and return its music map as a plain dict."""
    song_path = Path(song_path)
    y, sr = librosa.load(str(song_path), sr=SR, mono=True)
    duration = float(len(y) / sr)
    if duration < 2.0:
        raise ValueError(
            f"'{song_path.name}' is only {duration:.1f} s long; Kadenz needs at least a few seconds of music."
        )

    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
    tempo, rough_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, hop_length=HOP)
    rough_times = librosa.frames_to_time(rough_frames, sr=sr, hop_length=HOP)
    if len(rough_times) < BEATS_PER_BAR * 2:
        raise ValueError(f"Could not find a steady beat in '{song_path.name}'. Try a track with a clear rhythm.")

    beat_times, bpm = _fit_grid(y, sr, float(np.atleast_1d(tempo)[0]), rough_times, duration)
    beat_frames = librosa.time_to_frames(beat_times, sr=sr, hop_length=HOP)

    # How hard each beat hits (onset strength at the beat, scaled 0..1).
    strength = onset_env[np.clip(beat_frames, 0, len(onset_env) - 1)]
    beat_strength = strength / (strength.max() or 1.0)

    downbeat_phase = _downbeat_phase(y, sr, beat_frames)
    downbeats = beat_times[downbeat_phase::BEATS_PER_BAR]

    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=HOP)
    energy = _energy_curve(rms, rms_times, duration)
    sections = _sections(rms, rms_times, downbeats, duration)

    return {
        "version": MUSIC_MAP_VERSION,
        "song": str(song_path.resolve()),
        "duration": _r(duration),
        "bpm": _r(bpm, 2),
        "beats_per_bar": BEATS_PER_BAR,
        "beats": [_r(t) for t in beat_times],
        "beat_strength": [_r(s) for s in beat_strength],
        "downbeats": [_r(t) for t in downbeats],
        "energy": {"rate": ENERGY_RATE, "values": [_r(v) for v in energy]},
        "sections": sections,
    }


def save(music_map: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(music_map, indent=2), encoding="utf-8")
    return path


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# --- internals ---------------------------------------------------------------

def _r(x: float, nd: int = 3) -> float:
    return round(float(x), nd)


FINE_HOP = 128  # ~6 ms frames for precise beat placement


def _fit_grid(y, sr, bpm0, rough_times, duration):
    """Find the exact tempo and phase of a fixed-tempo beat grid.

    librosa's tracker measures the beat period in whole frames, so its tempo is
    rounded (120 BPM comes out as 117.45) and its beats drift. Montage music is
    almost always produced at a fixed tempo, so we search tempos within +-4% of
    librosa's estimate, and every phase, for the grid that lands hardest on the
    onsets. If the grid fits clearly worse than librosa's own beats (the tempo
    changes during the song), we keep librosa's beats instead.
    """
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=FINE_HOP)
    t_env = librosa.frames_to_time(np.arange(len(env)), sr=sr, hop_length=FINE_HOP)
    env = env / (env.max() or 1.0)

    def score(period, phases):
        k = np.arange(int(duration / period) + 1)
        t = phases[:, None] + k[None, :] * period
        vals = np.interp(t, t_env, env, left=0.0, right=0.0)
        return np.where(t < duration, vals, 0.0).sum(axis=1) / (duration / period)

    best = (-1.0, 60.0 / bpm0, 0.0)
    for span, steps in ((0.04, 161), (None, 41)):  # coarse, then fine around the best
        centre = best[1]
        lo, hi = ((centre * (1 - span), centre * (1 + span)) if span
                  else (centre - 0.0015 * centre, centre + 0.0015 * centre))
        for period in np.linspace(lo, hi, steps):
            phases = np.arange(0.0, period, 0.002)
            s = score(period, phases)
            i = int(np.argmax(s))
            if s[i] > best[0]:
                best = (float(s[i]), float(period), float(phases[i]))

    grid_score, period, phase = best
    rough_score = float(np.interp(rough_times, t_env, env).mean())
    if grid_score < 0.8 * rough_score:  # tempo is not steady: trust the tracker
        bpm = 60.0 / float(np.median(np.diff(rough_times)))
        return rough_times, bpm

    beats = np.arange(phase, duration, period)
    return beats, 60.0 / period


def _downbeat_phase(y: np.ndarray, sr: int, beat_frames: np.ndarray) -> int:
    """Pick which of the 4 beat positions is the downbeat.

    Bar starts usually carry the kick drum and bass, so we score each phase by
    the low-frequency onset strength on its beats and take the strongest.
    Simple and fast; madmom/beat_this are the upgrade path for tricky tracks.
    """
    low = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP, fmax=200, n_mels=32)
    idx = np.clip(beat_frames, 0, len(low) - 1)
    scores = [low[idx[p::BEATS_PER_BAR]].mean() for p in range(BEATS_PER_BAR)]
    return int(np.argmax(scores))


def _energy_curve(rms: np.ndarray, rms_times: np.ndarray, duration: float) -> np.ndarray:
    """Loudness curve resampled to ENERGY_RATE Hz and scaled 0..1."""
    grid = np.arange(0, duration, 1.0 / ENERGY_RATE)
    curve = np.interp(grid, rms_times, rms)
    # smooth over ~0.5 s so single hits don't dominate
    k = max(1, ENERGY_RATE // 2)
    curve = np.convolve(curve, np.ones(k) / k, mode="same")
    peak = curve.max() or 1.0
    return curve / peak


def _sections(rms, rms_times, downbeats, duration) -> list[dict]:
    """Split the song into labelled sections built from 4-bar phrases.

    Each phrase gets a loudness level (low / mid / high, relative to this song).
    Neighbouring phrases at the same level merge into one section, which is then
    named by level and position: high = drop, low = intro / breakdown / outro,
    mid = build-up when it leads into a drop, otherwise verse.
    """
    bounds = [0.0, *downbeats[BARS_PER_PHRASE::BARS_PER_PHRASE], duration]
    if downbeats[0] > 0 and len(bounds) > 2 and bounds[1] - bounds[0] < 0.5:
        bounds.pop(1)

    phrase_energy = []
    for a, b in pairwise(bounds):
        mask = (rms_times >= a) & (rms_times < b)
        phrase_energy.append(float(rms[mask].mean()) if mask.any() else 0.0)
    e = np.array(phrase_energy)

    lo, hi = np.percentile(e, 10), np.percentile(e, 90)
    norm = np.clip((e - lo) / (hi - lo), 0, 1) if hi - lo > 1e-9 else np.full_like(e, 0.5)
    if hi - lo <= 0.15 * max(hi, 1e-9):  # song is flat: one level throughout
        levels = ["mid"] * len(e)
    else:
        levels = ["high" if v >= 0.66 else "low" if v < 0.33 else "mid" for v in norm]

    merged: list[dict] = []
    for (a, b), lvl, n in zip(pairwise(bounds), levels, norm, strict=True):
        if merged and merged[-1]["level"] == lvl:
            m = merged[-1]
            m["end"] = b
            m["_e"].append(n)
        else:
            merged.append({"start": a, "end": b, "level": lvl, "_e": [n]})

    out = []
    for i, s in enumerate(merged):
        nxt = merged[i + 1]["level"] if i + 1 < len(merged) else None
        if s["level"] == "high":
            label = "drop"
        elif s["level"] == "low":
            label = "intro" if i == 0 else "outro" if i == len(merged) - 1 else "breakdown"
        else:
            label = "build-up" if nxt == "high" else "intro" if i == 0 else "verse"
        out.append({
            "start": _r(s["start"]),
            "end": _r(s["end"]),
            "label": label,
            "energy": _r(np.mean(s["_e"])),
        })
    return out
