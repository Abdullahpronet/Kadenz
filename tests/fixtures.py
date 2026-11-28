"""Generated test media. Nothing here is committed as a media file."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

SR = 22050


def _tone(freq: float, dur: float, decay: float) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    return np.sin(2 * np.pi * freq * t) * np.exp(-t / decay)


def click_track(
    path: Path,
    bpm: float = 120.0,
    bars_quiet: int = 16,
    bars_loud: int = 16,
    lead_in: float = 0.5,
    seed: int = 0,
) -> dict:
    """Write a 4/4 track: a kick on beat 1 of each bar, a click on every beat.

    The first `bars_quiet` bars are quiet, the next `bars_loud` are loud (with
    an added noise bed), so the loud part should be detected as a drop.
    Returns the ground truth: beat times, downbeat times and the drop start.
    """
    rng = np.random.default_rng(seed)
    beat = 60.0 / bpm
    n_bars = bars_quiet + bars_loud
    total = lead_in + n_bars * 4 * beat + 1.0
    y = np.zeros(int(total * SR), dtype=np.float64)

    kick = _tone(55, 0.25, 0.06) + 0.5 * _tone(110, 0.25, 0.04)
    click = _tone(2000, 0.05, 0.01)

    beats, downbeats = [], []
    for i in range(n_bars * 4):
        t = lead_in + i * beat
        gain = 0.15 if i < bars_quiet * 4 else 1.0
        start = int(t * SR)
        y[start:start + len(click)] += gain * 0.6 * click
        if i % 4 == 0:
            y[start:start + len(kick)] += gain * kick
            downbeats.append(t)
        beats.append(t)

    drop_start = lead_in + bars_quiet * 4 * beat
    loud = slice(int(drop_start * SR), int((drop_start + bars_loud * 4 * beat) * SR))
    y[loud] += 0.25 * rng.standard_normal(loud.stop - loud.start)

    y /= np.abs(y).max()
    sf.write(str(path), (0.9 * y).astype(np.float32), SR)
    return {"bpm": bpm, "beats": np.array(beats), "downbeats": np.array(downbeats), "drop_start": drop_start}
