"""Adaptive Hindi short-form story timing and editorial coverage planning.

Six screenplay beats remain the narrative spine. This module derives 7–14 editorial
shots from measured voice timings; it never adds plot events or shortens dialogue.
"""
from __future__ import annotations

import math
from typing import Any

STORY_POLICIES: dict[str, dict[str, Any]] = {
    "emotional": {"target_seconds": 35, "min_seconds": 30, "max_seconds": 45, "min_words": 75, "max_words": 105, "min_shots": 10, "max_shots": 14},
    "suspense": {"target_seconds": 35, "min_seconds": 30, "max_seconds": 45, "min_words": 75, "max_words": 110, "min_shots": 10, "max_shots": 14},
    "twist": {"target_seconds": 25, "min_seconds": 20, "max_seconds": 30, "min_words": 52, "max_words": 78, "min_shots": 7, "max_shots": 10},
    "comedy": {"target_seconds": 25, "min_seconds": 20, "max_seconds": 30, "min_words": 52, "max_words": 78, "min_shots": 7, "max_shots": 10},
    "poetry": {"target_seconds": 22, "min_seconds": 18, "max_seconds": 26, "min_words": 32, "max_words": 60, "min_shots": 7, "max_shots": 9},
    "insight": {"target_seconds": 28, "min_seconds": 20, "max_seconds": 35, "min_words": 50, "max_words": 82, "min_shots": 8, "max_shots": 12},
}

STORY_TYPE_ALIASES = {
    "family": "emotional",
    "family_emotion": "emotional",
    "relationship": "emotional",
    "emotional_story": "emotional",
    "micro_drama": "emotional",
    "thriller": "suspense",
    "mystery": "suspense",
    "suspense_twist": "suspense",
    "plot_twist": "twist",
    "funny": "comedy",
    "humour": "comedy",
    "humor": "comedy",
    "shayari": "poetry",
    "micro_poetry": "poetry",
    "micro_story": "emotional",
    "everyday_insight": "insight",
}


def normalise_story_type(value: Any) -> str:
    raw = str(value or "emotional").strip().lower().replace("-", "_").replace(" ", "_")
    raw = STORY_TYPE_ALIASES.get(raw, raw)
    if raw not in STORY_POLICIES:
        raise ValueError(f"Unsupported story_type {raw!r}; choose one of {', '.join(STORY_POLICIES)}.")
    return raw


def infer_story_type(concept: dict[str, Any]) -> str:
    explicit = concept.get("story_type")
    if explicit:
        return normalise_story_type(explicit)
    pillar = str(concept.get("pillar") or "").strip().lower()
    if pillar == "everyday_insight":
        return "insight"
    if pillar == "cinematic_moment":
        text = " ".join(str(concept.get(k) or "") for k in ("title", "theme", "hook")).lower()
        if any(token in text for token in ("raaz", "suspense", "twist", "mystery", "secret")):
            return "suspense"
    return "emotional"


def policy_for(concept_or_type: dict[str, Any] | str) -> dict[str, Any]:
    story_type = infer_story_type(concept_or_type) if isinstance(concept_or_type, dict) else normalise_story_type(concept_or_type)
    return {"story_type": story_type, **STORY_POLICIES[story_type]}


def spoken_word_count(concept: dict[str, Any]) -> int:
    words = 0
    for beat in concept.get("beats", []):
        segments = beat.get("speech_segments")
        if isinstance(segments, list):
            words += sum(len(str(segment.get("text") or "").split()) for segment in segments if isinstance(segment, dict))
        else:
            words += len(str(beat.get("voiceover") or "").split())
    return words


