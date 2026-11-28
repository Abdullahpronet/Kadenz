"""Stage [2] Clip Analyzer: folder of clips -> shots.

Each clip is split into shots (PySceneDetect), and every shot gets a motion
score from optical flow and a "best moment": the timestamp where its motion
peaks. v0.2 adds AI tags; for now `tags` stays empty.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import cv2
import numpy as np
from scenedetect import ContentDetector, detect

SHOTS_VERSION = "0.1"

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
MOTION_RATE = 10.0   # motion samples per second
MOTION_WIDTH = 160   # frames are shrunk to this width for optical flow
MIN_SHOT = 0.25      # seconds; shorter shots are unusable as cuts

Progress = Callable[[int, int, str], None]


def find_clips(folder: str | Path) -> list[Path]:
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"Clips folder not found: {folder}")
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS)


def analyze(folder: str | Path, progress: Progress | None = None) -> dict:
    """Analyse every video clip in `folder` and return the shots map."""
    clips_found = find_clips(folder)
    if not clips_found:
        raise ValueError(f"No video clips in '{folder}'. Kadenz reads: {', '.join(sorted(VIDEO_EXTS))}")

    clips, shots, skipped = [], [], []
    for i, path in enumerate(clips_found):
        if progress:
            progress(i, len(clips_found), path.name)
        try:
            info, clip_shots = analyze_clip(path)
        except Exception as exc:  # one bad file should not stop the whole run
            skipped.append({"path": str(path.resolve()), "reason": str(exc) or type(exc).__name__})
            continue
        clips.append(info)
        shots.extend(clip_shots)
    if progress:
        progress(len(clips_found), len(clips_found), "")

    if not shots:
        reasons = "; ".join(f"{Path(s['path']).name}: {s['reason']}" for s in skipped)
        raise ValueError(f"Could not read any clips. {reasons}")

    peak = max(s["motion_raw"] for s in shots) or 1.0
    for s in shots:
        s["motion"] = round(s["motion_raw"] / peak, 3)

    return {"version": SHOTS_VERSION, "clips": clips, "shots": shots, "skipped": skipped}


def analyze_clip(path: str | Path) -> tuple[dict, list[dict]]:
    path = Path(path).resolve()
    with _readable_path(path) as src:
        times, motion, info = _motion_signal(src)
        cuts = _scene_bounds(src, info["duration"])
    info["path"] = str(path)

    shots = []
    for n, (a, b) in enumerate(cuts):
        if b - a < MIN_SHOT:
            continue
        # a flow sample compares frame t with the frame before it; skip the one across the cut
        inside = (times - 1.0 / info["fps"] >= a - 1e-6) & (times <= b + 1e-6)
        m = motion[inside]
        if m.size:
            smooth = np.convolve(m, np.ones(3) / 3, mode="same") if m.size >= 3 else m
            best = float(times[inside][int(np.argmax(smooth))])
            raw = float(m.mean())
        else:  # very short shot: no full sample inside
            best, raw = (a + b) / 2, 0.0
        shots.append({
            "id": f"{path.stem}#{n}",
            "clip": str(path),
            "start": _r(a),
            "end": _r(b),
            "duration": _r(b - a),
            "motion_raw": _r(raw, 4),
            "motion": 0.0,
            "best": _r(min(max(best, a), b)),
            "tags": [],
        })
    return info, shots


def save(shots_map: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(shots_map, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# --- internals ---------------------------------------------------------------

def _r(x: float, nd: int = 3) -> float:
    return round(float(x), nd)


@contextmanager
def _readable_path(path: Path) -> Iterator[Path]:
    """A path OpenCV can open.

    OpenCV on Windows cannot open files whose path has non-ASCII characters
    (Arabic, accents...). There we use the 8.3 short path when the drive has
    one, else read from a temporary ASCII-named copy.
    """
    if sys.platform != "win32" or str(path).isascii():
        yield path
        return
    short = _windows_short_path(path)
    if short and short.isascii():
        yield Path(short)
        return
    tmp = tempfile.mkdtemp(prefix="kadenz_")
    try:
        copy = Path(tmp) / f"clip{path.suffix.lower()}"
        shutil.copyfile(path, copy)
        yield copy
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _windows_short_path(path: Path) -> str | None:
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        n = ctypes.windll.kernel32.GetShortPathNameW(os.fspath(path), buf, len(buf))
        return buf.value if 0 < n < len(buf) else None
    except Exception:
        return None


def _open(path: Path) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError("cannot open video (unsupported codec or damaged file)")
    return cap


def _motion_signal(path: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    """Optical-flow motion sampled at MOTION_RATE, plus basic clip info."""
    cap = _open(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    step = max(1, round(fps / MOTION_RATE))

    def small_gray(frame):
        h = max(1, round(frame.shape[0] * MOTION_WIDTH / frame.shape[1]))
        small = cv2.resize(frame, (MOTION_WIDTH, h), interpolation=cv2.INTER_AREA)
        return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    # Every `step` frames, measure flow between that frame and the one just
    # before it, so the motion is per frame and fast pans stay trackable.
    times, motion = [], []
    prev, idx, read = None, 0, 0
    while cap.grab():
        want_prev = step > 1 and idx % step == step - 1
        if idx % step == 0 or want_prev:
            ok, frame = cap.retrieve()
            if not ok:
                break
            read += 1
            gray = small_gray(frame)
            if idx % step == 0 and prev is not None:
                flow = cv2.calcOpticalFlowFarneback(prev, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
                times.append(idx / fps)
                motion.append(float(np.linalg.norm(flow, axis=2).mean()))
            prev = gray
        idx += 1
    cap.release()

    if read == 0:
        raise ValueError("no readable frames")
    duration = (n_frames or idx) / fps
    info = {"path": str(path), "duration": _r(duration), "fps": _r(fps, 3), "width": width, "height": height}
    return np.array(times), np.array(motion), info


def _scene_bounds(path: Path, duration: float) -> list[tuple[float, float]]:
    scenes = detect(str(path), ContentDetector(), start_in_scene=True)
    bounds = [(s.seconds, e.seconds) for s, e in scenes]
    return bounds or [(0.0, duration)]
