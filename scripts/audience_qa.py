"""Evidence-backed synthetic audience simulation and real human review records.

Synthetic reviewers are simulated decision profiles, never represented as real people.
No view/reach prediction is produced. Real human votes are stored separately.
"""
from __future__ import annotations

import hashlib
import math
import os
import random
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_SIMULATED_REVIEWERS = 10_000
EDITORIAL_DIMENSIONS = (
    "hook_clarity", "story_progression", "payoff", "originality", "share_value",
    "human_specificity", "emotional_resonance", "illustrated_visual_quality",
    "creative_contribution_beyond_stock", "continuity_coherence", "voiceover_rhythm",
    "readability", "platform_safety",
)
HUMAN_DIMENSIONS = (
    "hook", "story", "emotion", "visual", "audio", "ending", "clarity", "share_value",
)
COHORTS = (
    ("casual_scrollers", 0.20, ("hook_clarity", "illustrated_visual_quality", "readability")),
    ("young_short_form", 0.15, ("hook_clarity", "originality", "voiceover_rhythm")),
    ("emotion_seekers", 0.15, ("emotional_resonance", "human_specificity", "payoff")),
    ("story_focused", 0.12, ("story_progression", "payoff", "continuity_coherence")),
    ("poetry_and_language", 0.10, ("readability", "voiceover_rhythm", "emotional_resonance")),
    ("skeptical_viewers", 0.10, ("originality", "human_specificity", "platform_safety")),
    ("low_attention_viewers", 0.10, ("hook_clarity", "story_progression", "voiceover_rhythm")),
    ("mature_general", 0.08, ("story_progression", "human_specificity", "readability")),
)


def _valid_score(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and 1.0 <= float(value) <= 5.0
    )