def validate_screenplay_length(concept: dict[str, Any]) -> dict[str, Any]:
    story_type = infer_story_type(concept)
    policy = policy_for(story_type)
    count = spoken_word_count(concept)
    if not policy["min_words"] <= count <= policy["max_words"]:
        raise ValueError(
            f"{story_type} screenplay has {count} spoken words; expected "
            f"{policy['min_words']}–{policy['max_words']} for its duration class. "
            "Rewrite the complete story; never truncate dialogue."
        )
    concept["story_type"] = story_type
    concept["duration_policy"] = {
        **policy,
        "word_count": count,
        "duration_source": "measured_tts_wav_after_voice_generation",
        "duration_is_adaptive": True,
    }
    return concept["duration_policy"]


def validate_measured_duration(total_seconds: float, story_type: str) -> dict[str, Any]:
    if isinstance(total_seconds, bool) or not isinstance(total_seconds, (int, float)) or not math.isfinite(float(total_seconds)):
        raise ValueError("Measured Reel duration must be a finite number.")
    policy = policy_for(story_type)
    duration = float(total_seconds)
    if not policy["min_seconds"] <= duration <= policy["max_seconds"]:
        raise ValueError(
            f"Measured {policy['story_type']} audio is {duration:.2f}s; allowed range is "
            f"{policy['min_seconds']}–{policy['max_seconds']}s. Revise the story or voice direction; "
            "do not speed up, trim or pad dialogue to force a duration."
        )
    return {
        "story_type": policy["story_type"],
        "target_seconds": policy["target_seconds"],
        "measured_seconds": round(duration, 3),
        "minimum_seconds": policy["min_seconds"],
        "maximum_seconds": policy["max_seconds"],
        "duration_source": "sum_of_measured_beat_wav_timelines",
        "dialogue_truncated": False,
    }


def _allocate_counts(durations: list[float], target_count: int) -> list[int]:
    counts = [1] * len(durations)
    remaining = target_count - len(durations)
    if remaining <= 0:
        return counts
    total = sum(durations)
    quotas = [remaining * duration / total for duration in durations]
    floors = [int(math.floor(value)) for value in quotas]
    counts = [base + extra for base, extra in zip(counts, floors)]
    left = remaining - sum(floors)
    order = sorted(range(len(durations)), key=lambda i: (quotas[i] - floors[i], durations[i]), reverse=True)
    for index in order[:left]:
        counts[index] += 1
    return counts


