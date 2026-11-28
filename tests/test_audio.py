import json
from itertools import pairwise

import numpy as np
import pytest

from kadenz import audio
from tests.fixtures import click_track

TOL = 0.04  # 40 ms: about 2 frames at 60 fps


@pytest.fixture(scope="module", params=[120.0, 140.0])
def analysed(request, tmp_path_factory):
    path = tmp_path_factory.mktemp("audio") / f"click_{int(request.param)}.wav"
    truth = click_track(path, bpm=request.param)
    return truth, audio.analyze(path)


def _nearest(a, b):
    """Distance from every time in `a` to its nearest time in `b`."""
    b = np.asarray(b)
    return np.array([np.abs(b - t).min() for t in a])


def test_bpm(analysed):
    truth, m = analysed
    assert m["bpm"] == pytest.approx(truth["bpm"], rel=0.02)


def test_beats_line_up(analysed):
    truth, m = analysed
    hit = _nearest(truth["beats"], m["beats"]) < TOL
    assert hit.mean() > 0.95
    assert len(m["beat_strength"]) == len(m["beats"])


def test_downbeats_are_bar_starts(analysed):
    truth, m = analysed
    # the grid keeps counting through silence at the end; check where music plays
    playing = [t for t in m["downbeats"] if t <= truth["beats"][-1] + TOL]
    assert len(playing) == len(truth["downbeats"])
    assert (_nearest(playing, truth["downbeats"]) < TOL).all()


def test_drop_found(analysed):
    truth, m = analysed
    drops = [s for s in m["sections"] if s["label"] == "drop"]
    assert drops, m["sections"]
    phrase = 16 * 60.0 / truth["bpm"]
    assert abs(drops[0]["start"] - truth["drop_start"]) <= phrase + TOL
    assert m["sections"][0]["label"] in {"intro", "build-up"}


def test_sections_cover_song(analysed):
    _, m = analysed
    s = m["sections"]
    assert s[0]["start"] == 0.0
    assert s[-1]["end"] == pytest.approx(m["duration"], abs=1e-3)
    for a, b in pairwise(s):
        assert a["end"] == pytest.approx(b["start"], abs=1e-6)


def test_energy_curve(analysed):
    _, m = analysed
    v = m["energy"]["values"]
    assert len(v) == pytest.approx(m["duration"] * m["energy"]["rate"], abs=2)
    assert 0.0 <= min(v) and max(v) <= 1.0


def test_save_load_roundtrip(analysed, tmp_path):
    _, m = analysed
    p = audio.save(m, tmp_path / "cache" / "music_map.json")
    assert audio.load(p) == json.loads(json.dumps(m))


def test_too_short(tmp_path):
    import soundfile as sf
    p = tmp_path / "blip.wav"
    sf.write(str(p), np.zeros(22050, dtype=np.float32), 22050)
    with pytest.raises(ValueError, match="at least"):
        audio.analyze(p)


def test_mp3_with_unicode_name(tmp_path):
    import soundfile as sf
    src = tmp_path / "src.wav"
    click_track(src, bpm=128.0, bars_quiet=4, bars_loud=4)
    y, sr = sf.read(str(src))
    mp3 = tmp_path / "أغنية my track.mp3"
    sf.write(str(mp3), y, sr, format="MP3")
    m = audio.analyze(mp3)
    assert m["bpm"] == pytest.approx(128.0, rel=0.02)