def collect_evidence(concept: dict[str, Any], build: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    """Collect only scores already present in the editorial/VLM QA artifacts."""
    review = concept.get("editorial_review", {})
    raw_scores = review.get("scores", {}) if isinstance(review, dict) else {}
    readiness = quality.get("director_10k_readiness", {})
    readiness_scores = readiness.get("dimensions", {}) if isinstance(readiness, dict) else {}
    technical = build.get("technical", {}) if isinstance(build, dict) else {}
    visual = technical.get("rendered_frame_visual_qa", {}) if isinstance(technical, dict) else {}
    visual_scores = visual.get("scores", {}) if isinstance(visual, dict) else {}

    scores: dict[str, float] = {}
    provenance: dict[str, str] = {}
    for key in EDITORIAL_DIMENSIONS:
        candidate = raw_scores.get(key)
        source = "editorial_review.scores"
        if not _valid_score(candidate):
            candidate = readiness_scores.get(key)
            source = "director_10k_readiness.dimensions"
        if _valid_score(candidate):
            scores[key] = round(float(candidate), 3)
            provenance[key] = source

    # The VLM frame scorecard is a separate evidence source. It supplements, but
    # never silently replaces, the editorial critic's story/audience judgements.
    visual_map = {
        "frame_text_legibility": "text_legibility",
        "frame_visual_quality": "visual_quality",
        "frame_character_continuity": "character_continuity",
        "frame_story_visual_match": "story_visual_match",
        "frame_anatomy_integrity": "anatomy_integrity",
        "frame_safe_composition": "safe_composition",
        "frame_devanagari_rendering": "devanagari_rendering",
        "frame_metadata_text_cleanliness": "metadata_text_cleanliness",
    }
    for target, source_key in visual_map.items():
        value = visual_scores.get(source_key)
        if _valid_score(value):
            scores[target] = round(float(value), 3)
            provenance[target] = "rendered_frame_visual_qa.scores"

    motion = visual.get("full_video_motion_diagnostics", {}) if isinstance(visual, dict) else {}
    ocr = visual.get("metadata_ocr_qa", {}) if isinstance(visual, dict) else {}
    technical_gates = {
        "technical_checks_passed": technical.get("technical_checks_passed") is True,
        "visual_review_completed": visual.get("status") == "reviewed",
        "motion_scan_passed": isinstance(motion, dict) and motion.get("status") == "passed"
        and motion.get("full_video_scanned") is True,
        "metadata_ocr_passed": isinstance(ocr, dict) and ocr.get("status") == "passed",
    }
    return {
        "scores": scores,
        "provenance": provenance,
        "technical_gates": technical_gates,
        "evidence_count": len(scores),
        "evidence_coverage_percent": round(len(scores) / (len(EDITORIAL_DIMENSIONS) + len(visual_map)) * 100, 1),
    }


def _allocate_counts(sample_size: int) -> list[tuple[str, int, tuple[str, ...]]]:
    exact = [sample_size * share for _, share, _ in COHORTS]
    counts = [int(value) for value in exact]
    remainder = sample_size - sum(counts)
    order = sorted(range(len(COHORTS)), key=lambda i: exact[i] - counts[i], reverse=True)
    for index in order[:remainder]:
        counts[index] += 1
    return [(COHORTS[i][0], counts[i], COHORTS[i][2]) for i in range(len(COHORTS))]


def generate_simulated_audience_report(
    reel_id: str,
    concept: dict[str, Any],
    build: dict[str, Any],
    quality: dict[str, Any],
    sample_size: int = DEFAULT_SIMULATED_REVIEWERS,
    seed: int | None = None,
) -> dict[str, Any]:
    """Run a deterministic, evidence-conditioned audience simulation.

    The synthetic panel creates preference-weighted reactions with bounded variation.
    Its intent rates are hypotheses only, not measured people or predicted platform reach.
    """
    if not isinstance(sample_size, int) or isinstance(sample_size, bool) or not 1 <= sample_size <= 100_000:
        raise ValueError("sample_size must be an integer from 1 to 100000.")
    evidence = collect_evidence(concept, build, quality)
    scores = evidence["scores"]
    if not scores:
        return {
            "schema_version": SCHEMA_VERSION,
            "engine": "bsk_human_reality_qa_v1",
            "reel_id": str(reel_id),
            "status": "insufficient_evidence",
            "simulation_type": "synthetic_not_human",
            "simulated_review_count": 0,
            "requested_sample_size": sample_size,
            "evidence": evidence,
            "reason": "No valid 1–5 editorial or rendered-frame QA scores were supplied.",
            "real_human_reviews": {"count": 0, "status": "not_received"},
            "view_prediction": None,
        }

    seed_material = str(seed) if seed is not None else str(reel_id) + "|" + "|".join(
        f"{key}:{scores[key]:.3f}" for key in sorted(scores)
    )
    seed_int = int(hashlib.sha256(seed_material.encode("utf-8")).hexdigest()[:16], 16)
    rng = random.Random(seed_int)

    # Segment-specific preferences are deliberately modest; they change weighting,
    # not the underlying evidence. Missing dimensions are never imputed.
    overall_totals = {key: 0.0 for key in scores}
    overall_counts = {key: 0 for key in scores}
    cohort_reports: list[dict[str, Any]] = []
    outcomes = {"hook_interest": 0, "watch_intent": 0, "rewatch_intent": 0, "share_intent": 0}
    total_score_sum = 0.0
    total_score_sq = 0.0

    for cohort_name, count, preferences in _allocate_counts(sample_size):
        if count == 0:
            continue
        cohort_total = 0.0
        cohort_outcomes = {key: 0 for key in outcomes}
        for _ in range(count):
            sampled: dict[str, float] = {}
            for key, base in scores.items():
                # Individual simulated tastes vary around the source evidence.
                jitter = rng.gauss(0.0, 0.42)
                value = max(1.0, min(5.0, base + jitter))
                sampled[key] = value
                overall_totals[key] += value
                overall_counts[key] += 1

            preferred = [key for key in preferences if key in sampled]
            weights = {key: 1.35 if key in preferred else 1.0 for key in sampled}
            composite = sum(sampled[key] * weights[key] for key in sampled) / sum(weights.values())
            hook_values = [sampled[k] for k in ("hook_clarity",) if k in sampled]
            story_values = [sampled[k] for k in ("story_progression", "payoff") if k in sampled]
            emotion_values = [sampled[k] for k in ("emotional_resonance", "human_specificity") if k in sampled]
            share_values = [sampled[k] for k in ("share_value", "originality", "emotional_resonance") if k in sampled]
            rhythm_values = [sampled[k] for k in ("voiceover_rhythm", "readability") if k in sampled]

            def mean(values: list[float], fallback: float) -> float:
                return sum(values) / len(values) if values else fallback

            hook_interest = mean(hook_values, composite) >= 3.25
            watch_intent = mean(story_values + emotion_values + rhythm_values, composite) >= 3.35
            rewatch_intent = mean(emotion_values + [sampled[k] for k in ("payoff", "originality") if k in sampled], composite) >= 3.55
            share_intent = mean(share_values, composite) >= 3.65
            cohort_outcomes["hook_interest"] += int(hook_interest)
            cohort_outcomes["watch_intent"] += int(watch_intent)
            cohort_outcomes["rewatch_intent"] += int(rewatch_intent)
            cohort_outcomes["share_intent"] += int(share_intent)
            cohort_total += composite
            total_score_sum += composite
            total_score_sq += composite * composite
            for key, value in (
                ("hook_interest", hook_interest), ("watch_intent", watch_intent),
                ("rewatch_intent", rewatch_intent), ("share_intent", share_intent),
            ):
                outcomes[key] += int(value)

        cohort_reports.append({
            "segment": cohort_name,
            "simulated_profiles": count,
            "mean_editorial_fit_1_to_5": round(cohort_total / count, 3),
            "modeled_intent_percent": {
                key: round(value / count * 100, 1) for key, value in cohort_outcomes.items()
            },
        })

    dimension_means = {
        key: round(overall_totals[key] / max(overall_counts[key], 1), 3)
        for key in scores
    }
    ranked = sorted(dimension_means.items(), key=lambda item: item[1])
    score_mean = total_score_sum / sample_size
    variance = max(0.0, total_score_sq / sample_size - score_mean * score_mean)
    strongest = [{"dimension": key, "mean_score_1_to_5": value} for key, value in ranked[-3:][::-1]]
    weakest = [{"dimension": key, "mean_score_1_to_5": value} for key, value in ranked[:3]]
    return {
        "schema_version": SCHEMA_VERSION,
        "engine": "bsk_human_reality_qa_v1",
        "reel_id": str(reel_id),
        "status": "completed" if evidence["evidence_count"] >= 5 else "completed_low_evidence",
        "simulation_type": "synthetic_not_human",
        "simulated_review_count": sample_size,
        "requested_sample_size": sample_size,
        "seed_sha256": hashlib.sha256(seed_material.encode("utf-8")).hexdigest(),
        "evidence": evidence,
        "modeled_audience_fit_score_0_to_100": round(score_mean * 20, 1),
        "modeled_score_stddev_1_to_5": round(math.sqrt(variance), 3),
        "modeled_intent_percent": {
            key: round(value / sample_size * 100, 1) for key, value in outcomes.items()
        },
        "dimension_means_1_to_5": dimension_means,
        "strongest_evidence_dimensions": strongest,
        "weakest_evidence_dimensions": weakest,
        "cohort_results": cohort_reports,
        "real_human_reviews": {"count": 0, "status": "not_received"},
        "view_prediction": None,
        "limitations": [
            "These are synthetic preference simulations, not 10,000 real people.",
            "Intent percentages are not watch-time, virality, reach, or view predictions.",
            "Results are constrained by the supplied editorial/VLM scores and inherit their errors.",
            "A full human playback and owner decision remain mandatory.",
        ],
    }


def record_human_review(
    store: dict[str, Any],
    reel_id: str,
    reviewer_id: str,
    ratings: dict[str, Any],
    verdict: str,
    notes: str = "",
    update_id: int | None = None,
    hash_salt: str | None = None,
) -> dict[str, Any]:
    """Save one independent real-person review; one vote per reviewer per Reel."""
    if not str(reel_id).strip() or len(str(reel_id)) > 120:
        raise ValueError("A valid reel_id is required.")
    if not str(reviewer_id).strip():
        raise ValueError("A configured reviewer identity is required.")
    if verdict not in {"pass", "revise", "reject"}:
        raise ValueError("verdict must be pass, revise, or reject.")
    if not isinstance(ratings, dict) or set(ratings) != set(HUMAN_DIMENSIONS):
        raise ValueError("All eight human rating fields are required: " + ", ".join(HUMAN_DIMENSIONS))
    invalid = [key for key, value in ratings.items() if not _valid_score(value)]
    if invalid:
        raise ValueError("Ratings must be numeric values from 1 to 5: " + ", ".join(invalid))
    salt = hash_salt if hash_salt is not None else os.getenv("BSK_REVIEWER_HASH_SALT", "bsk-human-review-v1")
    reviewer_hash = hashlib.sha256((salt + ":" + str(reviewer_id)).encode("utf-8")).hexdigest()
    records = store.setdefault("reviews", [])
    if not isinstance(records, list):
        raise ValueError("Human review store has an invalid reviews collection.")
    if any(row.get("reel_id") == reel_id and row.get("reviewer_hash") == reviewer_hash for row in records):
        return {"saved": False, "duplicate": True, "reviewer_hash": reviewer_hash}
    record = {
        "reel_id": str(reel_id),
        "reviewer_hash": reviewer_hash,
        "ratings": {key: round(float(ratings[key]), 2) for key in HUMAN_DIMENSIONS},
        "verdict": verdict,
        "notes": str(notes or "").strip()[:800],
        "received_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "telegram_update_id": update_id,
        "source": "allowlisted_telegram_human_reviewer",
    }
    records.append(record)
    return {"saved": True, "duplicate": False, "reviewer_hash": reviewer_hash}


def summarize_human_reviews(
    store: dict[str, Any], reel_id: str, minimum_responses: int = 3
) -> dict[str, Any]:
    if not isinstance(minimum_responses, int) or isinstance(minimum_responses, bool) or minimum_responses < 1:
        raise ValueError("minimum_responses must be a positive integer.")
    rows = [
        row for row in store.get("reviews", [])
        if isinstance(row, dict) and row.get("reel_id") == reel_id
    ]
    averages: dict[str, float] = {}
    for key in HUMAN_DIMENSIONS:
        values = [
            float(row["ratings"][key]) for row in rows
            if isinstance(row.get("ratings"), dict) and _valid_score(row["ratings"].get(key))
        ]
        if values:
            averages[key] = round(sum(values) / len(values), 2)
    verdict_counts = {
        verdict: sum(1 for row in rows if row.get("verdict") == verdict)
        for verdict in ("pass", "revise", "reject")
    }
    return {
        "count": len(rows),
        "minimum_responses": minimum_responses,
        "status": "sufficient" if len(rows) >= minimum_responses else "pending",
        "dimension_averages_1_to_5": averages,
        "verdict_counts": verdict_counts,
        "review_source": "real_allowlisted_human_telegram_reviews",
    }