def build_editorial_shot_plan(beat_durations: list[float], story_type: str) -> dict[str, Any]:
    """Allocate fast editorial coverage over the six approved source beats.

    Each generated Wan clip remains one source beat. Wide/medium/close cut points are
    made in post, so editorial shot count increases without multiplying GPU generations.
    """
    policy = policy_for(story_type)
    if not isinstance(beat_durations, list) or len(beat_durations) != 6:
        raise ValueError("Editorial planning requires exactly six measured narrative-beat durations.")
    durations = [float(item) for item in beat_durations]
    if any(not math.isfinite(item) or item < 2.5 for item in durations):
        raise ValueError("Every source beat must have a finite measured duration of at least 2.5 seconds.")
    total = sum(durations)
    measured = validate_measured_duration(total, policy["story_type"])
    shot_target = int(round(total / 2.5))
    shot_target = max(policy["min_shots"], min(policy["max_shots"], shot_target))
    counts = _allocate_counts(durations, shot_target)

    # Keep editorial cuts readable: if a beat is too short for its allocated cuts,
    # move that cut to the longest beat rather than creating sub-1.5s flash edits.
    changed = True
    while changed:
        changed = False
        for index, duration in enumerate(durations):
            if counts[index] > 1 and duration / counts[index] < 1.5:
                counts[index] -= 1
                receiver = max(range(len(durations)), key=lambda i: durations[i] / counts[i])
                counts[receiver] += 1
                changed = True
                break

    if sum(counts) > policy["max_shots"]:
        raise ValueError("Editorial shot allocation exceeds the genre's maximum.")
    if any(duration / count < 1.45 or duration / count > 4.8 for duration, count in zip(durations, counts)):
        raise ValueError("Measured beat timing cannot produce readable editorial shots; revise storyboard timing.")

    beat_roles = ("hook", "context", "conflict", "escalation", "turn", "payoff")
    total_shots = sum(counts)
    hero_count = max(1, int(round(total_shots * 0.25)))
    if hero_count == 1:
        hero_indices = {total_shots - 1}
    else:
        hero_indices = {
            int(round(index * (total_shots - 1) / (hero_count - 1)))
            for index in range(hero_count)
        }
    shots: list[dict[str, Any]] = []
    reel_cursor = 0.0
    shot_number = 0
    for beat_index, (duration, count) in enumerate(zip(durations, counts), start=1):
        cut_duration = duration / count
        local_cursor = 0.0
        for cut_index in range(count):
            shot_number += 1
            role = beat_roles[beat_index - 1]
            if count > 1:
                subrole = ("establishing", "reaction", "detail")[min(cut_index, 2)]
            else:
                subrole = "continuous"
            zoom = 1.0 if cut_index == 0 else (1.10 if cut_index == 1 else 1.14)
            source = "hero_video" if shot_number - 1 in hero_indices else "depth_parallax"
            start = local_cursor
            end = duration if cut_index == count - 1 else (cut_index + 1) * cut_duration
            shots.append({
                "shot_number": shot_number,
                "beat_index": beat_index,
                "shot_in_beat": cut_index + 1,
                "story_role": role,
                "coverage": subrole,
                "source": source,
                "start_seconds": round(start, 4),
                "end_seconds": round(end, 4),
                "duration_seconds": round(end - start, 4),
                "zoom": zoom,
                "crop_x": 0.5,
                "crop_y": 0.5,
            })
            local_cursor = end
        reel_cursor += duration

    if abs(sum(item["duration_seconds"] for item in shots) - total) > 0.02:
        raise RuntimeError("Editorial shot plan does not preserve the complete measured audio duration.")
    return {
        "schema_version": 1,
        "visual_pipeline": "hybrid_25d_motion_comic_v1",
        "story_type": policy["story_type"],
        "measured_duration_seconds": measured["measured_seconds"],
        "source_beat_count": len(beat_durations),
        "editorial_shot_count": len(shots),
        "hero_video_shot_count": sum(1 for shot in shots if shot["source"] == "hero_video"),
        "depth_parallax_shot_count": sum(1 for shot in shots if shot["source"] == "depth_parallax"),
        "gpu_generation_count": len(beat_durations),
        "gpu_generation_saving_claim": False,
        "shots": shots,
        "duration_source": "measured_tts_wav_before_gpu",
    }


def shots_for_beat(plan: dict[str, Any], beat_index: int) -> list[dict[str, Any]]:
    selected = [dict(item) for item in plan.get("shots", []) if int(item.get("beat_index", 0)) == beat_index]
    if not selected:
        raise ValueError(f"Editorial shot plan has no shots for beat {beat_index}.")
    return selected


def retime_beat_shots(shots: list[dict[str, Any]], target_duration: float) -> list[dict[str, Any]]:
    """Scale sub-shot boundaries to the final mux duration without dropping any audio."""
    if not shots or not math.isfinite(float(target_duration)) or target_duration <= 0:
        raise ValueError("Cannot retime an empty shot list or a non-positive duration.")
    source_duration = float(shots[-1]["end_seconds"])
    if source_duration <= 0:
        raise ValueError("Editorial shot source duration must be positive.")
    ratio = float(target_duration) / source_duration
    result = []
    cursor = 0.0
    for index, raw in enumerate(shots):
        item = dict(raw)
        next_end = target_duration if index == len(shots) - 1 else float(raw["end_seconds"]) * ratio
        item["start_seconds"] = round(cursor, 4)
        item["end_seconds"] = round(next_end, 4)
        item["duration_seconds"] = round(next_end - cursor, 4)
        cursor = next_end
        result.append(item)
    if abs(cursor - target_duration) > 0.01:
        raise RuntimeError("Retimed editorial shots do not cover the full scene.")
    return result
