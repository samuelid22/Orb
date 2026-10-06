"""Local generated-media experiment; no provider/API/database dependencies.

Not imported by production. Outputs live under ignored output/ by default.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from prometheus.video.tools import resolve_tool
from prometheus.video.sampler import canonical_timestamp, uniform_timestamps
from prometheus.video.segmenter import build_scene_spans

SHOW = re.compile(r"n:\s*(\d+).*?pts_time:([\d.e+-]+).*?s:(\d+)x(\d+).*?checksum:([0-9A-F]+)")
BENCH = re.compile(r"utime=([\d.]+)s stime=([\d.]+)s rtime=([\d.]+)s")
CUT = re.compile(r"pts_time:([\d.e+-]+)")


def run(args, timeout=600):
    start = time.perf_counter()
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    wall = (time.perf_counter() - start) * 1000
    if result.returncode:
        raise RuntimeError("Local FFmpeg experiment failed: " + result.stderr[-2000:])
    match = BENCH.search(result.stderr)
    return result, {"wall_ms": wall, "cpu_ms": (float(match[1]) + float(match[2])) * 1000 if match else None,
                    "ffmpeg_rtime_ms": float(match[3]) * 1000 if match else None}


def frames(log, offset=0):
    return [{"pts": float(m[2]) + offset, "dimensions": [int(m[3]), int(m[4])], "checksum": m[5]}
            for m in SHOW.finditer(log)]


def scene_command(ffmpeg, source, variant):
    cmd = [ffmpeg, "-nostdin", "-benchmark"]
    if variant in {"threads1", "threads2"}:
        cmd += ["-threads:v", variant[-1], "-filter_threads", variant[-1]]
    cmd += ["-i", str(source)]
    if variant != "baseline":
        cmd += ["-an", "-sn", "-dn"]
    if variant == "video_map":
        cmd += ["-map", "0:v:0"]  # Experimental only; NOT safe for general auto-selection.
    return cmd + ["-vf", "select='gt(scene,0.3)',showinfo", "-f", "null", "-"]


def detect(ffmpeg, source, duration, variant):
    result, timing = run(scene_command(ffmpeg, source, variant))
    cuts = sorted({float(value) for value in CUT.findall(result.stderr) if 0 <= float(value) < duration})
    dedup = []
    for value in cuts:
        if not dedup or value - dedup[-1] > .2:
            dedup.append(value)
    return dedup, timing


def individual(ffmpeg, source, timestamp, destination, variant="baseline"):
    seek = canonical_timestamp(timestamp)
    cmd = [ffmpeg, "-nostdin", "-y", "-benchmark", "-loglevel", "info"]
    if variant in {"threads1", "threads2"}:
        cmd += ["-threads:v", variant[-1]]
    if variant != "output_seek":
        cmd += ["-ss", seek]
    cmd += ["-i", str(source)]
    if variant == "output_seek":
        cmd += ["-ss", seek]
    if variant != "baseline":
        cmd += ["-an", "-sn", "-dn"]
    # showinfo observes the decoded source before automatic output conversion.
    cmd += ["-vf", "showinfo", "-frames:v", "1", "-q:v", "2", str(destination)]
    result, timing = run(cmd, timeout=120)
    observations = frames(result.stderr, 0 if variant == "output_seek" else float(seek))
    if not destination.is_file() or not observations:
        raise RuntimeError("Missing experimental frame/diagnostic timestamp")
    if variant == "output_seek":
        # Output-side seeking filters after showinfo; identify the emitted frame
        # by comparing image output, rather than claiming the first log is it.
        observation = {"pts": None, "dimensions": list(Image.open(destination).size), "checksum": None}
    else:
        observation = observations[0]
    return observation, timing


def batch(ffmpeg, source, timestamps, destination):
    destination.mkdir(parents=True, exist_ok=True)
    seeks = sorted({canonical_timestamp(t) for t in timestamps}, key=float)
    # First decoded frame at/after each seek, without merging distinct seeks.
    expression = "+".join(f"gte(t,{s})*if(isnan(prev_pts),1,lt(prev_pts*TB,{s}))" for s in seeks)
    cmd = [ffmpeg, "-nostdin", "-y", "-benchmark", "-loglevel", "info", "-i", str(source),
           "-an", "-sn", "-dn", "-vf", f"select='{expression}',showinfo",
           "-fps_mode", "vfr", "-q:v", "2", str(destination / "frame_%03d.jpg")]
    try:
        result, timing = run(cmd)
        paths = sorted(destination.glob("frame_*.jpg"))
        observed = frames(result.stderr)[:len(paths)]
        if len(paths) != len(observed):
            raise RuntimeError("Incomplete batch diagnostics")
        mapping = {}
        for seek in seeks:
            selected = next(((path, frame) for path, frame in zip(paths, observed) if frame["pts"] + 1e-7 >= float(seek)), None)
            if selected is None:
                raise RuntimeError("No batch frame for requested seek")
            mapping[seek] = selected
        return mapping, timing
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def compare(reference_path, path, reference, observed):
    same_bytes = reference_path.read_bytes() == path.read_bytes()
    with Image.open(reference_path) as a, Image.open(path) as b:
        dimensions = a.size == b.size
        if not dimensions:
            return {"same_jpeg": False, "same_dimensions": False, "same_source": False}
        histogram = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).histogram()
        samples = a.width * a.height * 3
    mse = sum(count * (index % 256) ** 2 for index, count in enumerate(histogram)) / samples
    return {"same_jpeg": same_bytes, "same_dimensions": dimensions,
            "same_source": observed["checksum"] == reference["checksum"] if observed["checksum"] is not None else same_bytes,
            "pts_delta_ms": abs(observed["pts"] - reference["pts"]) * 1000 if observed["pts"] is not None else None,
            "mae": sum(count * (index % 256) for index, count in enumerate(histogram)) / samples,
            "psnr_db": round(10 * math.log10(255 ** 2 / mse), 4) if mse else None}


def generate(ffmpeg, root, name, width, height, duration, interval):
    source = root / (name + ".mp4")
    if not source.exists():
        filters = [f"testsrc2=size={width}x{height}:rate=24:duration={duration}"]
        if interval:
            filters += [f"negate=enable='mod(floor(t/{interval}),2)'"]
        run([ffmpeg, "-nostdin", "-y", "-loglevel", "error", "-f", "lavfi", "-i", ",".join(filters),
             "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={duration}",
             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-g", "48", "-threads:v", "2",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(source)])
    return source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "video-phase2")
    parser.add_argument("--fixtures", nargs="+", default=["short", "medium", "long"])
    parser.add_argument("--variants", nargs="+", default=["single_batch", "two_batch", "no_audio", "threads1", "threads2", "output_seek"])
    parser.add_argument("--fixture-dir", type=Path)
    parser.add_argument("--one-cpu", action="store_true", help="Local experiment process and children only; never infrastructure")
    args = parser.parse_args()
    root = args.output.resolve()
    # Restrict generated/cleaned paths to the repository's ignored runtime tree.
    if not root.is_relative_to(ROOT / "output"):
        raise ValueError("Benchmark output must stay under Orb/output")
    fixture_root = args.fixture_dir.resolve() if args.fixture_dir else root
    if not fixture_root.is_relative_to(ROOT / "output"):
        raise ValueError("Generated fixtures must stay under Orb/output")
    if args.one_cpu:
        if os.name == "nt":
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.GetCurrentProcess.restype = ctypes.c_void_p
            handle = kernel.GetCurrentProcess()
            process_mask, system_mask = ctypes.c_size_t(), ctypes.c_size_t()
            kernel.GetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)]
            kernel.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
            if not kernel.GetProcessAffinityMask(handle, ctypes.byref(process_mask), ctypes.byref(system_mask)):
                raise OSError("Could not read local benchmark affinity")
            mask = process_mask.value & -process_mask.value
            if not kernel.SetProcessAffinityMask(handle, mask):
                raise OSError("Could not set local benchmark-only affinity")
        else:
            os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    root.mkdir(parents=True, exist_ok=True)
    ffmpeg = resolve_tool("ffmpeg")
    version = subprocess.check_output([ffmpeg, "-version"], text=True).splitlines()[0]
    startups = [run([ffmpeg, "-version"])[1]["wall_ms"] for _ in range(5)]
    report_path = root / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {"fixtures": {}}
    report.update(version=version, startup_median_ms=statistics.median(startups), cpu_budget="one" if args.one_cpu else "default")
    specs = {"short": (1024, 576, 17.23, 8.5), "medium": (720, 1564, 30.09, None), "long": (1280, 720, 120.117, 10)}
    for name in args.fixtures:
        width, height, duration, interval = specs[name]
        fixture_root.mkdir(parents=True, exist_ok=True)
        source = generate(ffmpeg, fixture_root, name, width, height, duration, interval)
        scene_results = {}
        for variant in ["baseline", "no_audio", "video_map", "threads1", "threads2"]:
            cuts, timing = detect(ffmpeg, source, duration, variant)
            scene_results[variant] = {**timing, "cuts": cuts}
        cuts = scene_results["baseline"]["cuts"]
        spans = build_scene_spans([0.0] + cuts + [duration], 1.0, 12)
        scene_times = [timestamp for start, end in spans for timestamp in uniform_timestamps(start, end, 2)]
        global_times = uniform_timestamps(0, duration, 8)
        # Preserve evidence order separately from the sorted extraction plan.
        evidence = scene_times + global_times
        unique = list(dict.fromkeys(canonical_timestamp(t) for t in evidence))
        directory = root / name
        directory.mkdir(exist_ok=True)
        reference = {}
        baseline_ms = baseline_cpu = baseline_rtime = 0
        for index, seek in enumerate(unique):
            path = directory / f"baseline_{index:03}.jpg"
            observation, timing = individual(ffmpeg, source, float(seek), path)
            baseline_ms += timing["wall_ms"]
            baseline_cpu += timing["cpu_ms"] or 0
            baseline_rtime += timing["ffmpeg_rtime_ms"] or 0
            reference[seek] = (path, observation)
        extraction = {"baseline": {"wall_ms": baseline_ms, "cpu_ms": baseline_cpu, "ffmpeg_rtime_ms": baseline_rtime, "launches": len(unique),
                                     "evidence_entries": len(evidence), "unique_frames": len(unique)}}
        for variant in args.variants:
            mapping = {}
            wall = cpu = launches = 0
            if variant in {"single_batch", "two_batch"}:
                groups = [evidence] if variant == "single_batch" else [scene_times, global_times]
                for index, group in enumerate(groups):
                    result, timing = batch(ffmpeg, source, group, directory / (variant + str(index)))
                    mapping.update(result)
                    wall += timing["wall_ms"]
                    cpu += timing["cpu_ms"] or 0
                    launches += 1
            else:
                for index, seek in enumerate(unique):
                    path = directory / f"{variant}_{index:03}.jpg"
                    observation, timing = individual(ffmpeg, source, float(seek), path, variant)
                    mapping[seek] = (path, observation)
                    wall += timing["wall_ms"]
                    cpu += timing["cpu_ms"] or 0
                    launches += 1
            comparisons = []
            for timestamp in evidence:
                seek = canonical_timestamp(timestamp)
                path, observation = mapping[seek]
                ref_path, ref = reference[seek]
                comparisons.append({"requested_timestamp": timestamp, "canonical_seek": seek,
                                    "baseline_pts": ref["pts"], "actual_pts": observation["pts"],
                                    "dimensions": observation["dimensions"], **compare(ref_path, path, ref, observation)})
            extraction[variant] = {"wall_ms": wall, "cpu_ms": cpu, "launches": launches,
                "evidence_entries": len(comparisons), "same_jpeg": sum(c["same_jpeg"] for c in comparisons),
                "same_source": sum(c["same_source"] for c in comparisons), "comparisons": comparisons}
        record = {"duration": duration, "dimensions": [width, height], "scene_count": len(spans),
                  "scene_detection": scene_results, "extraction": extraction}
        report["fixtures"][name] = record
        (root / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("PHASE2 " + json.dumps({"fixture": name, "scene_count": len(spans),
              "scene_ms": {k: round(v["wall_ms"], 1) for k, v in scene_results.items()},
              "equivalent_cuts": {k: v["cuts"] == cuts for k, v in scene_results.items()},
              "extraction": {k: {key: round(val, 1) if isinstance(val, float) else val for key, val in v.items() if key != "comparisons"}
                             for k, v in extraction.items()}}, sort_keys=True), flush=True)
    print("Sanitized local benchmark report: " + (root / "report.json").relative_to(ROOT).as_posix(), flush=True)


if __name__ == "__main__":
    main()
