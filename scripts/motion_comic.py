"""Deterministic FFmpeg assembly for the hybrid 2.5D motion-comic cut.

The GPU worker creates the illustrated keyframe parallax clip; this module combines
selected hero-video intervals and depth-parallax intervals into an exact-timed montage.
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path
from typing import Any


def build_editorial_filter_graph(
    shots: list[dict[str, Any]],
    *,
    width: int = 1080,
    height: int = 1920,
    fps: int = 24,
    video_speed_ratio: float = 1.0,
    video_hold_duration: float = 0.0,
) -> str:
    if not shots:
        raise ValueError("Editorial montage requires at least one shot.")
    if width <= 0 or height <= 0 or fps <= 0:
        raise ValueError("Editorial output dimensions and frame rate must be positive.")
    if not math.isfinite(video_speed_ratio) or video_speed_ratio <= 0:
        raise ValueError("Video speed ratio must be finite and positive.")
    if not math.isfinite(video_hold_duration) or video_hold_duration < 0:
        raise ValueError("Video hold duration must be finite and non-negative.")

    hero_count = sum(1 for shot in shots if shot.get("source") == "hero_video")
    parallax_count = sum(1 for shot in shots if shot.get("source") == "depth_parallax")
    if hero_count + parallax_count != len(shots):
        raise ValueError("Editorial shot source must be hero_video or depth_parallax.")

    parts: list[str] = []
    labels: list[str] = []
    for input_index, count, prefix in ((0, hero_count, "h"), (1, parallax_count, "p")):
        if count == 0:
            continue
        filters = [f"[{input_index}:v]setpts=PTS*{video_speed_ratio:.7f}"]
        if video_hold_duration > 0.001:
            filters.append(f"tpad=stop_mode=clone:stop_duration={video_hold_duration:.4f}")
        if count > 1:
            outputs = "".join(f"[{prefix}{index}]" for index in range(count))
            filters.append(f"split={count}{outputs}")
        else:
            filters.append(f"[{prefix}0]")
        parts.append(",".join(filters))
    source_indexes = {"hero_video": 0, "depth_parallax": 0}
    hero_position = 0
    parallax_position = 0

    for index, shot in enumerate(shots):
        source = str(shot.get("source") or "")
        prefix = "h" if source == "hero_video" else "p"
        local_index = hero_position if prefix == "h" else parallax_position
        if prefix == "h":
            hero_position += 1
        else:
            parallax_position += 1
        start = float(shot.get("start_seconds", 0.0))
        end = float(shot.get("end_seconds", 0.0))
        duration = end - start
        zoom = float(shot.get("zoom", 1.0))
        crop_x = float(shot.get("crop_x", 0.5))
        crop_y = float(shot.get("crop_y", 0.5))
        if not all(math.isfinite(value) for value in (start, end, zoom, crop_x, crop_y)):
            raise ValueError(f"Shot {index + 1} contains non-finite timing/crop data.")
        if start < 0 or duration < 0.05 or not 1.0 <= zoom <= 1.25:
            raise ValueError(f"Shot {index + 1} has an invalid time range or zoom.")
        if not 0.0 <= crop_x <= 1.0 or not 0.0 <= crop_y <= 1.0:
            raise ValueError(f"Shot {index + 1} crop anchor must be within 0..1.")
        scaled_width = int(math.ceil(width * zoom / 2.0) * 2)
        scaled_height = int(math.ceil(height * zoom / 2.0) * 2)
        label = f"v{index}"
        parts.append(
            f"[{prefix}{local_index}]trim=start={start:.4f}:end={end:.4f},"
            f"setpts=PTS-STARTPTS,scale={scaled_width}:{scaled_height}:flags=lanczos,"
            f"crop={width}:{height}:x=(iw-ow)*{crop_x:.4f}:y=(ih-oh)*{crop_y:.4f},"
            f"fps={fps},setsar=1,format=yuv420p[{label}]"
        )
        labels.append(f"[{label}]")
    parts.append("".join(labels) + f"concat=n={len(shots)}:v=1:a=0[outv]")
    return ";".join(parts)


def render_editorial_montage(
    hero_video: Path,
    depth_parallax_video: Path,
    destination: Path,
    shots: list[dict[str, Any]],
    *,
    target_duration: float,
    video_speed_ratio: float = 1.0,
    video_hold_duration: float = 0.0,
    fps: int = 24,
) -> Path:
    if not hero_video.is_file() or not depth_parallax_video.is_file():
        raise FileNotFoundError("Both source hero video and depth-parallax video are required.")
    if not math.isfinite(float(target_duration)) or target_duration <= 0:
        raise ValueError("Montage target duration must be finite and positive.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.stem + ".partial.mp4")
    temporary.unlink(missing_ok=True)
    graph = build_editorial_filter_graph(
        shots, fps=fps, video_speed_ratio=video_speed_ratio,
        video_hold_duration=video_hold_duration,
    )
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(hero_video), "-i", str(depth_parallax_video),
        "-filter_complex", graph, "-map", "[outv]", "-an",
        "-t", f"{target_duration:.4f}", "-r", str(fps),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temporary),
    ]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
    if result.returncode:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"2.5D editorial montage failed ({result.returncode}): {result.stdout[-3000:]}")
    if not temporary.is_file() or temporary.stat().st_size < 100_000:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("2.5D editorial montage is missing or too small.")
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(temporary),
    ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=45)
    try:
        measured = float(probe.stdout.strip())
    except (TypeError, ValueError) as exc:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("2.5D montage duration could not be verified by ffprobe.") from exc
    if probe.returncode or abs(measured - target_duration) > max(0.15, 2.0 / fps):
        temporary.unlink(missing_ok=True)
        raise RuntimeError(
            f"2.5D montage duration mismatch: expected {target_duration:.3f}s, measured {measured:.3f}s."
        )
    temporary.replace(destination)
    return destination
