import pytest

from kadenz import vision
from tests.fixtures import cut_video, plain_video

FRAME = 1 / 30


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("clips")
    truth = cut_video(d / "a_cuts.mp4")
    plain_video(d / "b_plain clip.mp4")
    (d / "notes.txt").write_text("not a video")
    (d / "c_broken.mp4").write_bytes(b"this is not an mp4")
    return d, truth


@pytest.fixture(scope="module")
def result(clips):
    d, _ = clips
    calls = []
    out = vision.analyze(d, progress=lambda i, n, name: calls.append((i, n, name)))
    return out, calls


def _shots_of(out, stem):
    return [s for s in out["shots"] if s["id"].startswith(stem + "#")]


def test_shot_bounds(result, clips):
    out, _ = result
    _, truth = clips
    shots = _shots_of(out, "a_cuts")
    assert len(shots) == 3
    for s, (a, b) in zip(shots, truth["bounds"], strict=True):
        assert s["start"] == pytest.approx(a, abs=2 * FRAME)
        assert s["end"] == pytest.approx(b, abs=2 * FRAME)


def test_motion_ranking(result):
    out, _ = result
    still, fast, slow = _shots_of(out, "a_cuts")
    assert fast["motion"] == 1.0
    assert fast["motion"] > slow["motion"] > still["motion"]
    assert still["motion"] < 0.05


def test_best_moment(result, clips):
    out, _ = result
    _, truth = clips
    fast = _shots_of(out, "a_cuts")[1]
    assert fast["best"] == pytest.approx(truth["peak"], abs=0.3)
    for s in out["shots"]:
        assert s["start"] <= s["best"] <= s["end"]


def test_clip_without_cuts_is_one_shot(result):
    out, _ = result
    shots = _shots_of(out, "b_plain clip")
    assert len(shots) == 1
    assert shots[0]["start"] == 0.0
    assert shots[0]["end"] == pytest.approx(3.0, abs=2 * FRAME)


def test_skips_bad_files(result):
    out, calls = result
    assert [p["path"].endswith("c_broken.mp4") for p in out["skipped"]] == [True]
    assert {c["path"].split("/")[-1] for c in out["clips"]} == {"a_cuts.mp4", "b_plain clip.mp4"}
    assert calls[0] == (0, 3, "a_cuts.mp4") and calls[-1][0] == 3


def test_clip_info(result):
    out, _ = result
    info = out["clips"][0]
    assert info["fps"] == pytest.approx(30.0)
    assert (info["width"], info["height"]) == (320, 180)
    assert info["duration"] == pytest.approx(7.0, abs=2 * FRAME)


def test_unicode_name_and_roundtrip(tmp_path):
    plain_video(tmp_path / "لقطة 1.mp4", seconds=1.5)
    out = vision.analyze(tmp_path)
    assert len(out["shots"]) == 1
    p = vision.save(out, tmp_path / "cache" / "shots.json")
    assert vision.load(p) == out
    assert "لقطة" in p.read_text(encoding="utf-8")


def test_empty_and_missing_folder(tmp_path):
    with pytest.raises(ValueError, match="No video clips"):
        vision.analyze(tmp_path)
    with pytest.raises(FileNotFoundError):
        vision.analyze(tmp_path / "nope")
