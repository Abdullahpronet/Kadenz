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


# --- video -------------------------------------------------------------------

VIDEO_FPS = 30
VIDEO_SIZE = (320, 180)


def _texture(rng: np.random.Generator, tint: tuple[int, int, int], w: int, h: int) -> np.ndarray:
    import cv2
    base = rng.integers(0, 255, (h // 8, w // 8), dtype=np.uint8)
    base = cv2.resize(base, (w, h), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255
    img = np.stack([base * c for c in tint], axis=2)
    return img.clip(0, 255).astype(np.uint8)


def cut_video(path: Path, seed: int = 0) -> dict:
    """Write a 7 s, 30 fps clip with hard cuts at 2.0 s and 4.5 s.

    Shot A (0-2 s): still blue frame, no motion.
    Shot B (2-4.5 s): grey texture panning fast; pan speed peaks at 3.5 s.
    Shot C (4.5-7 s): red texture panning slowly.
    """
    import cv2
    rng = np.random.default_rng(seed)
    w, h = VIDEO_SIZE
    wide_b = _texture(rng, (200, 200, 200), w * 6, h)
    wide_c = _texture(rng, (40, 60, 230), w * 2, h)  # BGR: red-ish
    still = np.full((h, w, 3), (180, 90, 20), np.uint8)
    still[h // 3: 2 * h // 3, w // 3: 2 * w // 3] = (220, 140, 60)

    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), VIDEO_FPS, (w, h))
    x_b = x_c = 0.0
    for i in range(7 * VIDEO_FPS):
        t = i / VIDEO_FPS
        if t < 2.0:
            frame = still
        elif t < 4.5:
            x_b += max(1.0, 12.0 - 10.0 * abs(t - 3.5))
            frame = wide_b[:, int(x_b): int(x_b) + w]
        else:
            x_c += 1.0
            frame = wide_c[:, int(x_c): int(x_c) + w]
        writer.write(np.ascontiguousarray(frame))
    writer.release()
    return {"bounds": [(0.0, 2.0), (2.0, 4.5), (4.5, 7.0)], "peak": 3.5, "duration": 7.0}


def plain_video(path: Path, seconds: float = 3.0) -> None:
    """A clip with no cuts: one slowly panning texture."""
    import cv2
    rng = np.random.default_rng(1)
    w, h = VIDEO_SIZE
    wide = _texture(rng, (90, 200, 90), w * 2, h)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), VIDEO_FPS, (w, h))
    for i in range(int(seconds * VIDEO_FPS)):
        writer.write(np.ascontiguousarray(wide[:, 2 * i: 2 * i + w]))
    writer.release()
