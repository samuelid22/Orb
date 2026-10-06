"""Local-only FFmpeg experiments; production strategies are not changed."""
from __future__ import annotations

import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def experiment():
    return runpy.run_path(str(ROOT / "scripts" / "benchmark-video-phase2.py"))


@pytest.mark.parametrize("times", [
    [.017, 1.007, 2.071, 3.71],
    [.5, .5, 1.0, 1.00000000001, 2.3],
    [.001, .017, .018, .333, 2.001, 3.79],
])
def test_real_batch_keeps_exact_evidence_order_dimensions_and_bytes(experiment, synthetic_video, tmp_path, times):
    ffmpeg = experiment["resolve_tool"]("ffmpeg")
    result, _ = experiment["batch"](ffmpeg, synthetic_video, times, tmp_path / "batch")
    observed_order = []
    for index, requested in enumerate(times):
        baseline_path = tmp_path / f"baseline_{index}.jpg"
        observation, _ = experiment["individual"](ffmpeg, synthetic_video, requested, baseline_path)
        seek = experiment["canonical_timestamp"](requested)
        path, actual = result[seek]
        comparison = experiment["compare"](baseline_path, path, observation, actual)
        assert comparison["same_jpeg"] and comparison["same_source"] and comparison["same_dimensions"]
        assert comparison["mae"] == 0 and comparison["pts_delta_ms"] < .1
        assert actual["dimensions"] == [320, 240]
        observed_order.append((index, requested, path.read_bytes()))
    assert len(observed_order) == len(times)
    assert [item[1] for item in observed_order] == times


def test_variable_frame_rate_odd_seeks_select_identical_source_frames(experiment, tmp_path):
    ffmpeg = experiment["resolve_tool"]("ffmpeg")
    source = tmp_path / "vfr.mp4"
    experiment["run"]([ffmpeg, "-nostdin", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
        "testsrc2=size=320x240:rate=30:duration=8,select='not(mod(n,3))+not(mod(n,5))'",
        "-fps_mode", "vfr", "-c:v", "libx264", "-preset", "ultrafast", "-g", "45", str(source)])
    times = [0, .001, .017, .333, 1.007, 2.071, 4.013, 7.75]
    result, _ = experiment["batch"](ffmpeg, source, times, tmp_path / "batch")
    for index, requested in enumerate(times):
        path = tmp_path / f"ref{index}.jpg"
        observation, _ = experiment["individual"](ffmpeg, source, requested, path)
        output, actual = result[experiment["canonical_timestamp"](requested)]
        comparison = experiment["compare"](path, output, observation, actual)
        assert comparison["same_jpeg"] and comparison["same_source"]
        assert comparison["mae"] == 0 and comparison["pts_delta_ms"] < .1


def test_batch_failure_cleans_its_own_partial_files(experiment, monkeypatch, tmp_path):
    destination = tmp_path / "batch"
    other = tmp_path / "unrelated.txt"
    other.write_text("keep")
    def failed_run(*args, **kwargs):
        (destination / "partial.jpg").write_bytes(b"partial")
        raise RuntimeError("simulated FFmpeg failure")
    monkeypatch.setitem(experiment["batch"].__globals__, "run", failed_run)
    with pytest.raises(RuntimeError, match="simulated FFmpeg"):
        experiment["batch"]("unused", tmp_path / "source.mp4", [.5], destination)
    assert not destination.exists() and other.read_text() == "keep"


def test_real_bad_input_does_not_leave_batch_artifacts(experiment, tmp_path):
    ffmpeg = experiment["resolve_tool"]("ffmpeg")
    source = tmp_path / "bad.mp4"
    source.write_bytes(b"invalid container")
    with pytest.raises(RuntimeError, match="FFmpeg experiment failed"):
        experiment["batch"](ffmpeg, source, [.5], tmp_path / "batch")
    assert not (tmp_path / "batch").exists()


@pytest.mark.parametrize("duration,scene_count,width,height", [
    (17.23, 2, 1024, 576), (30.09, 1, 720, 1564), (120.117, 12, 1280, 720),
])
def test_representative_batch_commands_keep_all_exact_seeks_and_quality(experiment, monkeypatch, tmp_path, duration, scene_count, width, height):
    uniform = experiment["uniform_timestamps"]
    scenes = [value for index in range(scene_count)
              for value in uniform(duration * index / scene_count, duration * (index + 1) / scene_count, 2)]
    globals_ = uniform(0, duration, 8)
    evidence = scenes + globals_
    calls = []
    def fake_run(command, **kwargs):
        calls.append(command)
        seeks = sorted({experiment["canonical_timestamp"](t) for t in evidence}, key=float)
        log = []
        output = Path(command[-1]).parent
        for index, seek in enumerate(seeks):
            (output / f"frame_{index+1:03}.jpg").write_bytes(b"mock-output")
            log.append(f"n: {index} pts_time:{seek} s:{width}x{height} checksum:ABCD")
        return type("Process", (), {"stderr": "\n".join(log)})(), {"wall_ms": 1, "cpu_ms": 1}
    monkeypatch.setitem(experiment["batch"].__globals__, "run", fake_run)
    mapping, _ = experiment["batch"]("ffmpeg", tmp_path / "source.mp4", evidence, tmp_path / "batch")
    assert len(calls) == 1
    assert calls[0][calls[0].index("-q:v") + 1] == "2"
    assert not any(option in calls[0] for option in ["-s", "-r", "-ss", "-threads"])
    assert [mapping[experiment["canonical_timestamp"](t)][1]["pts"] for t in evidence] == [float(experiment["canonical_timestamp"](t)) for t in evidence]
    assert all(frame["dimensions"] == [width, height] for _, frame in mapping.values())
    assert len(evidence) == scene_count * 2 + 8


def test_scene_flags_leave_algorithm_unchanged_and_do_not_force_a_different_stream(experiment):
    baseline = experiment["scene_command"]("ffmpeg", Path("source.mp4"), "baseline")
    no_audio = experiment["scene_command"]("ffmpeg", Path("source.mp4"), "no_audio")
    assert baseline[baseline.index("-vf") + 1] == no_audio[no_audio.index("-vf") + 1]
    assert all(flag in no_audio for flag in ["-an", "-sn", "-dn"])
    assert "-map" not in no_audio and "-s" not in no_audio and "-r" not in no_audio
