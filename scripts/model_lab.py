#!/usr/bin/env python3
"""Offline model qualification helper; never downloads models or calls paid APIs."""
from __future__ import annotations
import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / 'data' / 'model_lab' / 'standard_prompts_v1.json'
CANDIDATES = {
    'hunyuanvideo-1.5': {'kind': 'video', 'production_status': 'not_qualified', 'track': 'T2V 480p 50-step first; compare same prompts against Wan. Test 720p separately. Step-distilled 8/12-step checkpoint is 480p I2V only.'},
    'flux.1-schnell': {'kind': 'image', 'production_status': 'not_qualified', 'track': 'Still images, covers and keyframes only; not a video replacement.'},
    'indic-speak': {'kind': 'tts', 'production_status': 'not_qualified', 'track': 'Local Hindi TTS; gated weights and upstream licence conditions must be accepted/reviewed before test.'},
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def template(candidate: str) -> dict:
    if candidate not in CANDIDATES:
        raise ValueError(f'Unknown candidate {candidate!r}; choose one of: {", ".join(CANDIDATES)}')
    prompts = load_json(PROMPTS)
    kind = CANDIDATES[candidate]['kind']
    samples = prompts['video_prompts'] if kind == 'video' else prompts['image_prompts'] if kind == 'image' else prompts['tts_lines']
    metrics = {
        'video': ['photorealism', 'motion_stability', 'anatomy_integrity', 'prompt_adherence', 'scene_coherence'],
        'image': ['photorealism', 'anatomy_integrity', 'prompt_fidelity', 'cover_composition', 'lighting_quality'],
        'tts': ['intelligibility', 'hindi_pronunciation', 'naturalness', 'emotional_prosody', 'speaker_consistency'],
    }[kind]
    return {
        'schema_version': 1, 'benchmark_id': prompts['benchmark_id'], 'candidate': candidate,
        'kind': kind, 'baseline': 'Wan2.2-TI2V-5B' if kind == 'video' else 'current-production-baseline',
        'environment': {'gpu_name': '', 'gpu_vram_gb': None, 'system_ram_gb': None, 'runtime_minutes': None, 'peak_vram_gb': None, 'model_download_gb': None, 'settings': {}},
        'rights': {'weights_license_reviewed': False, 'upstream_components_reviewed': False, 'commercial_use_confirmed': False, 'attribution_recorded': False},
        'human_review': {'all_samples_reviewed': False, 'reviewer_notes': ''},
        'samples': [{
            'id': sample['id'], 'prompt_or_text': sample['prompt'] if 'prompt' in sample else sample['text'],
            'scores_1_to_5': {metric: None for metric in metrics},
            'baseline_scores_1_to_5': {metric: None for metric in metrics},
            'runtime_seconds': None, 'baseline_runtime_seconds': None,
            'catastrophic_defect': False, 'notes': ''
        } for sample in samples],
        'decision': {'status': 'not_qualified', 'score': None, 'reason': 'Complete every sample and verify rights before scoring.'}
    }


def score_submission(data: dict) -> dict:
    candidate = str(data.get('candidate', ''))
    if candidate not in CANDIDATES:
        raise ValueError('Candidate is not in the controlled candidate registry.')
    samples = data.get('samples')
    if not isinstance(samples, list) or not samples:
        raise ValueError('Submission has no samples.')
    score_rows = []
    baseline_rows = []
    runtimes = []
    baseline_runtimes = []
    for sample in samples:
        metrics = sample.get('scores_1_to_5', {})
        if not metrics or any(not isinstance(v, (int, float)) or not 1 <= float(v) <= 5 for v in metrics.values()):
            raise ValueError(f"Sample {sample.get('id')} has missing or invalid 1-5 scores.")
        baseline_metrics = sample.get('baseline_scores_1_to_5', {})
        if set(baseline_metrics) != set(metrics) or any(not isinstance(v, (int, float)) or not 1 <= float(v) <= 5 for v in baseline_metrics.values()):
            raise ValueError(f"Sample {sample.get('id')} has missing or invalid baseline scores.")
        score_rows.append(statistics.mean(float(v) for v in metrics.values()))
        baseline_rows.append(statistics.mean(float(v) for v in baseline_metrics.values()))
        baseline_runtime = sample.get('baseline_runtime_seconds')
        if isinstance(baseline_runtime, (int, float)) and baseline_runtime > 0:
            baseline_runtimes.append(float(baseline_runtime))
        else:
            raise ValueError(f"Sample {sample.get('id')} has no positive baseline_runtime_seconds.")
        runtime = sample.get('runtime_seconds')
        if isinstance(runtime, (int, float)) and runtime > 0:
            runtimes.append(float(runtime))
        else:
            raise ValueError(f"Sample {sample.get('id')} has no positive runtime_seconds.")
    rights = data.get('rights', {})
    rights_ok = all(rights.get(k) is True for k in ('weights_license_reviewed', 'upstream_components_reviewed', 'commercial_use_confirmed', 'attribution_recorded'))
    human_ok = data.get('human_review', {}).get('all_samples_reviewed') is True
    catastrophic = any(bool(s.get('catastrophic_defect')) for s in samples)
    success_rate = sum(1 for s in samples if s.get('catastrophic_defect') is False) / len(samples)
    score = round(statistics.mean(score_rows), 3)
    # Strict promotion: complete standard pack, all samples reviewed, all rights confirmed, >=90% valid samples, no catastrophic defect, high quality.
    baseline_score = round(statistics.mean(baseline_rows), 3)
    uplift = round(score - baseline_score, 3)
    median_runtime = statistics.median(runtimes)
    baseline_median_runtime = statistics.median(baseline_runtimes)
    runtime_ratio = round(median_runtime / baseline_median_runtime, 3)
    runtime_ok = runtime_ratio <= 1.25 or uplift >= 0.50
    ready = len(samples) >= 10 and rights_ok and human_ok and success_rate >= 0.90 and not catastrophic and score >= 4.20 and uplift >= 0.25 and runtime_ok
    result = dict(data)
    result['decision'] = {
        'status': 'eligible_for_production_trial' if ready else 'not_qualified',
        'score': score, 'baseline_score': baseline_score, 'uplift_vs_baseline': uplift,
        'success_rate': round(success_rate, 3),
        'median_runtime_seconds': round(median_runtime, 2),
        'baseline_median_runtime_seconds': round(baseline_median_runtime, 2),
        'runtime_ratio_vs_baseline': runtime_ratio,
        'reason': ('Meets lab gate; still requires 3 successful real production shadow runs before promotion.' if ready else 'Does not pass all gates: require >=10 paired samples, complete rights review, full human sample review, >=90% clean samples, candidate score >=4.20/5, uplift >=0.25, and runtime <=1.25x baseline unless quality uplift >=0.50.')
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description='BINA SHOR KE offline candidate qualification lab (no model downloads).')
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('template'); make.add_argument('--candidate', choices=sorted(CANDIDATES), required=True); make.add_argument('--output', required=True)
    score = sub.add_parser('score'); score.add_argument('--submission', required=True); score.add_argument('--output', default='')
    args = parser.parse_args()
    try:
        if args.command == 'template':
            result = template(args.candidate)
            dest = Path(args.output); dest.parent.mkdir(parents=True, exist_ok=True); dest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'Created empty benchmark scorecard: {dest}. Fill it only after real local tests; this command does not download or run the model.')
            return 0
        data = score_submission(load_json(Path(args.submission)))
        output = Path(args.output) if args.output else Path(args.submission).with_name(Path(args.submission).stem + '_scored.json')
        output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(data['decision'], ensure_ascii=False, indent=2))
        print(f'Saved scorecard: {output}')
        return 0
    except Exception as exc:
        print(f'MODEL LAB ERROR: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
