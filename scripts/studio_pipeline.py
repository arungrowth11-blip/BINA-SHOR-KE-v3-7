#!/usr/bin/env python3
"""Orchestrate BINA SHOR KE: editorial planning -> Kaggle Wan GPU -> final QA -> Telegram.
No Facebook publishing; paid fallbacks are intentionally disabled.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import statistics
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
OUT = ROOT / 'output'
PENDING = DATA / 'pending_gpu_job.json'
TOOLCHAIN_LOCK = DATA / 'toolchain_lock.json'
IMAGE_TOOLCHAIN_LOCK = DATA / 'image_toolchain_lock.json'
TZ = ZoneInfo('Asia/Kolkata')
sys.path.insert(0, str(ROOT / 'scripts'))
import producer  # noqa: E402
import voice_first  # noqa: E402
import character_library  # noqa: E402

DEFAULT_KAGGLE_SLUG = 'bina-shor-ke-studio-video'

def configured_kaggle_slug(value=None) -> str:
    raw = os.getenv('KAGGLE_KERNEL_SLUG') if value is None else value
    return str(raw or '').strip().lower() or DEFAULT_KAGGLE_SLUG

KAGGLE_SLUG = configured_kaggle_slug()

# Invoke Kaggle through the exact interpreter running this pipeline. This avoids
# PATH/shebang drift between pip's Python and a stale global `kaggle` launcher.
KAGGLE_CLI_BOOTSTRAP = (
    "import sys; from kaggle.cli import main; "
    "sys.argv = ['kaggle', *sys.argv[1:]]; main()"
)


def kaggle_cli_command(*arguments: str) -> list[str]:
    return [sys.executable, '-c', KAGGLE_CLI_BOOTSTRAP, *arguments]


ACTIVE_GPU_STATES = {
    'dispatching', 'dispatch_unknown', 'gpu_running', 'gpu_complete',
    'finalizing', 'finalize_failed', 'gpu_checkpoint_saved',
}


def terminal_finalization_qa_reason(pending: dict) -> str:
    """Return a reason only for the known, non-retryable end-hold QA rejection."""
    if pending.get('status') != 'finalize_failed':
        return ''
    error = str(pending.get('finalize_error') or '').strip()
    if (
        'AI scene needs' in error
        and 'end hold' in error
        and 'above the 1.20s quality limit' in error
    ):
        return error
    return ''


def archive_completed_qa_rejection(pending: dict, reason: str) -> dict:
    """Archive a terminal QA-rejected batch only after Kaggle confirms its GPU run is COMPLETE.

    Unknown/transient finalization errors are deliberately not eligible. This preserves the
    retry-finalize path for recoverable failures and never releases an active/ambiguous GPU job.
    """
    if pending.get('status') != 'finalize_failed' or not reason:
        raise RuntimeError('Only a classified terminal finalization QA rejection can be archived.')
    job_id = str(pending.get('job_id') or '').strip()
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', job_id):
        raise RuntimeError('Cannot archive terminal QA batch: job_id is missing or invalid.')
    kernel_id = str(pending.get('kaggle_kernel_id') or '').strip()
    if not kernel_id or '/' not in kernel_id:
        raise RuntimeError('Cannot archive terminal QA batch: saved Kaggle kernel identity is missing.')
    manifest_reels = (pending.get('manifest') or {}).get('reels')
    if not isinstance(manifest_reels, list) or not manifest_reels:
        raise RuntimeError('Cannot archive terminal QA batch: saved manifest has no Reel list.')
    if any(not isinstance(reel, dict) or len(reel.get('beats') or []) != 6 for reel in manifest_reels):
        raise RuntimeError('Cannot archive terminal QA batch: manifest does not contain six scenes for every Reel.')

    remote_status, remote_output = kaggle_status(kernel_id)
    if remote_status != 'COMPLETE':
        detail = str(remote_output or '').strip()[-700:]
        raise RuntimeError(
            f'Old batch {job_id} is not proven terminal in Kaggle (status={remote_status}); '
            f'keeping the pending lock. Inspect the original Kaggle run before starting another GPU job. {detail}'
        )

    archive_dir = DATA / 'job_archive'
    archive_path = archive_dir / f'{job_id}.json'
    if archive_path.exists():
        existing = load_json(archive_path, {}) or {}
        if existing.get('job_id') != job_id or existing.get('status') != 'finalize_failed':
            raise RuntimeError(f'Archive path already contains a different record: {archive_path}')
    else:
        archived = json.loads(json.dumps(pending, ensure_ascii=False))
        archived['archive_metadata'] = {
            'archived_at_ist': datetime.now(TZ).isoformat(timespec='seconds'),
            'archive_reason': 'terminal_qa_rejection_after_completed_gpu_render',
            'final_qa_rejection_reason': reason,
            'kaggle_kernel_id': kernel_id,
            'verified_kaggle_status': remote_status,
            'verified_kaggle_output': str(remote_output or '')[-1200:],
        }
        write_json(archive_path, archived)

    pending['status'] = 'qa_rejected'
    pending['qa_rejection_reason'] = reason
    try:
        archive_location = archive_path.relative_to(ROOT).as_posix()
    except ValueError:
        archive_location = str(archive_path)
    pending['finalization_resolution'] = {
        'status': 'archived_terminal_qa_rejection',
        'resolved_at_ist': datetime.now(TZ).isoformat(timespec='seconds'),
        'archive_path': archive_location,
        'kaggle_kernel_id': kernel_id,
        'verified_kaggle_status': remote_status,
        'new_gpu_dispatch_required': False,
    }
    write_json(PENDING, pending)
    return pending


def log(msg: str):
    print(f"[{datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S %Z')}] {msg}", flush=True)


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def kaggle_kernel_id():
    username = os.getenv('KAGGLE_USERNAME', '').strip()
    key = os.getenv('KAGGLE_KEY', '').strip()
    if not username or not key:
        raise RuntimeError('Required GitHub Secrets missing: KAGGLE_USERNAME and/or KAGGLE_KEY. No cloud GPU job was started.')
    return f"{username}/{KAGGLE_SLUG}"


def configure_kaggle_cli():
    if not os.getenv('KAGGLE_USERNAME') or not os.getenv('KAGGLE_KEY'):
        raise RuntimeError('KAGGLE_USERNAME/KAGGLE_KEY are required for the GPU dispatch/poll stage.')
    home = Path.home() / '.kaggle'
    home.mkdir(parents=True, exist_ok=True)
    (home / 'kaggle.json').write_text(json.dumps({
        'username': os.environ['KAGGLE_USERNAME'], 'key': os.environ['KAGGLE_KEY']
    }), encoding='utf-8')
    try:
        (home / 'kaggle.json').chmod(0o600)
    except OSError:
        pass


def alert_failure(message: str):
    try:
        producer.failure_alert(message[:2500])
    except Exception as exc:
        log(f'Failure alert could not be sent (check Telegram /start and secrets): {exc}')


def build_kaggle_kernel(manifest: dict):
    kernel_dir = ROOT / 'kaggle_kernel'
    if kernel_dir.exists():
        shutil.rmtree(kernel_dir)
    kernel_dir.mkdir(parents=True, exist_ok=True)
    template = (ROOT / 'scripts' / 'kaggle_gpu_runner.py').read_text(encoding='utf-8')
    # Encode the manifest exactly once as JSON text, then parse it in the worker.
    # The previous double-encoding produced a Python str, not the dict the worker expects.
    manifest_json = json.dumps(manifest, ensure_ascii=False, separators=(',', ':'))
    manifest_literal = f"json.loads({manifest_json!r})"
    # The source template contains exactly one placeholder, and no API secrets are embedded.
    if template.count('__MANIFEST_JSON__') != 1:
        raise RuntimeError('Kaggle worker manifest placeholder is missing or duplicated.')
    script = template.replace('__MANIFEST_JSON__', manifest_literal)
    (kernel_dir / 'studio_kaggle.py').write_text(script, encoding='utf-8')
    username = os.environ['KAGGLE_USERNAME'].strip()
    meta = {
        'id': f'{username}/{KAGGLE_SLUG}',
        'title': 'BINA SHOR KE — Private Cinematic Scene Worker',
        'code_file': 'studio_kaggle.py',
        'language': 'python',
        'kernel_type': 'script',
        'is_private': True,
        'enable_gpu': True,
        'enable_internet': True,
        'dataset_sources': [manifest['resume_dataset_id']] if manifest.get('resume_dataset_id') else [],
        'competition_sources': [],
        'kernel_sources': [],
    }
    write_json(kernel_dir / 'kernel-metadata.json', meta)
    # Quick syntax check before sending to Kaggle.
    check = subprocess.run([sys.executable, '-m', 'py_compile', str(kernel_dir / 'studio_kaggle.py')], text=True, capture_output=True)
    if check.returncode:
        raise RuntimeError('Generated Kaggle worker failed syntax check: ' + check.stderr[-2000:])
    return kernel_dir


def ensure_reel_qa_passed(build: dict) -> None:
    technical = build.get('technical', {}) if isinstance(build, dict) else {}
    if not isinstance(technical, dict) or technical.get('technical_checks_passed') is not True:
        raise RuntimeError('Final Reel technical QA did not pass; refusing Telegram delivery and weekly qualification.')
    visual = technical.get('rendered_frame_visual_qa')
    if not isinstance(visual, dict) or visual.get('status') != 'reviewed':
        status = visual.get('status', 'missing') if isinstance(visual, dict) else 'missing'
        raise RuntimeError(
            f'Rendered-frame visual QA is {status}; only a completed reviewed result can pass. '
            'A QA outage or incomplete scorecard is not a pass.'
        )
    if visual.get('critical_issue') is not False or visual.get('missing_required_scores'):
        raise RuntimeError('Rendered-frame visual QA is missing required scores or reports a critical issue.')
    motion = visual.get('full_video_motion_diagnostics')
    if not isinstance(motion, dict) or motion.get('status') != 'passed' or motion.get('full_video_scanned') is not True:
        status = motion.get('status', 'missing') if isinstance(motion, dict) else 'missing'
        raise RuntimeError(
            f'Full-video motion diagnostics are {status}; black/frozen-frame scan must complete and pass.'
        )
    ocr = visual.get('metadata_ocr_qa')
    if not isinstance(ocr, dict) or ocr.get('status') != 'passed':
        status = ocr.get('status', 'missing') if isinstance(ocr, dict) else 'missing'
        raise RuntimeError(
            f'On-screen metadata OCR is {status}; OCR must complete with zero forbidden prompt labels.'
        )

def ensure_complete_telegram_delivery(steps: dict) -> None:
    required = ('video', 'cover', 'message', 'publish_kit')
    if not isinstance(steps, dict) or not all(steps.get(step) is True for step in required):
        missing = [step for step in required if not isinstance(steps, dict) or steps.get(step) is not True]
        raise RuntimeError('Telegram delivery is incomplete; missing successful step(s): ' + ', '.join(missing))

def require_weekly_qualification(history: dict, saved_lock: dict) -> None:
    """Require an actually delivered, QA-passed, owner-approved one-Reel pilot."""
    qualification = history.get('one_reel_qualification') if isinstance(history, dict) else None
    required = (
        isinstance(qualification, dict)
        and qualification.get('status') == 'qualified'
        and qualification.get('qa_passed') is True
        and qualification.get('telegram_delivered') is True
        and qualification.get('owner_approved') is True
        and bool(qualification.get('reel_id'))
        and bool(qualification.get('approved_at_ist'))
    )
    if not required:
        raise RuntimeError(
            'Weekly 3-Reel production is locked. First complete one plan-one Reel, pass final QA, '
            'deliver the video/cover/review message/publish kit to Telegram, and send '
            '/approve title=Exact Reel Title. Then run Telegram Feedback Sync and retry plan-week.'
        )
    image_lock = load_json(IMAGE_TOOLCHAIN_LOCK, {}) or {}
    benchmark = image_lock.get('gpu_benchmark') if isinstance(image_lock, dict) else None
    if not isinstance(benchmark, dict) or benchmark.get('qualified') is not True:
        raise RuntimeError(
            'Weekly 3-Reel production is locked until the image-first FLUX + depth-parallax '
            'GPU benchmark qualifies. The old Wan benchmark is not valid evidence for the new renderer.'
        )
    estimated_hours = float(benchmark.get('estimated_3_reel_hours', 999))
    if estimated_hours > 8.0:
        raise RuntimeError(
            f'Weekly batch is not qualified for the Kaggle 12-hour session: conservative estimate is '
            f'{estimated_hours:.1f} hours for the image-first renderer. Keep one-Reel jobs only; no paid fallback will be used.'
        )


def prepare_voice_first_plan(concept: dict, reel_id: str) -> dict:
    """Generate and measure every character turn before spending any video-GPU time."""
    # Bind every generated cast to this Reel instance. Repeated story titles should not
    # accidentally reuse another Reel's saved character identity.
    concept['story_instance_id'] = reel_id
    voice_first.normalise_screenplay(concept)
    characters = concept.get('characters', [])
    if not characters:
        raise RuntimeError('Voice-first screenplay has no cast; refusing GPU dispatch.')
    # Character metadata is persisted only after the complete voice-first storyboard passes.
    with tempfile.TemporaryDirectory(prefix='bsk-voice-preflight-') as temp_root:
        temp_root = Path(temp_root)
        for beat_index, beat in enumerate(concept['beats'], start=1):
            segments = beat.get('speech_segments')
            if not isinstance(segments, list):
                raise RuntimeError(f'Beat {beat_index} has no structured speech_segments array.')
            measured = {}
            for line_index, segment in enumerate(segments, start=1):
                segment_id = str(segment.get('segment_id') or f'beat_{beat_index:02d}_line_{line_index:02d}')
                segment['segment_id'] = segment_id
                voice_name = str(segment.get('gemini_voice') or producer.TTS_VOICE)
                voice_direction = voice_first.segment_voice_direction(segment)
                destination = temp_root / f'{reel_id}_{segment_id}_{segment.get("speaker_id", "speaker")}.wav'
                # Cache key includes transcript, performance direction and voice identity.
                producer.ensure_tts_wav(
                    str(segment['text']), destination,
                    voice_direction=voice_direction, voice_name=voice_name,
                )
                duration = voice_first.wav_duration(destination)
                segment['duration_seconds'] = round(duration, 4)
                measured[segment_id] = duration
                log(f'[{concept.get("title", reel_id)}] Voice locked: {segment_id} / {voice_name} / {duration:.2f}s')
            timing = voice_first.build_scene_timing_plan(segments, measured)
            beat['voice_timing'] = timing
            beat['target_frames'] = timing['target_frames']
            log(
                f'[{concept.get("title", reel_id)}] Scene {beat_index} timing locked: '
                f'{timing["target_frames"]} frames / {timing["target_duration_seconds"]:.2f}s; '
                f'{len(segments)} speaker turn(s), no dialogue truncation.'
            )
    concept['voice_first_plan'] = {
        'status': 'voice_measured_before_video',
        'audio_model': producer.GEMINI_TTS_MODEL,
        'cache_key_version': 2,
        'scene_count': len(concept['beats']),
        'dialogue_truncated': False,
        'video_duration_source': 'measured_voice_audio',
    }
    return concept


def persist_character_cast(concept: dict) -> int:
    """Persist only cast records belonging to a fully voice-locked storyboard."""
    characters = concept.get('characters', [])
    for character in characters:
        character_library.upsert_character(character)
    return len(characters)


def plan_week(reel_count: int = 3) -> int:
    if reel_count not in (1, 3):
        raise ValueError('This zero-spend workflow supports a one-Reel test or a 3-Reel weekly batch only.')
    producer.require_env()
    configure_kaggle_cli()
    prior = load_json(PENDING, {}) or {}
    terminal_qa_reason = terminal_finalization_qa_reason(prior)
    if terminal_qa_reason:
        prior = archive_completed_qa_rejection(prior, terminal_qa_reason)
        log(
            f"Archived old batch {prior.get('job_id')} as a terminal QA rejection after Kaggle "
            "confirmed COMPLETE. Its existing scenes will not be reused; a fresh one-Reel plan may proceed."
        )
    if prior.get('status') in ACTIVE_GPU_STATES:
        raise RuntimeError(f"There is already an unfinished GPU batch ({prior.get('job_id')}, status={prior.get('status')}). The system will not queue a duplicate batch; run poll-finalize or inspect the previous Kaggle job first.")

    saved_lock = load_json(TOOLCHAIN_LOCK, {}) or {}
    toolchain_lock = {}
    if saved_lock.get('status') == 'locked':
        toolchain_lock = {
            key: saved_lock[key] for key in ('comfyui_commit', 'comfyui_gguf_commit', 'model_revisions')
            if saved_lock.get(key)
        }
        if len(toolchain_lock) != 3:
            raise RuntimeError('Saved toolchain lock is incomplete. Do not run the weekly batch; use the no-code guide to reset the lock and pass a one-Reel requalification first.')

    history = producer.load_history()
    # Ingest owner-provided performance notes if Telegram has already been connected.
    try:
        accepted = producer.process_telegram_feedback(history)
        # Reload regardless of accepted-insight count: /approve updates history but is not an insight.
        history = producer.load_history()
        if accepted:
            log(f'Incorporated {accepted} owner-submitted performance insight(s) into next-week planning.')
    except Exception as exc:
        log(f'Feedback sync skipped; planning still uses saved history: {exc}')

    if reel_count == 3:
        require_weekly_qualification(history, saved_lock)

    rotation = int(history.get('generated_count', 0)) // 3
    slots = producer.next_post_slots(reel_count, rotation=rotation, history=history)
    planned: list[dict] = []
    local_history = json.loads(json.dumps(history, ensure_ascii=False))
    job_id = datetime.now(TZ).strftime('%Y%m%d_%H%M%S')
    for i, slot in enumerate(slots):
        pillar = producer.choose_pillar(local_history, 0)
        log(f'Planning Reel {i+1}/{reel_count}, pillar={pillar}, proposed slot={slot.isoformat()}')
        concept, review = producer.acquire_approved_concept(local_history, pillar, slot, i)
        reel_id = f"reel_{i+1:02d}_{job_id[-6:]}"
        concept['reel_id'] = reel_id
        concept = prepare_voice_first_plan(concept, reel_id)
        # Create the final shot prompts only after all speaker WAV durations are measured.
        concept = producer.generate_voice_aware_storyboard(concept)
        persisted_cast = persist_character_cast(concept)
        log(f'Persisted {persisted_cast} character metadata record(s) after voice/storyboard validation.')
        concept['editorial_review'] = concept.get('editorial_review') or {
            'scores': review.get('scores', {}), 'approved': review.get('approved', False)
        }
        beats = concept.get('beats', [])
        for j, beat in enumerate(beats, start=1):
            # Model text rendering is unreliable. On-screen Hindi text is always added by FFmpeg after generation.
            prompt = str(beat.get('video_prompt', '')).strip()
            prompt_words = len(prompt.split())
            if not 55 <= prompt_words <= 180 or len(prompt) > 1600:
                raise RuntimeError(
                    f"Reel {i+1}, scene {j}: final voice-aware shot prompt is invalid "
                    f"({prompt_words} words / {len(prompt)} characters). No GPU run was queued."
                )
            beat['scene_index'] = j
        planned.append({
            'reel_id': reel_id,
            'title': concept['title'],
            'pillar': pillar,
            'story_type': concept.get('story_type', 'emotional'),
            'visual_pipeline': concept.get('visual_pipeline', 'legacy_wan_video'),
            'visual_bible': concept.get('visual_bible', ''),
            'theme': concept['theme'],
            'planned_publish_at': slot.isoformat(),
            'planned_publish_label': slot.strftime('%a %d %b, %I:%M %p IST'),
            'concept': concept,
            'beats': [{
                'video_prompt': b['video_prompt'],
                'narrative_role': b['narrative_role'],
                'state_change': b['state_change'],
                'causal_link': b['causal_link'],
                'visual_direction': b['visual_direction'],
                'scene_index': b['scene_index'],
                'voice_timing': b['voice_timing'],
                'target_frames': b['target_frames'],
                'editorial_shots': b.get('editorial_shots', []),
            } for b in beats],
            'delivery_status': 'planned',
        })
        local_history.setdefault('topics', []).append({
            'title': concept['title'], 'theme': concept['theme'], 'pillar': pillar,
            'story_type': concept.get('story_type', 'emotional'),
            'share_recipient': concept.get('share_recipient', ''),
            'share_reason': concept.get('share_reason', ''),
            'narrative_engine': concept.get('narrative_engine', ''),
            'emotional_aftertaste': concept.get('emotional_aftertaste', ''),
            'human_detail': concept.get('human_detail', ''),
            'character_contradiction': concept.get('character_contradiction', ''),
            'cost_of_choice': concept.get('cost_of_choice', ''),
            'generated_at': datetime.now(TZ).isoformat(timespec='seconds'),
            'planned_publish_at': slot.isoformat(), 'status': 'planned_not_published',
        })
        # Advance local anti-repeat/adaptation context only; persisted history updates after final delivery.
        local_history['generated_count'] = int(local_history.get('generated_count', 0)) + 1
        time.sleep(2)

    manifest = {
        'job_id': job_id,
        'created_at_ist': datetime.now(TZ).isoformat(timespec='seconds'),
        'status': 'dispatching',
        'toolchain_lock': toolchain_lock,
        'image_toolchain_lock': load_json(IMAGE_TOOLCHAIN_LOCK, {}) or {},
        'screenplay_schema_version': 2,
        'audio_before_video': True,
        'visual_pipeline': producer.story_engine.PRIMARY_25D_PIPELINE,
        'generation_mode': 'still_image_first',
        'editorial_shot_count': sum(int((r['concept'].get('editorial_shot_plan') or {}).get('editorial_shot_count', 0)) for r in planned),
        'model': 'FLUX.1-schnell Q4_K_S GGUF (4-step still generation) + Depth Anything V2 Small + deterministic 2.5D parallax; no Wan video generation in the primary path',
        'reels': [{
            'reel_id': r['reel_id'], 'title': r['title'], 'pillar': r['pillar'],
            'visual_bible': r['concept'].get('visual_bible', ''),
            'characters': r['concept'].get('characters', []),
            'story_type': r['concept'].get('story_type', 'emotional'),
            'visual_pipeline': r['concept'].get('visual_pipeline', 'legacy_wan_video'),
            'visual_style_profile': r['concept'].get('visual_style_profile', {}),
            'beats': r['beats']
        } for r in planned],
    }
    write_json(PENDING, {
        'job_id': job_id, 'created_at_ist': manifest['created_at_ist'], 'status': 'dispatching',
        'kaggle_kernel_id': kaggle_kernel_id(), 'manifest': manifest, 'reels': planned,
        'policy': {'paid_fallback': False, 'auto_facebook_publish': False, 'max_reels': reel_count},
    })
    push_started = False
    try:
        kernel_dir = build_kaggle_kernel(manifest)
        configure_kaggle_cli()
        push_started = True
        result = subprocess.run(kaggle_cli_command('kernels', 'push', '-p', str(kernel_dir)), text=True, capture_output=True, timeout=900)
        console = (result.stdout or '') + '\n' + (result.stderr or '')
        if result.returncode:
            raise RuntimeError('Kaggle kernel push returned a non-zero exit code: ' + console[-3000:])
    except Exception as exc:
        pending = load_json(PENDING, {}) or {}
        pending['dispatch_error'] = f'{type(exc).__name__}: {exc}'[-5000:]
        pending['dispatch_failed_at_ist'] = datetime.now(TZ).isoformat(timespec='seconds')
        remote_status, remote_output = ('NOT_CHECKED', '')
        if push_started:
            try:
                remote_status, remote_output = kaggle_status(pending.get('kaggle_kernel_id', ''))
            except Exception as status_exc:
                remote_status, remote_output = ('UNKNOWN', f'{type(status_exc).__name__}: {status_exc}')
        pending['dispatch_remote_status'] = remote_status
        if push_started and remote_status in {'RUNNING', 'QUEUED', 'COMPILING', 'CREATED'}:
            # A push can reach Kaggle even when the CLI connection drops. Treat it as active
            # rather than issuing a second job and wasting quota.
            pending['status'] = 'gpu_running'
            pending['dispatched_at_ist'] = datetime.now(TZ).isoformat(timespec='seconds')
            pending['dispatch_output'] = (remote_output or pending['dispatch_error'])[-2000:]
            write_json(PENDING, pending)
            alert_failure('Kaggle accepted or is compiling the BINA SHOR KE job despite a CLI error. The factory has locked this batch to prevent a duplicate GPU run. It will poll the existing job. Details: ' + pending['dispatch_error'][-800:])
            log('Kaggle reports an active job after push error; preserving the existing job instead of dispatching again.')
            return 0
        if push_started:
            # COMPLETE can refer to a previous version of the fixed Kaggle kernel slug.
            # Without a matching job manifest, do not guess whether the new version started.
            pending['status'] = 'dispatch_unknown'
            pending['dispatch_remote_output'] = (remote_output or '')[-2000:]
            write_json(PENDING, pending)
            alert_failure('BINA SHOR KE dispatch status is ambiguous. No second GPU job will be started automatically. Inspect the Kaggle kernel version/history; then set pending status to gpu_running if this run exists, or dispatch_failed only after confirming it did not start. Details: ' + pending['dispatch_error'][-800:])
        else:
            pending['status'] = 'dispatch_failed'
            write_json(PENDING, pending)
            alert_failure('BINA SHOR KE free GPU dispatch failed before any Kaggle push was attempted. No paid fallback was used. Details: ' + pending['dispatch_error'][-1200:])
        raise
    pending = load_json(PENDING, {})
    pending['status'] = 'gpu_running'
    pending['dispatched_at_ist'] = datetime.now(TZ).isoformat(timespec='seconds')
    pending['dispatch_output'] = console[-2000:]
    write_json(PENDING, pending)
    log('Kaggle GPU batch dispatched. It will not post to Facebook; the completion poller will fetch clips, finalize, QA and message Telegram.')
    return 0


def kaggle_status(kernel_id: str) -> tuple[str, str]:
    configure_kaggle_cli()
    p = subprocess.run(kaggle_cli_command('kernels', 'status', kernel_id), text=True, capture_output=True, timeout=180)
    output = (p.stdout or '') + '\n' + (p.stderr or '')
    if p.returncode:
        lower = output.lower()
        if any(word in lower for word in ('not found', '404', 'does not exist')):
            return 'ERROR', output
        return 'UNKNOWN', output
    upper = output.upper()
    # Parse explicit enum/status tokens first so INCOMPLETE cannot be mistaken for COMPLETE.
    match = re.search(r"KERNELWORKERSTATUS\.([A-Z_]+)|\bSTATUS\s*[:=]\s*([A-Z_]+)\b", upper)
    token = next((group for group in match.groups() if group), '') if match else ''
    if token:
        aliases = {'COMPLETED': 'COMPLETE', 'CANCELED': 'CANCELLED', 'FAILED': 'ERROR'}
        token = aliases.get(token, token)
        if token in {'COMPLETE', 'ERROR', 'CANCELLED', 'RUNNING', 'QUEUED', 'COMPILING', 'CREATED'}:
            return token, output
    # Fallback uses line-level word boundaries and explicitly excludes INCOMPLETE.
    for line in upper.splitlines():
        if 'INCOMPLETE' in line:
            continue
        for status in ('CANCELLED', 'CANCELED', 'ERROR', 'RUNNING', 'QUEUED', 'COMPILING', 'COMPLETE', 'CREATED'):
            if re.search(rf'\b{status}\b', line):
                return ('CANCELLED' if status == 'CANCELED' else 'COMPLETE' if status == 'COMPLETED' else status), output
    return 'UNKNOWN', output


def locate_output_root(root: Path) -> Path | None:
    direct = root / 'bsk_output'
    if direct.exists():
        return direct
    for marker in ('gpu_output_manifest.json', 'gpu_checkpoint_manifest.json', 'GPU_JOB_ERROR.json'):
        for p in root.rglob(marker):
            return p.parent
    # Kaggle may flatten the output folder while preserving individual scene files.
    if any(root.rglob('scene_*.mp4')):
        return root
    return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def collect_checkpoint_clips(root: Path, pending: dict) -> list[dict]:
    """Find valid scene files from a possibly failed Kaggle output bundle."""
    checkpoint_path = root / 'gpu_checkpoint_manifest.json'
    saved = load_json(checkpoint_path, {}) if checkpoint_path.exists() else {}
    saved_items = {
        (str(x.get('reel_id')), int(x.get('scene_index', 0))): x
        for x in saved.get('scenes', []) if x.get('reel_id') and x.get('scene_index')
    }
    worker_manifest = load_json(root / 'gpu_output_manifest.json', {}) if (root / 'gpu_output_manifest.json').exists() else {}
    worker_items = {
        (str(x.get('reel_id')), int(x.get('scene_index', 0))): x
        for x in worker_manifest.get('scenes', []) if x.get('reel_id') and x.get('scene_index')
    }
    collected = []
    for reel in pending.get('reels', []):
        reel_id = str(reel.get('reel_id', ''))
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', reel_id):
            continue
        for index in range(1, len(reel.get('beats', [])) + 1):
            candidates = [root / reel_id / f'scene_{index:02d}.mp4']
            candidates.extend(root.rglob(f'{reel_id}__scene_{index:02d}.mp4'))
            candidates.extend(x for x in root.rglob(f'scene_{index:02d}.mp4') if reel_id in str(x))
            source = next((x for x in candidates if x.is_file() and x.stat().st_size >= 100_000), None)
            if source is None:
                continue
            try:
                duration = producer.probe_duration(source)
            except Exception:
                continue
            if not 2.5 <= duration <= 8.0:
                continue
            key = (reel_id, index)
            old = saved_items.get(key, worker_items.get(key, {}))
            collected.append({
                'reel_id': reel_id, 'scene_index': index, 'file': f'{reel_id}__scene_{index:02d}.mp4',
                'source_path': str(source), 'bytes': source.stat().st_size, 'sha256': _sha256(source),
                'duration_seconds': round(duration, 3),
                'generation_elapsed_seconds': float(old.get('generation_elapsed_seconds', 0) or 0),
                'prompt_id': old.get('prompt_id'),
            })
    # One scene may appear in the direct location and a flattened CLI output; retain one row per key.
    deduped = {}
    for item in collected:
        deduped[(item['reel_id'], item['scene_index'])] = item
    return list(deduped.values())


def estimate_resume_hours(pending: dict, scenes: list[dict]) -> float:
    expected = sum(len(x.get('beats', [])) for x in pending.get('reels', []))
    present = {(x['reel_id'], x['scene_index']) for x in scenes}
    missing = max(0, expected - len(present))
    if missing == 0:
        return 1.5  # ComfyUI/model bootstrap can still consume substantial time
    times = [float(x.get('generation_elapsed_seconds', 0)) for x in scenes if float(x.get('generation_elapsed_seconds', 0)) > 0]
    if not times:
        lock = load_json(TOOLCHAIN_LOCK, {}) or {}
        benchmark = lock.get('gpu_benchmark') if isinstance(lock, dict) else {}
        average = float((benchmark or {}).get('sample_scene_mean_seconds', 0) or 0)
    else:
        average = statistics.median(times)
    if average <= 0:
        return 999.0
    # 2x generation-time safety plus 60 minutes for model bootstrap and dataset restoration.
    return round((missing * average * 2.0 + 3600) / 3600, 2)


def persist_private_resume_dataset(root: Path, pending: dict) -> dict | None:
    """Upload only verified MP4 scene checkpoints to a private Kaggle dataset."""
    scenes = collect_checkpoint_clips(root, pending)
    if not scenes:
        return None
    username = os.getenv('KAGGLE_USERNAME', '').strip()
    if not username:
        raise RuntimeError('Cannot save recovery clips: KAGGLE_USERNAME is missing.')
    job_token = re.sub(r'[^a-z0-9]', '', str(pending.get('job_id', '')).lower())[-18:] or str(int(time.time()))
    dataset_slug = str((pending.get('resume_dataset_id') or '').split('/')[-1] or f'bsk-resume-{job_token}')
    dataset_id = f'{username}/{dataset_slug}'
    expected = sum(len(x.get('beats', [])) for x in pending.get('reels', []))
    with tempfile.TemporaryDirectory(prefix='bsk-private-checkpoint-') as folder:
        stage = Path(folder)
        total_bytes = 0
        scene_rows = []
        for item in scenes:
            source = Path(item['source_path'])
            dest = stage / item['file']
            shutil.copy2(source, dest)
            # Verify the copy before asking Kaggle to store it.
            if dest.stat().st_size != item['bytes'] or _sha256(dest) != item['sha256']:
                raise RuntimeError(f'Checkpoint copy verification failed for {item["file"]}.')
            total_bytes += dest.stat().st_size
            scene_rows.append({key: value for key, value in item.items() if key != 'source_path'})
        if total_bytes > 8 * 1024**3:
            raise RuntimeError('Recovered clips exceed the 8 GiB safety cap; refusing to upload a large checkpoint dataset.')
        write_json(stage / 'checkpoint_manifest.json', {
            'schema_version': 1, 'job_id': pending.get('job_id'), 'expected_scenes': expected,
            'completed_scenes': len(scene_rows), 'scenes': scene_rows,
            'privacy': 'Kaggle dataset created without --public; intended to remain private.',
        })
        metadata = {
            'title': f'BINA SHOR KE private scene checkpoint {job_token}',
            'id': dataset_id,
            'licenses': [{'name': 'other'}],
            'keywords': ['bina-shor-ke', 'private-checkpoint', 'video-scenes'],
        }
        write_json(stage / 'dataset-metadata.json', metadata)
        existing = bool(pending.get('resume_dataset_id'))
        if existing:
            command = ['kaggle', 'datasets', 'version', '-p', str(stage), '-m', 'BINA SHOR KE resumable scene checkpoint update', '-q', '-r', 'skip']
        else:
            command = ['kaggle', 'datasets', 'create', '-p', str(stage), '-q', '-r', 'skip']
        response = subprocess.run(command, text=True, capture_output=True, timeout=1800)
        output = (response.stdout or '') + '\n' + (response.stderr or '')
        if response.returncode:
            raise RuntimeError('Kaggle private checkpoint dataset upload failed: ' + output[-2500:])
    missing = max(0, expected - len(scene_rows))
    return {
        'resume_dataset_id': dataset_id, 'resume_scene_count': len(scene_rows),
        'resume_missing_scene_count': missing, 'resume_estimated_hours': estimate_resume_hours(pending, scenes),
        'resume_dataset_updated_at_ist': datetime.now(TZ).isoformat(timespec='seconds'),
        'resume_checkpoint_sha256': hashlib.sha256(json.dumps(scene_rows, sort_keys=True).encode()).hexdigest(),
    }


def dispatch_checkpoint_resume(pending: dict, automatic: bool) -> int:
    """Dispatch one bounded resume run from the last private scene checkpoint."""
    dataset_id = str(pending.get('resume_dataset_id', '')).strip()
    if not dataset_id:
        raise RuntimeError('No private Kaggle checkpoint dataset is saved; there is nothing to resume.')
    if int(pending.get('resume_attempts', 0)) >= 2:
        raise RuntimeError('The maximum of two bounded resume attempts has been used. A new production plan is required.')
    estimate = float(pending.get('resume_estimated_hours', 999) or 999)
    limit = 4.0 if automatic else 8.0
    if estimate > limit:
        raise RuntimeError(f'Remaining-scene estimate is {estimate:.1f} hours, above the {limit:.1f}-hour resume safety limit. Keep the private checkpoint; do not risk another free GPU session.')
    manifest = dict(pending.get('manifest') or {})
    manifest['resume_dataset_id'] = dataset_id
    kernel_dir = build_kaggle_kernel(manifest)
    try:
        result = subprocess.run(['kaggle', 'kernels', 'push', '-p', str(kernel_dir)], text=True, capture_output=True, timeout=900)
        console = (result.stdout or '') + '\n' + (result.stderr or '')
        push_failed = bool(result.returncode)
    except Exception as push_exc:
        # A timeout/network reset can happen after Kaggle accepted the kernel version.
        # Treat this exactly like a non-zero result and require owner confirmation.
        console = f'{type(push_exc).__name__}: {push_exc}'
        push_failed = True
    if push_failed:
        try:
            status, remote = kaggle_status(pending.get('kaggle_kernel_id', ''))
        except Exception as status_exc:
            status, remote = 'UNKNOWN', f'{type(status_exc).__name__}: {status_exc}'
        # Any non-zero/timeout response is ambiguous: Kaggle may have accepted the request.
        # Do not trust a possibly stale kernel status or send another job.
        pending['status'] = 'dispatch_unknown'
        pending['resume_dispatch_attempt_pending'] = True
        pending['resume_dispatch_error'] = console[-2500:]
        pending['resume_dispatch_remote_status'] = status
        pending['resume_dispatch_remote_output'] = remote[-1500:]
        write_json(PENDING, pending)
        alert_failure('BINA SHOR KE checkpoint resume dispatch returned an unclear result. No duplicate GPU job was sent. Inspect the existing Kaggle kernel run/version before taking further action.')
        return 1
    pending['manifest'] = manifest
    pending['resume_attempts'] = int(pending.get('resume_attempts', 0)) + 1
    pending['resume_dispatched_at_ist'] = datetime.now(TZ).isoformat(timespec='seconds')
    pending['resume_dispatch_mode'] = 'automatic' if automatic else 'owner_requested'
    pending['status'] = 'gpu_running'
    pending['dispatched_at_ist'] = pending['resume_dispatched_at_ist']
    pending['dispatch_output'] = console[-2000:]
    write_json(PENDING, pending)
    log(f'Resumed {pending.get("resume_scene_count", 0)} verified scene checkpoints; Kaggle will render only the missing scenes.')
    return 0


def cleanup_resume_dataset(dataset_id: str | None):
    if not dataset_id or not re.fullmatch(r'[A-Za-z0-9_-]{1,50}/bsk-resume-[A-Za-z0-9_-]{1,50}', dataset_id):
        return
    try:
        subprocess.run(['kaggle', 'datasets', 'delete', dataset_id, '-y'], text=True, capture_output=True, timeout=180)
    except Exception as exc:
        log(f'Private checkpoint cleanup skipped; dataset remains private: {exc}')


def handle_gpu_failure(root: Path | None, pending: dict, reason: str) -> bool:
    """Save recoverable scenes and start at most one safe resume. Returns True if resumed."""
    if root is None:
        pending['status'] = 'gpu_failed'
        pending['gpu_error'] = reason[:5000]
        write_json(PENDING, pending)
        alert_failure('BINA SHOR KE GPU job failed and Kaggle exposed no output bundle to recover. No paid fallback or duplicate GPU job was started. ' + reason[:1200])
        return False
    try:
        checkpoint = persist_private_resume_dataset(root, pending)
    except Exception as exc:
        pending['status'] = 'gpu_failed'
        pending['gpu_error'] = reason[:3500]
        pending['checkpoint_save_error'] = f'{type(exc).__name__}: {exc}'[:2500]
        write_json(PENDING, pending)
        alert_failure('BINA SHOR KE GPU job failed. Automatic checkpoint upload could not be completed; no partial Reel was sent and no paid fallback was used. ' + pending['checkpoint_save_error'][:1100])
        return False
    if not checkpoint:
        pending['status'] = 'gpu_failed'
        pending['gpu_error'] = reason[:5000]
        write_json(PENDING, pending)
        alert_failure('BINA SHOR KE GPU job failed; no complete scene MP4 passed recovery validation. No partial Reel was delivered and no duplicate job was started. ' + reason[:1200])
        return False
    pending.update(checkpoint)
    pending['gpu_error'] = reason[:5000]
    write_json(PENDING, pending)
    if int(pending.get('resume_attempts', 0)) < 1 and float(pending.get('resume_estimated_hours', 999)) <= 4.0:
        alert_failure(f'Kaggle job stopped. Saved {pending["resume_scene_count"]} verified scenes to a private Kaggle checkpoint; estimated remaining render is {pending["resume_estimated_hours"]:.1f}h. Starting the one bounded auto-resume now.')
        return dispatch_checkpoint_resume(pending, automatic=True) == 0
    pending['status'] = 'gpu_checkpoint_saved'
    write_json(PENDING, pending)
    remaining_attempts = max(0, 2 - int(pending.get('resume_attempts', 0)))
    if remaining_attempts:
        alert_failure(f'Kaggle job stopped. Saved {pending["resume_scene_count"]} verified scenes to a private Kaggle checkpoint. Estimated remaining time: {pending["resume_estimated_hours"]:.1f}h. Automatic resume was withheld to protect free GPU quota; one owner-triggered resume can be started from workflow action=resume-checkpoint if the estimate is within 8h.')
    else:
        alert_failure(f'Resume attempt limit reached. Saved {pending["resume_scene_count"]} verified scenes in a private Kaggle checkpoint for diagnosis; no further GPU run was started. Create a fresh plan when ready.')
    return False


def verify_or_lock_toolchain(gpu_manifest: dict, job_id: str | None = None) -> dict:
    """Pin the first successful GPU toolchain; refuse silent upstream drift later."""
    observed = {
        'comfyui_commit': str(gpu_manifest.get('comfyui_commit', '')).strip(),
        'comfyui_gguf_commit': str(gpu_manifest.get('comfyui_gguf_commit', '')).strip(),
        'model_revisions': gpu_manifest.get('model_revisions'),
        'runtime_packages': gpu_manifest.get('runtime_packages') if isinstance(gpu_manifest.get('runtime_packages'), dict) else {},
    }
    if not observed['comfyui_commit'] or not observed['comfyui_gguf_commit']:
        raise RuntimeError('GPU manifest is missing source commit SHAs; cannot establish a reproducible toolchain lock.')
    if not isinstance(observed['model_revisions'], dict) or not all(observed['model_revisions'].get(k) for k in ('unet', 'clip', 'vae')):
        raise RuntimeError('GPU manifest is missing one or more model revision SHAs; cannot establish a reproducible model lock.')

    existing = load_json(TOOLCHAIN_LOCK, {}) or {}
    if existing.get('status') == 'locked':
        for key in ('comfyui_commit', 'comfyui_gguf_commit'):
            if existing.get(key) != observed[key]:
                raise RuntimeError(f'Toolchain drift detected for {key}; refusing to silently change the proven version.')
        for key in ('unet', 'clip', 'vae'):
            if (existing.get('model_revisions') or {}).get(key) != observed['model_revisions'].get(key):
                raise RuntimeError(f'Model revision drift detected for {key}; refusing to silently change the proven model weights.')
        locked_depth = (existing.get('model_revisions') or {}).get('depth')
        observed_depth = observed['model_revisions'].get('depth')
        if locked_depth and observed_depth != locked_depth:
            raise RuntimeError('Depth Anything model revision drift detected; refusing to silently change the proven depth estimator.')
        depth_revision_addition = bool(observed_depth and not locked_depth)
        if depth_revision_addition:
            existing.setdefault('model_revisions', {})['depth'] = observed_depth
            existing['depth_model_locked_at_ist'] = datetime.now(TZ).isoformat(timespec='seconds')
        locked_packages = existing.get('runtime_packages') or {}
        if not isinstance(locked_packages, dict):
            raise RuntimeError('GPU runtime package lock is malformed; refusing to continue without a reproducible dependency baseline.')
        changed = sorted(
            name for name, locked_version in locked_packages.items()
            if observed['runtime_packages'].get(name) != locked_version
        )
        if changed:
            raise RuntimeError(
                'GPU runtime dependency drift detected; refusing to change or omit previously locked packages: '
                + ', '.join(changed)
            )
        package_additions = {
            name: version for name, version in observed['runtime_packages'].items()
            if name not in locked_packages
        }
        lock_updated = depth_revision_addition
        if package_additions:
            # Additive migration only: preserve every previously qualified version.
            existing.setdefault('runtime_packages', {}).update(package_additions)
            existing['runtime_packages_extended_at_ist'] = datetime.now(TZ).isoformat(timespec='seconds')
            prior_additions = existing.get('runtime_package_additions', [])
            if not isinstance(prior_additions, list) or not all(isinstance(item, str) for item in prior_additions):
                prior_additions = []
            existing['runtime_package_additions'] = sorted(set(prior_additions) | set(package_additions))
            lock_updated = True
        if lock_updated:
            write_json(TOOLCHAIN_LOCK, existing)
            if depth_revision_addition:
                log('Added the first immutable Depth Anything V2 revision to the existing Wan toolchain lock.')
            if package_additions:
                log('Extended the existing GPU runtime lock with newly required packages: ' + ', '.join(sorted(package_additions)))
        scene_times = [float(x.get('generation_elapsed_seconds', 0)) for x in gpu_manifest.get('scenes', []) if float(x.get('generation_elapsed_seconds', 0)) > 0]
        if not existing.get('gpu_benchmark') and scene_times and len(scene_times) >= 5:
            startup = max(0.0, float(gpu_manifest.get('total_elapsed_seconds', 0)) - sum(scene_times))
            estimate = (startup + sum(scene_times) * 3) * 1.5 / 3600.0
            existing['gpu_benchmark'] = {'qualified': estimate <= 8.0, 'sample_scene_count': len(scene_times), 'sample_scene_mean_seconds': round(sum(scene_times)/len(scene_times), 2), 'first_run_startup_seconds': round(startup, 2), 'estimated_3_reel_hours': round(estimate, 2), 'safety_factor': 1.5, 'note': 'One-Reel benchmark; not a runtime guarantee.'}
            write_json(TOOLCHAIN_LOCK, existing)
        return existing

    scene_times = [float(x.get('generation_elapsed_seconds', 0)) for x in gpu_manifest.get('scenes', []) if float(x.get('generation_elapsed_seconds', 0)) > 0]
    benchmark = None
    if scene_times and len(scene_times) >= 5:
        startup = max(0.0, float(gpu_manifest.get('total_elapsed_seconds', 0)) - sum(scene_times))
        estimated_3_reel_hours = (startup + sum(scene_times) * 3) * 1.5 / 3600.0
        benchmark = {
            'qualified': estimated_3_reel_hours <= 8.0,
            'sample_scene_count': len(scene_times),
            'sample_scene_mean_seconds': round(sum(scene_times) / len(scene_times), 2),
            'first_run_startup_seconds': round(startup, 2),
            'estimated_3_reel_hours': round(estimated_3_reel_hours, 2),
            'safety_factor': 1.5,
            'note': 'Estimate based on one successful Reel; re-check actual Kaggle session/quota before batch. Not a runtime guarantee.'
        }
    locked = {
        'status': 'locked',
        'gpu_benchmark': benchmark,
        'comfyui_commit': observed['comfyui_commit'],
        'comfyui_gguf_commit': observed['comfyui_gguf_commit'],
        'model_revisions': observed['model_revisions'],
        'runtime_packages': observed['runtime_packages'],
        'locked_at_ist': datetime.now(TZ).isoformat(timespec='seconds'),
        'source_job_id': job_id or gpu_manifest.get('job_id'),
        'note': 'First complete GPU generation; future jobs reuse these exact source/model revisions until deliberate requalification.',
    }
    write_json(TOOLCHAIN_LOCK, locked)
    log('Locked the first successful ComfyUI/GGUF/model revisions for reproducible future runs.')
    return locked


def verify_or_lock_image_toolchain(gpu_manifest: dict, job_id: str | None = None) -> dict:
    """Pin FLUX still generation, its text encoders, VAE and depth model separately from legacy Wan."""
    observed = {
        'comfyui_commit': str(gpu_manifest.get('comfyui_commit', '')).strip(),
        'comfyui_gguf_commit': str(gpu_manifest.get('comfyui_gguf_commit', '')).strip(),
        'model_revisions': gpu_manifest.get('model_revisions'),
        'runtime_packages': gpu_manifest.get('runtime_packages') if isinstance(gpu_manifest.get('runtime_packages'), dict) else {},
    }
    required_models = ('unet', 'clip_l', 't5xxl', 'vae', 'depth')
    if not re.fullmatch(r'[0-9a-f]{40}', observed['comfyui_commit']):
        raise RuntimeError('Image-first manifest lacks an immutable ComfyUI commit SHA.')
    if not re.fullmatch(r'[0-9a-f]{40}', observed['comfyui_gguf_commit']):
        raise RuntimeError('Image-first manifest lacks an immutable ComfyUI-GGUF commit SHA.')
    if not isinstance(observed['model_revisions'], dict) or any(
        not re.fullmatch(r'[0-9a-f]{40}', str(observed['model_revisions'].get(key, '')))
        for key in required_models
    ):
        raise RuntimeError('Image-first manifest lacks one or more immutable FLUX/text-encoder/VAE/depth model revisions.')

    existing = load_json(IMAGE_TOOLCHAIN_LOCK, {}) or {}
    if existing.get('status') == 'locked':
        for key in ('comfyui_commit', 'comfyui_gguf_commit'):
            if existing.get(key) != observed[key]:
                raise RuntimeError(f'Image toolchain drift detected for {key}; refusing silent upstream changes.')
        for key in required_models:
            if (existing.get('model_revisions') or {}).get(key) != observed['model_revisions'].get(key):
                raise RuntimeError(f'Image model revision drift detected for {key}; refusing silent model changes.')
        locked_packages = existing.get('runtime_packages') or {}
        changed = sorted(
            name for name, version in locked_packages.items()
            if observed['runtime_packages'].get(name) != version
        )
        if changed:
            raise RuntimeError('Image GPU runtime dependency drift detected: ' + ', '.join(changed))
    else:
        existing = {
            'status': 'locked',
            'generation_mode': 'still_image_first',
            'model_family': 'FLUX.1-schnell-Q4_K_S-GGUF',
            'comfyui_commit': observed['comfyui_commit'],
            'comfyui_gguf_commit': observed['comfyui_gguf_commit'],
            'model_revisions': observed['model_revisions'],
            'runtime_packages': observed['runtime_packages'],
            'locked_at_ist': datetime.now(TZ).isoformat(timespec='seconds'),
            'source_job_id': job_id or gpu_manifest.get('job_id'),
            'note': 'Separate immutable image-first toolchain lock. Does not overwrite or reinterpret the legacy Wan toolchain.',
        }

    elapsed = float(gpu_manifest.get('total_elapsed_seconds', 0) or 0)
    scene_times = [
        float(item.get('generation_elapsed_seconds', 0))
        for item in gpu_manifest.get('scenes', [])
        if float(item.get('generation_elapsed_seconds', 0) or 0) > 0
    ]
    if gpu_manifest.get('status') == 'complete' and elapsed > 0 and len(scene_times) >= 5:
        # Conservative estimate: one clean 6-scene image+parallax run, repeated
        # three times, with 50% safety margin. This is not a runtime guarantee.
        estimate = elapsed * 3.0 * 1.5 / 3600.0
        existing['gpu_benchmark'] = {
            'qualified': estimate <= 8.0,
            'sample_scene_count': len(scene_times),
            'sample_scene_mean_seconds': round(statistics.mean(scene_times), 2),
            'measured_one_reel_seconds': round(elapsed, 2),
            'estimated_3_reel_hours': round(estimate, 2),
            'safety_factor': 1.5,
            'note': 'Measured end-to-end FLUX still + depth + checkpoint runtime from one completed Reel; repeat runs may vary.',
        }
        existing['last_benchmark_job_id'] = job_id or gpu_manifest.get('job_id')
        existing['last_benchmark_at_ist'] = datetime.now(TZ).isoformat(timespec='seconds')
    write_json(IMAGE_TOOLCHAIN_LOCK, existing)
    return existing


def _poll_and_finalize_impl() -> int:
    producer.require_env()
    pending = load_json(PENDING, {})
    if not pending or pending.get('status') not in {'gpu_running', 'gpu_complete'}:
        log(f'No active batch to poll (status={pending.get("status") if pending else "none"}).')
        return 0
    kernel_id = pending['kaggle_kernel_id']
    status, raw = kaggle_status(kernel_id)
    log(f'Kaggle status: {status}; {raw.strip()[:300]}')
    if status in {'RUNNING', 'QUEUED', 'COMPILING', 'CREATED', 'UNKNOWN'}:
        dispatched = pending.get('dispatched_at_ist') or pending.get('created_at_ist')
        if dispatched and not pending.get('long_run_alert_sent'):
            try:
                age_hours = (datetime.now(TZ) - datetime.fromisoformat(dispatched)).total_seconds() / 3600
            except (TypeError, ValueError):
                age_hours = 0
            if age_hours >= 8:
                pending['long_run_alert_sent'] = True
                pending['last_seen_gpu_status'] = status
                write_json(PENDING, pending)
                alert_failure(f'BINA SHOR KE GPU batch is still {status} after about {age_hours:.1f} hours. Free Kaggle queue/session limits may be involved. No duplicate job or paid fallback was started; inspect Kaggle status before retrying.')
        return 0

    with tempfile.TemporaryDirectory(prefix='bsk-kaggle-output-') as td:
        dest = Path(td) / 'downloaded'
        dest.mkdir(parents=True, exist_ok=True)
        configure_kaggle_cli()
        p = subprocess.run(['kaggle', 'kernels', 'output', kernel_id, '-p', str(dest)], text=True, capture_output=True, timeout=1800)
        dl_output = (p.stdout or '') + '\n' + (p.stderr or '')
        root = locate_output_root(dest)
        err_file = None
        if root:
            err_file = root / 'GPU_JOB_ERROR.json'
        if status in {'ERROR', 'CANCELLED', 'CANCELED'} or p.returncode:
            reason = dl_output[-2000:]
            if err_file and err_file.exists():
                reason = err_file.read_text(encoding='utf-8')[-4000:]
            resumed = handle_gpu_failure(root, pending, reason)
            return 0 if resumed else 1
        if not root:
            pending['status'] = 'gpu_failed'
            pending['gpu_error'] = 'Kaggle run completed but no bsk_output manifest/folder was returned. ' + dl_output[-2000:]
            write_json(PENDING, pending)
            alert_failure('BINA SHOR KE GPU output is missing or incomplete. No partial Reel was delivered. Check Kaggle kernel outputs.')
            return 1
        manifest_path = root / 'gpu_output_manifest.json'
        gpu_manifest = load_json(manifest_path, {}) if manifest_path.exists() else {}
        if err_file and err_file.exists() or gpu_manifest.get('status') != 'complete':
            reason = load_json(err_file, {}) if err_file and err_file.exists() else gpu_manifest
            resumed = handle_gpu_failure(root, pending, json.dumps(reason, ensure_ascii=False))
            return 0 if resumed else 1

        expected = sum(len(r['beats']) for r in pending.get('reels', []))
        primary_image_first = gpu_manifest.get('generation_mode') == 'still_image_first'
        existing_videos = list(root.rglob('scene_*.mp4'))
        existing_images = list(root.rglob('scene_*.png'))
        if primary_image_first:
            parallax_videos = [p for p in existing_videos if re.fullmatch(r'scene_\d{2}_25d\.mp4', p.name)]
            if len(existing_images) < expected or len(parallax_videos) < expected:
                resumed = handle_gpu_failure(
                    root, pending,
                    f'Image-first job expected {expected} FLUX PNG stills and {expected} depth-parallax videos; '
                    f'received {len(existing_images)} stills and {len(parallax_videos)} parallax videos.'
                )
                return 0 if resumed else 1
            verify_or_lock_image_toolchain(gpu_manifest, pending.get('job_id'))
        else:
            if len(existing_videos) < expected:
                resumed = handle_gpu_failure(root, pending, f'Expected {expected} AI scene clips, received {len(existing_videos)}.')
                return 0 if resumed else 1
            verify_or_lock_toolchain(gpu_manifest, pending.get('job_id'))

        pending['status'] = 'finalizing'
        write_json(PENDING, pending)
        all_missing = []
        stamp_prefix = datetime.now(TZ).strftime('%Y%m%d_%H%M')
        for ordinal, reel in enumerate(pending['reels'], start=1):
            if reel.get('delivery_status') == 'delivered':
                continue
            concept = reel['concept']
            slug = re.sub(r'[^a-z0-9]+', '-', concept['title'].lower()).strip('-') or f'reel-{ordinal}'
            pending['active_finalizing_reel_id'] = reel['reel_id']
            write_json(PENDING, pending)
            if reel.get('output_directory'):
                reel_dir = ROOT / reel['output_directory']
            else:
                reel_dir = OUT / f'{stamp_prefix}_{ordinal}_{slug}'
                reel['output_directory'] = str(reel_dir.relative_to(ROOT))
                write_json(PENDING, pending)
            ai_dir = reel_dir / 'ai_clips'
            ai_dir.mkdir(parents=True, exist_ok=True)
            needed = len(concept['beats'])
            missing = []
            for i in range(1, needed + 1):
                extension = 'png' if primary_image_first else 'mp4'
                source_name = f'scene_{i:02d}.{extension}'
                candidates = [
                    p for p in (existing_images if primary_image_first else existing_videos)
                    if reel['reel_id'] in p.parts and p.name == source_name
                ]
                if not candidates:
                    candidates = [
                        p for p in (existing_images if primary_image_first else existing_videos)
                        if p.name == source_name and reel['reel_id'] in str(p)
                    ]
                if len(candidates) != 1:
                    missing.append(f'{i}_source_missing_or_ambiguous')
                    continue
                source = candidates[0]
                if primary_image_first:
                    image_rows = [
                        item for item in gpu_manifest.get('scenes', [])
                        if str(item.get('reel_id')) == str(reel['reel_id'])
                        and int(item.get('scene_index', 0)) == i
                        and item.get('media_type') == 'image/png'
                    ]
                    if len(image_rows) != 1:
                        missing.append(f'{i}_still_manifest_missing_or_ambiguous')
                        continue
                    row = image_rows[0]
                    expected_bytes = int(row.get('bytes', -1))
                    expected_sha = str(row.get('sha256', '')).lower()
                    if (
                        expected_bytes <= 100_000
                        or not re.fullmatch(r'[0-9a-f]{64}', expected_sha)
                        or source.stat().st_size != expected_bytes
                        or _sha256(source) != expected_sha
                    ):
                        missing.append(f'{i}_still_hash_or_size_mismatch')
                        continue
                    with Image.open(source) as image:
                        image.verify()
                    with Image.open(source) as image:
                        if image.size != (704, 1280):
                            missing.append(f'{i}_still_dimensions_invalid')
                            continue
                    still_dest = ai_dir / f'scene_{i:02d}.png'
                    shutil.copy2(source, still_dest)
                    if _sha256(still_dest) != expected_sha:
                        still_dest.unlink(missing_ok=True)
                        missing.append(f'{i}_still_copy_hash_mismatch')
                        continue
                else:
                    shutil.copy2(source, ai_dir / f'scene_{i:02d}.mp4')

                if producer.story_engine.is_25d_pipeline(concept.get('visual_pipeline')):
                    depth_candidates = [
                        p for p in existing_videos
                        if reel['reel_id'] in p.parts and p.name == f'scene_{i:02d}_25d.mp4'
                    ]
                    if not depth_candidates:
                        depth_candidates = [
                            p for p in existing_videos
                            if p.name == f'scene_{i:02d}_25d.mp4' and reel['reel_id'] in str(p)
                        ]
                    depth_rows = [
                        item for item in gpu_manifest.get('parallax_scenes', [])
                        if str(item.get('reel_id')) == str(reel['reel_id'])
                        and int(item.get('scene_index', 0)) == i
                    ]
                    if len(depth_candidates) != 1 or len(depth_rows) != 1:
                        missing.append(f'{i}_25d_missing_or_ambiguous')
                    else:
                        depth_source = depth_candidates[0]
                        depth_meta = depth_rows[0]
                        expected_bytes = int(depth_meta.get('bytes', -1))
                        expected_sha = str(depth_meta.get('sha256', '')).lower()
                        if (
                            expected_bytes <= 100_000
                            or not re.fullmatch(r'[0-9a-f]{64}', expected_sha)
                            or depth_source.stat().st_size != expected_bytes
                            or _sha256(depth_source) != expected_sha
                        ):
                            missing.append(f'{i}_25d_hash_or_size_mismatch')
                        else:
                            depth_dest = ai_dir / f'scene_{i:02d}_25d.mp4'
                            shutil.copy2(depth_source, depth_dest)
                            if _sha256(depth_dest) != expected_sha:
                                depth_dest.unlink(missing_ok=True)
                                missing.append(f'{i}_25d_copy_hash_mismatch')
            if missing:
                all_missing.append(f"{reel['reel_id']}: scenes {missing}")
                continue
            (reel_dir / 'concept.json').write_text(json.dumps(concept, ensure_ascii=False, indent=2), encoding='utf-8')
            if isinstance(concept.get('editorial_shot_plan'), dict):
                write_json(reel_dir / 'editorial_shot_plan.json', concept['editorial_shot_plan'])
            os.environ['REQUIRE_AI_VIDEO'] = '1'
            build = producer.render_reel(concept, reel_dir, set(), set())
            slot = datetime.fromisoformat(reel['planned_publish_at'])
            quality = producer.write_pack(concept, build, reel_dir, slot)
            ensure_reel_qa_passed(build)
            image_first = gpu_manifest.get('generation_mode') == 'still_image_first'
            quality['video_generation'] = {
                'model': 'FLUX.1-schnell Q4_K_S GGUF still generation + Depth Anything V2 (ComfyUI)' if image_first else 'Wan2.2 TI2V-5B Q4_K_M GGUF (ComfyUI)',
                'scene_count': needed,
                'source_video_generation_count': 0 if image_first else needed,
                'source_still_image_generation_count': needed if image_first else 0,
                'parallax_video_count': needed if image_first else int((concept.get('editorial_shot_plan') or {}).get('depth_parallax_shot_count', 0)),
                'generation_mode': 'still_image_first' if image_first else 'wan_video_first_legacy',
                'editorial_shot_count': int((concept.get('editorial_shot_plan') or {}).get('editorial_shot_count', needed)),
                'visual_pipeline': concept.get('visual_pipeline', 'legacy_wan_video'),
                'depth_model': {
                    'name': 'depth-anything/Depth-Anything-V2-Small-hf',
                    'revision': gpu_manifest.get('depth_model_revision'),
                    'license': 'Apache-2.0',
                },
                'paid_generation_api_used': False,
                'visual_quality_claim': (
                    'Six FLUX-generated illustrated stills, pinned Depth Anything V2 maps and deterministic 100% 2.5D editorial coverage; no Wan video calls in the primary image-first path. Human review remains mandatory.'
                    if image_first else
                    'Illustrated Wan2.2 source clips plus pinned Depth Anything V2 keyframe parallax and deterministic editorial coverage; human review required; no guarantee of aesthetic approval.'
                ),
                'human_review_before_publish': True,
            }
            write_json(reel_dir / 'quality_report.json', quality)
            # Explicitly preserve original prompt bundle and one-screen review checklist.
            (reel_dir / 'ai_visual_prompts.txt').write_text('\n\n'.join(
                f"SCENE {i+1}\nPurpose: {b['visual_direction']}\nPrompt: {b['video_prompt']}" for i, b in enumerate(concept['beats'])
            ) + '\n', encoding='utf-8')
            def save_delivery_progress(steps):
                reel['delivery_steps'] = steps
                write_json(PENDING, pending)
            reel['delivery_steps'] = producer.send_to_telegram(
                concept, build, reel_dir, slot, ordinal, len(pending['reels']),
                progress=reel.get('delivery_steps', {}), on_progress=save_delivery_progress,
            )
            ensure_complete_telegram_delivery(reel['delivery_steps'])
            reel['delivery_status'] = 'delivered'
            reel['delivery_completed_at_ist'] = datetime.now(TZ).isoformat(timespec='seconds')
            history = producer.load_history()
            delivered_topic = {
                'title': concept['title'], 'theme': concept['theme'], 'pillar': concept['pillar'],
                'narrative_engine': concept.get('narrative_engine', ''),
                'emotional_aftertaste': concept.get('emotional_aftertaste', ''),
                'human_detail': concept.get('human_detail', ''),
                'character_contradiction': concept.get('character_contradiction', ''),
                'cost_of_choice': concept.get('cost_of_choice', ''),
                'generated_at': pending['created_at_ist'], 'planned_publish_at': reel['planned_publish_at'],
                'status': 'ready_for_manual_publish_not_confirmed_published',
                'reel_id': reel['reel_id'], 'job_id': pending.get('job_id'),
                # render_reel returns only after its hard technical and visual QA gates pass.
                'qa_passed': bool(
                    build.get('technical', {}).get('technical_checks_passed') is True
                    and build.get('technical', {}).get('rendered_frame_visual_qa', {}).get('status') == 'reviewed'
                    and build.get('technical', {}).get('rendered_frame_visual_qa', {}).get('full_video_motion_diagnostics', {}).get('status') == 'passed'
                    and build.get('technical', {}).get('rendered_frame_visual_qa', {}).get('metadata_ocr_qa', {}).get('status') == 'passed'
                ),
                'visual_qa_status': build.get('technical', {}).get('rendered_frame_visual_qa', {}).get('status'),
                'motion_diagnostics_status': build.get('technical', {}).get('rendered_frame_visual_qa', {}).get('full_video_motion_diagnostics', {}).get('status'),
                'metadata_ocr_status': build.get('technical', {}).get('rendered_frame_visual_qa', {}).get('metadata_ocr_qa', {}).get('status'),
                'telegram_delivered': all(reel['delivery_steps'].get(step) is True for step in ('video', 'cover', 'message', 'publish_kit')),
                'qa_completed_at_ist': datetime.now(TZ).isoformat(timespec='seconds'),
            }
            existing_topic = next((item for item in reversed(history.setdefault('topics', [])) if item.get('reel_id') == reel['reel_id']), None)
            if existing_topic is not None:
                existing_topic.update(delivered_topic)
            else:
                history['topics'].append(delivered_topic)
                history['generated_count'] = int(history.get('generated_count', 0)) + 1
            producer.save_history(history)
            write_json(PENDING, pending)
            log(f"Delivered ready-for-review Reel {ordinal}/{len(pending['reels'])}: {concept['title']}")
            time.sleep(3)

        if all_missing:
            pending['status'] = 'gpu_failed'
            pending['gpu_error'] = '; '.join(all_missing)
            write_json(PENDING, pending)
            alert_failure('BINA SHOR KE output could not be mapped to all Reel scenes. No missing-scene Reel was sent. ' + '; '.join(all_missing))
            return 1
        pending['status'] = 'delivered'
        pending['completed_at_ist'] = datetime.now(TZ).isoformat(timespec='seconds')
        write_json(PENDING, pending)
        cleanup_resume_dataset(pending.get('resume_dataset_id'))
        log('Weekly batch delivered to Telegram for manual review. Nothing was published to Facebook automatically.')
        return 0



def poll_and_finalize() -> int:
    """Run a single poll/finalize attempt; persist failure and require explicit retry."""
    try:
        return _poll_and_finalize_impl()
    except Exception as exc:
        pending = load_json(PENDING, {}) or {}
        error_text = f'{type(exc).__name__}: {exc}'[:5000]
        if pending.get('status') in {'gpu_running', 'gpu_complete', 'finalizing'}:
            # A hard visual/rhythm defect is not a transient API error. Mark it rejected so the owner
            # can create a fresh concept/batch; retry-finalize would only reuse the same bad pixels.
            if any(marker in error_text.lower() for marker in ('critical visual defect', 'excessive speed change', 'too short')):
                pending['status'] = 'qa_rejected'
                pending['qa_rejection_reason'] = error_text
                pending['qa_rejected_at_ist'] = datetime.now(TZ).isoformat(timespec='seconds')
                history = producer.load_history()
                failed_reel_id = pending.get('active_finalizing_reel_id')
                for reel in pending.get('reels', []):
                    if reel.get('delivery_status') != 'delivered':
                        is_failed_reel = reel.get('reel_id') == failed_reel_id
                        history.setdefault('topics', []).append({
                            'title': reel.get('title', ''), 'theme': reel.get('theme', ''), 'pillar': reel.get('pillar', ''),
                            'generated_at': pending.get('created_at_ist'), 'planned_publish_at': reel.get('planned_publish_at'),
                            'status': 'qa_rejected_not_published' if is_failed_reel else 'batch_aborted_not_rendered',
                            'rejection_reason': error_text[:700] if is_failed_reel else 'Batch stopped before this Reel finished production.',
                        })
                producer.save_history(history)
            else:
                pending['status'] = 'finalize_failed'
                pending['finalize_error'] = error_text
                pending['finalize_failed_at_ist'] = datetime.now(TZ).isoformat(timespec='seconds')
            write_json(PENDING, pending)
        if pending.get('status') == 'qa_rejected':
            instruction = 'The reel was rejected for a hard visual/rhythm QA issue. Do NOT publish it and do NOT use retry-finalize (that would reuse the same scenes). After checking the report, run plan-one for a fresh concept or plan-week for a new batch.'
        else:
            instruction = 'Fix the transient/API issue, then manually run the workflow with action=retry-finalize. Previously delivered Telegram items are checkpointed to prevent duplicate delivery.'
        alert_failure('BINA SHOR KE finalization stopped safely. No paid fallback was used and nothing was auto-published. ' + instruction + ' Details: ' + error_text[:1300])
        raise


def resolve_dispatch_unknown(confirm_running: bool) -> int:
    """Resolve an ambiguous Kaggle push only after the owner checks Kaggle's run history."""
    pending = load_json(PENDING, {}) or {}
    if pending.get('status') != 'dispatch_unknown':
        raise RuntimeError(f"There is no ambiguous dispatch to resolve (status={pending.get('status', 'none')}).")
    pending['dispatch_resolution_at_ist'] = datetime.now(TZ).isoformat(timespec='seconds')
    pending['dispatch_resolution_source'] = 'owner_confirmed_from_kaggle_ui'
    if confirm_running:
        pending['status'] = 'gpu_running'
        pending['dispatch_resolution'] = 'owner_confirmed_new_run_exists'
        if pending.pop('resume_dispatch_attempt_pending', False):
            pending['resume_attempts'] = int(pending.get('resume_attempts', 0)) + 1
        if pending.pop('gpu_retry_dispatch_attempt_pending', False):
            pending['gpu_retry_attempts'] = int(pending.get('gpu_retry_attempts', 0)) + 1
            pending['gpu_retry_dispatched_at_ist'] = datetime.now(TZ).isoformat(timespec='seconds')
        pending.setdefault('dispatched_at_ist', pending.get('created_at_ist'))
        write_json(PENDING, pending)
        log('Owner confirmed the new Kaggle run exists. Polling will continue without dispatching another GPU job.')
    else:
        if pending.pop('resume_dispatch_attempt_pending', False):
            pending['status'] = 'gpu_checkpoint_saved'
        elif pending.pop('gpu_retry_dispatch_attempt_pending', False):
            pending['status'] = 'gpu_failed'
        else:
            pending['status'] = 'dispatch_failed'
        pending['dispatch_resolution'] = 'owner_confirmed_new_run_did_not_start'
        write_json(PENDING, pending)
        log('Owner confirmed no new Kaggle run started. A fresh plan can now be requested; no automatic re-dispatch occurred.')
    return 0


def retry_failed_gpu() -> int:
    """Retry the same Reel once for a narrowly classified worker compatibility failure."""
    pending = load_json(PENDING, {}) or {}
    if pending.get('status') != 'gpu_failed':
        raise RuntimeError(f"GPU retry requires status=gpu_failed (current={pending.get('status', 'none')}). Run poll once first if the old Kaggle job has not yet been collected.")
    retry_attempts = int(pending.get('gpu_retry_attempts', 0) or 0)
    if retry_attempts >= 2:
        raise RuntimeError('The two bounded same-Reel GPU retries have been used; inspect Kaggle worker diagnostics before any new batch.')
    if pending.get('resume_dataset_id') or int(pending.get('resume_scene_count', 0) or 0) > 0:
        raise RuntimeError('Verified scene checkpoints exist. Use resume-checkpoint instead of retry-gpu so completed scenes are reused.')
    if pending.get('checkpoint_save_error'):
        raise RuntimeError('Checkpoint persistence failed. Do not retry the GPU blindly; inspect the saved Kaggle output and checkpoint error first.')

    raw_error = pending.get('gpu_error', '')
    try:
        error_payload = json.loads(raw_error) if isinstance(raw_error, str) else raw_error
    except (TypeError, ValueError):
        error_payload = {}
    failure_text = json.dumps(raw_error, ensure_ascii=False).lower()
    known_ksampler_failure = (
        'ksampler schema changed' in failure_text or 'control_after_generate' in failure_text
    )
    known_hf_revision_failure = (
        'revisionnotfounderror' in failure_text
        and (
            'invalid rev id: text_encoders' in failure_text
            or 'invalid rev id: vae' in failure_text
        )
    )
    known_comfyui_timeout = (
        isinstance(error_payload, dict)
        and error_payload.get('error_type') == 'TimeoutError'
        and 'ComfyUI scene generation timed out after 2700s' in str(error_payload.get('error', ''))
        and error_payload.get('stage') == 'kaggle_gpu_render'
        and error_payload.get('manifest_id') == pending.get('job_id')
    )
    allowed_first_retry = retry_attempts == 0 and (known_ksampler_failure or known_hf_revision_failure)
    allowed_timeout_retry = retry_attempts == 1 and known_comfyui_timeout
    if not (allowed_first_retry or allowed_timeout_retry):
        raise RuntimeError(
            'GPU retry is restricted to the first classified KSampler/Hugging Face compatibility fix, '
            'or one additional same-manifest retry for the exact recorded 2700-second ComfyUI timeout '
            'after queue-aware diagnostics are installed. Other failures and attempt counts are refused.'
        )

    manifest = pending.get('manifest')
    if not isinstance(manifest, dict) or manifest.get('job_id') != pending.get('job_id') or not manifest.get('reels'):
        raise RuntimeError('Saved manifest is incomplete or does not match the pending job. Refusing to create a different Reel.')
    if any(reel.get('delivery_status') == 'delivered' for reel in pending.get('reels', [])):
        raise RuntimeError('At least one Reel from this manifest is already delivered. Refusing to retry the whole GPU manifest.')

    # Reconcile the worker manifest with the repository's corrected, immutable model snapshot pins.
    saved_lock = load_json(TOOLCHAIN_LOCK, {}) or {}
    if saved_lock.get('status') != 'locked':
        raise RuntimeError('The verified GPU toolchain lock is missing or not locked. Refusing a retry.')
    saved_model_revisions = saved_lock.get('model_revisions')
    required_model_keys = ('unet', 'clip', 'vae')
    if not isinstance(saved_model_revisions, dict) or not all(
        re.fullmatch(r'[0-9a-f]{40}', str(saved_model_revisions.get(key, '')))
        for key in required_model_keys
    ):
        raise RuntimeError(
            'The saved Hugging Face model lock is invalid. All UNet, CLIP and VAE revisions must be 40-character snapshot SHAs.'
        )
    previous_manifest_lock = manifest.get('toolchain_lock') if isinstance(manifest.get('toolchain_lock'), dict) else {}
    for key in ('comfyui_commit', 'comfyui_gguf_commit'):
        previous = previous_manifest_lock.get(key)
        current = saved_lock.get(key)
        if previous and previous != current:
            raise RuntimeError(f'Toolchain source mismatch for {key}; refusing to change the ComfyUI code version during a GPU retry.')
    manifest['toolchain_lock'] = {
        'comfyui_commit': saved_lock['comfyui_commit'],
        'comfyui_gguf_commit': saved_lock['comfyui_gguf_commit'],
        'model_revisions': {key: saved_model_revisions[key] for key in required_model_keys},
    }
    pending['manifest'] = manifest
    write_json(PENDING, pending)

    configure_kaggle_cli()
    recorded_kernel_id = str(pending.get('kaggle_kernel_id', '')).strip()
    expected_kernel_id = kaggle_kernel_id()
    if not recorded_kernel_id or recorded_kernel_id != expected_kernel_id:
        raise RuntimeError(f"Kaggle kernel identity mismatch: pending={recorded_kernel_id or 'missing'}, configured={expected_kernel_id}. Correct the account/slug before retrying.")
    remote_status, remote_output = kaggle_status(recorded_kernel_id)
    if remote_status not in {'ERROR', 'CANCELLED'}:
        raise RuntimeError(f"The previous Kaggle run is not confirmed terminal (status={remote_status}). No new GPU run was dispatched. {remote_output[-600:]}")

    kernel_dir = build_kaggle_kernel(manifest)
    retry_reason = (
        'Queue-aware ComfyUI prompt tracking, 90-minute scene timeout and preserved worker diagnostics; original Reel manifest retained.'
        if allowed_timeout_retry
        else 'Corrected Hugging Face snapshot SHA pins for Wan2.2 text encoder/VAE; original Reel manifest retained.'
        if known_hf_revision_failure
        else 'ComfyUI KSampler API schema compatibility fix; original Reel manifest retained.'
    )
    try:
        result = subprocess.run(
            kaggle_cli_command('kernels', 'push', '-p', str(kernel_dir)),
            text=True, capture_output=True, timeout=900,
        )
        console = (result.stdout or '') + '\n' + (result.stderr or '')
        push_failed = bool(result.returncode)
    except Exception as push_exc:
        console = f'{type(push_exc).__name__}: {push_exc}'
        push_failed = True

    if push_failed:
        try:
            after_status, after_output = kaggle_status(recorded_kernel_id)
        except Exception as status_exc:
            after_status, after_output = 'UNKNOWN', f'{type(status_exc).__name__}: {status_exc}'
        if after_status in {'RUNNING', 'QUEUED', 'COMPILING', 'CREATED'}:
            console = (console + '\n' + after_output)[-2500:]
            log('Kaggle shows the corrected retry is active despite a CLI error; preserving the existing Reel and polling it.')
        else:
            pending['status'] = 'dispatch_unknown'
            pending['gpu_retry_dispatch_attempt_pending'] = True
            pending['gpu_retry_dispatch_error'] = console[-2500:]
            pending['gpu_retry_remote_status'] = after_status
            pending['gpu_retry_reason'] = retry_reason
            write_json(PENDING, pending)
            alert_failure('BINA SHOR KE corrected GPU retry returned an ambiguous result. No second retry was sent. Inspect Kaggle run history, then use resolve-dispatch-running or resolve-dispatch-not-started.')
            return 1

    pending['gpu_retry_attempts'] = int(pending.get('gpu_retry_attempts', 0)) + 1
    pending['gpu_retry_dispatched_at_ist'] = datetime.now(TZ).isoformat(timespec='seconds')
    pending['gpu_retry_reason'] = retry_reason
    pending['status'] = 'gpu_running'
    pending['dispatched_at_ist'] = pending['gpu_retry_dispatched_at_ist']
    pending['dispatch_output'] = console[-2000:]
    write_json(PENDING, pending)
    log(f"Dispatched one corrected GPU retry for the same Reel manifest {pending.get('job_id')}; no new story was planned.")
    return 0


def resume_saved_checkpoint() -> int:
    pending = load_json(PENDING, {}) or {}
    if pending.get('status') != 'gpu_checkpoint_saved':
        raise RuntimeError(f"No saved, non-running checkpoint is available (status={pending.get('status', 'none')}).")
    return dispatch_checkpoint_resume(pending, automatic=False)


def repair_rhythm_finalize() -> int:
    """Re-finalize the same completed AI scenes after a narrowly bounded rhythm-only QA rejection.

    This action does not dispatch Kaggle GPU. It permits at most one <=3% pitch-preserving
    audio tempo fit for the specifically rejected scene, and refuses visual/other QA defects.
    """
    pending = load_json(PENDING, {}) or {}
    if pending.get('status') != 'qa_rejected':
        raise RuntimeError(f"Rhythm repair requires qa_rejected state (current={pending.get('status', 'none')}).")
    reason = str(pending.get('qa_rejection_reason', ''))
    match = re.search(r'AI scene (\d+) would require excessive speed change \(([0-9.]+)x\)', reason, re.IGNORECASE)
    if not match:
        raise RuntimeError('This QA rejection is not a supported AI-scene rhythm-only rejection. Do not bypass visual/technical QA.')
    scene_index = int(match.group(1))
    reported_ratio = float(match.group(2))
    if not 1.38 < reported_ratio <= 1.42:
        raise RuntimeError(f'Reported speed ratio {reported_ratio:.2f}x is outside the narrow repair window (1.38x–1.42x).')
    if int(pending.get('rhythm_repair_attempts', 0) or 0) >= 1:
        raise RuntimeError('The one allowed rhythm-only repair attempt has already been used.')
    reels = pending.get('reels') if isinstance(pending.get('reels'), list) else []
    reel_id = pending.get('active_finalizing_reel_id')
    failed_reel = next((item for item in reels if item.get('reel_id') == reel_id), None)
    if not failed_reel or failed_reel.get('delivery_status') == 'delivered':
        raise RuntimeError('Could not uniquely identify an undelivered Reel for rhythm-only repair.')
    concept = failed_reel.get('concept') if isinstance(failed_reel.get('concept'), dict) else {}
    beats = concept.get('beats') if isinstance(concept.get('beats'), list) else []
    if not 1 <= scene_index <= len(beats):
        raise RuntimeError('Rejected scene index does not match the saved Reel concept.')
    if not pending.get('kaggle_kernel_id') or pending.get('kaggle_kernel_id') != kaggle_kernel_id():
        raise RuntimeError('Kaggle kernel identity mismatch. Correct the account/slug before rhythm repair.')
    configure_kaggle_cli()
    remote_status, remote_output = kaggle_status(pending['kaggle_kernel_id'])
    if remote_status != 'COMPLETE':
        raise RuntimeError(f'Kaggle source run must be COMPLETE before rhythm repair (status={remote_status}). {remote_output[-600:]}')

    pending['rhythm_repair_attempts'] = int(pending.get('rhythm_repair_attempts', 0) or 0) + 1
    pending['rhythm_repair'] = {
        'status': 'in_progress',
        'scene_index': scene_index,
        'reported_original_ratio': reported_ratio,
        'max_audio_tempo': 1.03,
        'max_video_speed_ratio': 1.38,
        'method': 'pitch-preserving FFmpeg atempo on narration only; reuse completed Kaggle scene MP4s',
        'requested_at_ist': datetime.now(TZ).isoformat(timespec='seconds'),
        'new_kaggle_gpu_dispatch': False,
    }
    pending['status'] = 'gpu_complete'
    write_json(PENDING, pending)
    os.environ['BSK_ALLOW_TINY_VO_TEMPO_FIT'] = '1'
    log(f"Starting one bounded rhythm-only finalization repair for Reel {reel_id}, scene {scene_index}; reusing completed Kaggle MP4s, no GPU dispatch.")
    result = poll_and_finalize()
    latest = load_json(PENDING, {}) or {}
    if latest.get('status') == 'delivered':
        latest.setdefault('rhythm_repair', {})['status'] = 'completed'
        latest['rhythm_repair']['completed_at_ist'] = datetime.now(TZ).isoformat(timespec='seconds')
        write_json(PENDING, latest)
    return result



def repair_scene_5_voiceover_finalize() -> int:
    """Replace only Scene 5 narration for the known 1.67x rejection and re-finalize existing MP4s.

    This guarded recovery does not dispatch Kaggle GPU, does not rewrite the story arc, and
    preserves the six existing video clips. The replacement is intentionally 8 words to
    retain the producer's 7–12 word structural rule while shortening the recorded line.
    """
    pending = load_json(PENDING, {}) or {}
    if pending.get('status') != 'qa_rejected':
        raise RuntimeError(
            f'Scene 5 voiceover repair requires qa_rejected state (current={pending.get("status", "none")}).'
        )
    reason = str(pending.get('qa_rejection_reason', ''))
    # v3.7.4b's QA exception string omits the scene index: it stores
    # "AI scene would require excessive speed change (1.67x)". Accept this
    # exact generic form as well as an explicit Scene 5 form; never accept a
    # different numbered scene. The exact Reel/source-line and preceding
    # rhythm-repair guards below bind the generic message to this one case.
    match = re.search(
        r'AI scene(?:\s+5)?\s+would require excessive speed change\s*\(([0-9.]+)x\)',
        reason,
        re.IGNORECASE,
    )
    if not match:
        raise RuntimeError('This action is restricted to the recorded Scene 5 excessive-speed QA rejection.')
    reported_ratio = float(match.group(1))
    if not 1.66 <= reported_ratio <= 1.68:
        raise RuntimeError(f'Scene 5 ratio {reported_ratio:.2f}x is outside this targeted 1.67x repair case.')
    if int(pending.get('rhythm_repair_attempts', 0) or 0) != 1:
        raise RuntimeError('Scene 5 voiceover repair requires the one recorded prior rhythm-repair attempt.')
    if int(pending.get('scene_voiceover_repair_attempts', 0) or 0) >= 1:
        raise RuntimeError('The one allowed Scene 5 voiceover rewrite attempt has already been used.')

    reel_id = pending.get('active_finalizing_reel_id')
    if reel_id != 'reel_01_115742':
        raise RuntimeError('This one-time voiceover repair is restricted to Reel reel_01_115742.')
    reels = pending.get('reels') if isinstance(pending.get('reels'), list) else []
    reel = next((item for item in reels if item.get('reel_id') == reel_id), None)
    if not reel or reel.get('delivery_status') == 'delivered':
        raise RuntimeError('Could not uniquely identify an undelivered Reel for Scene 5 voiceover repair.')
    concept = reel.get('concept') if isinstance(reel.get('concept'), dict) else {}
    beats = concept.get('beats') if isinstance(concept.get('beats'), list) else []
    if concept.get('title') != 'सूखी छतरी' or len(beats) != 6:
        raise RuntimeError('Saved Reel concept does not match the expected six-scene सूखी छतरी manifest.')
    beat = beats[4]
    if int(beat.get('scene_index', 5)) != 5:
        raise RuntimeError('The fifth concept beat is not marked as scene_index 5.')
    original_line = 'सुमित चुपचाप बालकनी में अपनी भीगी कमीज़ निचोड़ रहा था।'
    replacement_line = 'सुमित ने चुपचाप अपनी भीगी कमीज़ निचोड़ दी।'
    if beat.get('voiceover') != original_line:
        raise RuntimeError('Scene 5 voiceover no longer matches the reviewed source line; refusing an unexpected overwrite.')
    replacement_words = len(replacement_line.split())
    if not 7 <= replacement_words <= 12:
        raise RuntimeError('The Scene 5 replacement must satisfy the factory 7–12 spoken-word rule.')

    expected_kernel_id = kaggle_kernel_id()
    recorded_kernel_id = str(pending.get('kaggle_kernel_id', '')).strip()
    if not recorded_kernel_id or recorded_kernel_id != expected_kernel_id:
        raise RuntimeError('Kaggle kernel identity mismatch. Correct the account/slug before voiceover repair.')
    configure_kaggle_cli()
    remote_status, remote_output = kaggle_status(recorded_kernel_id)
    if remote_status != 'COMPLETE':
        raise RuntimeError(
            f'Kaggle source run must be COMPLETE before Scene 5 voiceover repair '
            f'(status={remote_status}). {remote_output[-600:]}'
        )

    # Persist the exact narration change before TTS/finalization so a transient API failure
    # can be retried with retry-finalize without consuming another rewrite attempt.
    pending['scene_voiceover_repair_attempts'] = int(pending.get('scene_voiceover_repair_attempts', 0) or 0) + 1
    pending['scene_voiceover_repair'] = {
        'status': 'in_progress',
        'scene_index': 5,
        'reported_original_ratio': reported_ratio,
        'original_voiceover': original_line,
        'replacement_voiceover': replacement_line,
        'replacement_word_count': replacement_words,
        'method': 'regenerate Scene 5 Hindi TTS only; preserve all six completed Kaggle MP4 scenes; rerun full final QA',
        'requested_at_ist': datetime.now(TZ).isoformat(timespec='seconds'),
        'new_kaggle_gpu_dispatch': False,
    }
    if isinstance(pending.get('rhythm_repair'), dict):
        pending['rhythm_repair']['status'] = 'partial_failed_at_scene_5'
        pending['rhythm_repair']['followup_rejection_reason'] = reason[:1000]
    beat['voiceover'] = replacement_line
    pending['status'] = 'gpu_complete'
    pending.pop('finalize_error', None)
    write_json(PENDING, pending)

    # Keep the already-approved tiny <=3% pitch-preserving fit available for Scene 1,
    # which was the original borderline 1.39x rejection. No video speed is forced past 1.38x.
    os.environ['BSK_ALLOW_TINY_VO_TEMPO_FIT'] = '1'
    log(
        f'Starting one targeted Scene 5 voiceover rewrite for Reel {reel_id}; '
        'all six completed Kaggle MP4s will be reused, no GPU dispatch.'
    )
    result = poll_and_finalize()
    latest = load_json(PENDING, {}) or {}
    if latest.get('status') == 'delivered':
        latest.setdefault('scene_voiceover_repair', {})['status'] = 'completed'
        latest['scene_voiceover_repair']['completed_at_ist'] = datetime.now(TZ).isoformat(timespec='seconds')
        write_json(PENDING, latest)
    elif latest.get('status') == 'qa_rejected':
        latest.setdefault('scene_voiceover_repair', {})['status'] = 'qa_rejected_again'
        latest['scene_voiceover_repair']['final_qa_rejection_reason'] = str(latest.get('qa_rejection_reason', ''))[:1200]
        write_json(PENDING, latest)
    elif latest.get('status') == 'finalize_failed':
        latest.setdefault('scene_voiceover_repair', {})['status'] = 'finalize_failed_retryable'
        latest['scene_voiceover_repair']['finalize_error'] = str(latest.get('finalize_error', ''))[:1200]
        write_json(PENDING, latest)
    return result



def repair_scene_6_voiceover_finalize() -> int:
    """Replace only Scene 6 narration for the known 1.62x rejection and re-finalize existing MP4s.

    This one-time recovery is strictly bound to the already-repaired Scene 5 in Reel
    reel_01_115742. It reuses all six completed Kaggle MP4s and never dispatches GPU.
    """
    pending = load_json(PENDING, {}) or {}
    if pending.get('status') != 'qa_rejected':
        raise RuntimeError(
            f'Scene 6 voiceover repair requires qa_rejected state (current={pending.get("status", "none")}).'
        )
    reason = str(pending.get('qa_rejection_reason', ''))
    match = re.search(
        r'AI scene(?:\s+6)?\s+would require excessive speed change\s*\(([0-9.]+)x\)',
        reason,
        re.IGNORECASE,
    )
    if not match:
        raise RuntimeError('This action is restricted to the recorded Scene 6 excessive-speed QA rejection.')
    reported_ratio = float(match.group(1))
    if not 1.61 <= reported_ratio <= 1.63:
        raise RuntimeError(f'Scene 6 ratio {reported_ratio:.2f}x is outside this targeted 1.62x repair case.')
    if int(pending.get('rhythm_repair_attempts', 0) or 0) != 1:
        raise RuntimeError('Scene 6 voiceover repair requires the one recorded prior rhythm-repair attempt.')
    if int(pending.get('scene_voiceover_repair_attempts', 0) or 0) != 1:
        raise RuntimeError('Scene 6 voiceover repair requires the completed one-time Scene 5 rewrite first.')
    if int(pending.get('scene6_voiceover_repair_attempts', 0) or 0) >= 1:
        raise RuntimeError('The one allowed Scene 6 voiceover rewrite attempt has already been used.')

    reel_id = pending.get('active_finalizing_reel_id')
    if reel_id != 'reel_01_115742':
        raise RuntimeError('This one-time voiceover repair is restricted to Reel reel_01_115742.')
    reels = pending.get('reels') if isinstance(pending.get('reels'), list) else []
    reel = next((item for item in reels if item.get('reel_id') == reel_id), None)
    if not reel or reel.get('delivery_status') == 'delivered':
        raise RuntimeError('Could not uniquely identify an undelivered Reel for Scene 6 voiceover repair.')
    concept = reel.get('concept') if isinstance(reel.get('concept'), dict) else {}
    beats = concept.get('beats') if isinstance(concept.get('beats'), list) else []
    if concept.get('title') != 'सूखी छतरी' or len(beats) != 6:
        raise RuntimeError('Saved Reel concept does not match the expected six-scene सूखी छतरी manifest.')

    scene5_original_replacement = 'सुमित ने चुपचाप अपनी भीगी कमीज़ निचोड़ दी।'
    scene6_original = 'उसने सूखी छतरी टांग दी, मगर कमरा चुप ही रहा।'
    scene6_replacement = 'उसने सूखी छतरी टाँगी, मगर कमरा चुप रहा।'
    if int(beats[4].get('scene_index', 5)) != 5 or beats[4].get('voiceover') != scene5_original_replacement:
        raise RuntimeError('Scene 5 must retain the approved v3.7.4b replacement before Scene 6 repair.')
    if int(beats[5].get('scene_index', 6)) != 6 or beats[5].get('voiceover') != scene6_original:
        raise RuntimeError('Scene 6 voiceover no longer matches the reviewed source line; refusing an unexpected overwrite.')
    replacement_words = len(scene6_replacement.split())
    if not 7 <= replacement_words <= 12:
        raise RuntimeError('The Scene 6 replacement must satisfy the factory 7–12 word rule.')

    expected_kernel_id = kaggle_kernel_id()
    recorded_kernel_id = str(pending.get('kaggle_kernel_id', '')).strip()
    if not recorded_kernel_id or recorded_kernel_id != expected_kernel_id:
        raise RuntimeError('Kaggle kernel identity mismatch. Correct the account/slug before Scene 6 voiceover repair.')
    configure_kaggle_cli()
    remote_status, remote_output = kaggle_status(recorded_kernel_id)
    if remote_status != 'COMPLETE':
        raise RuntimeError(
            f'Kaggle source run must be COMPLETE before Scene 6 voiceover repair '
            f'(status={remote_status}). {remote_output[-600:]}'
        )

    pending['scene6_voiceover_repair_attempts'] = int(pending.get('scene6_voiceover_repair_attempts', 0) or 0) + 1
    pending['scene6_voiceover_repair'] = {
        'status': 'in_progress',
        'scene_index': 6,
        'reported_original_ratio': reported_ratio,
        'original_voiceover': scene6_original,
        'replacement_voiceover': scene6_replacement,
        'replacement_word_count': replacement_words,
        'method': 'regenerate Scene 6 Hindi TTS only; preserve all six completed Kaggle MP4 scenes; rerun full final QA',
        'requested_at_ist': datetime.now(TZ).isoformat(timespec='seconds'),
        'new_kaggle_gpu_dispatch': False,
    }
    if isinstance(pending.get('scene_voiceover_repair'), dict):
        pending['scene_voiceover_repair']['status'] = 'completed_with_followup_scene6_repair'
    beats[5]['voiceover'] = scene6_replacement
    pending['status'] = 'gpu_complete'
    pending.pop('finalize_error', None)
    write_json(PENDING, pending)

    os.environ['BSK_ALLOW_TINY_VO_TEMPO_FIT'] = '1'
    log(
        f'Starting one targeted Scene 6 voiceover rewrite for Reel {reel_id}; '
        'all six completed Kaggle MP4s will be reused, no GPU dispatch.'
    )
    result = poll_and_finalize()
    latest = load_json(PENDING, {}) or {}
    if latest.get('status') == 'delivered':
        latest.setdefault('scene6_voiceover_repair', {})['status'] = 'completed'
        latest['scene6_voiceover_repair']['completed_at_ist'] = datetime.now(TZ).isoformat(timespec='seconds')
        write_json(PENDING, latest)
    elif latest.get('status') == 'qa_rejected':
        latest.setdefault('scene6_voiceover_repair', {})['status'] = 'qa_rejected_again'
        latest['scene6_voiceover_repair']['final_qa_rejection_reason'] = str(latest.get('qa_rejection_reason', ''))[:1200]
        write_json(PENDING, latest)
    elif latest.get('status') == 'finalize_failed':
        latest.setdefault('scene6_voiceover_repair', {})['status'] = 'finalize_failed_retryable'
        latest['scene6_voiceover_repair']['finalize_error'] = str(latest.get('finalize_error', ''))[:1200]
        write_json(PENDING, latest)
    return result


def repair_scene_6_voiceover_followup_finalize() -> int:
    """Make one final, narrowly-scoped Scene 6 narration shortening for the 1.54x QA rejection.

    This follow-up is allowed only after the first Scene 6 rewrite was recorded and failed QA.
    It reuses the six completed Kaggle MP4s, changes only the Scene 6 narration, and dispatches no GPU.
    """
    pending = load_json(PENDING, {}) or {}
    if pending.get('status') != 'qa_rejected':
        raise RuntimeError(
            f'Scene 6 follow-up repair requires qa_rejected state (current={pending.get("status", "none")}).'
        )
    reason = str(pending.get('qa_rejection_reason', ''))
    match = re.search(
        r'AI scene(?:\s+6)?\s+would require excessive speed change\s*\(([0-9.]+)x\)',
        reason,
        re.IGNORECASE,
    )
    if not match:
        raise RuntimeError('This action is restricted to the recorded Scene 6 follow-up speed-change rejection.')
    reported_ratio = float(match.group(1))
    if not 1.53 <= reported_ratio <= 1.55:
        raise RuntimeError(f'Scene 6 ratio {reported_ratio:.2f}x is outside this targeted 1.54x follow-up case.')
    if int(pending.get('rhythm_repair_attempts', 0) or 0) != 1:
        raise RuntimeError('Scene 6 follow-up requires the one recorded prior rhythm-repair attempt.')
    if int(pending.get('scene_voiceover_repair_attempts', 0) or 0) != 1:
        raise RuntimeError('Scene 6 follow-up requires the completed one-time Scene 5 rewrite first.')
    if int(pending.get('scene6_voiceover_repair_attempts', 0) or 0) != 1:
        raise RuntimeError('Scene 6 follow-up requires exactly one completed first Scene 6 rewrite.')
    if int(pending.get('scene6_voiceover_followup_attempts', 0) or 0) >= 1:
        raise RuntimeError('The one allowed Scene 6 follow-up rewrite attempt has already been used.')
    prior_repair = pending.get('scene6_voiceover_repair')
    if not isinstance(prior_repair, dict) or prior_repair.get('status') not in {'qa_rejected_again', 'in_progress'}:
        raise RuntimeError('The prior Scene 6 rewrite must be recorded as qa_rejected_again or in_progress after its exact 1.54x QA rejection.')

    reel_id = pending.get('active_finalizing_reel_id')
    if reel_id != 'reel_01_115742':
        raise RuntimeError('This follow-up is restricted to Reel reel_01_115742.')
    reels = pending.get('reels') if isinstance(pending.get('reels'), list) else []
    reel = next((item for item in reels if item.get('reel_id') == reel_id), None)
    if not reel or reel.get('delivery_status') == 'delivered':
        raise RuntimeError('Could not uniquely identify an undelivered Reel for Scene 6 follow-up.')
    concept = reel.get('concept') if isinstance(reel.get('concept'), dict) else {}
    beats = concept.get('beats') if isinstance(concept.get('beats'), list) else []
    if concept.get('title') != 'सूखी छतरी' or len(beats) != 6:
        raise RuntimeError('Saved Reel concept does not match the expected six-scene सूखी छतरी manifest.')

    scene5_required = 'सुमित ने चुपचाप अपनी भीगी कमीज़ निचोड़ दी।'
    scene6_previous = 'उसने सूखी छतरी टाँगी, मगर कमरा चुप रहा।'
    scene6_replacement = 'उसने छतरी टाँगी, मगर कमरा चुप रहा।'
    if int(beats[4].get('scene_index', 5)) != 5 or beats[4].get('voiceover') != scene5_required:
        raise RuntimeError('Scene 5 must retain its approved replacement before Scene 6 follow-up.')
    if int(beats[5].get('scene_index', 6)) != 6 or beats[5].get('voiceover') != scene6_previous:
        raise RuntimeError('Scene 6 voiceover does not match the exact prior replacement; refusing an unexpected overwrite.')
    replacement_words = len(scene6_replacement.split())
    if replacement_words != 7:
        raise RuntimeError('The Scene 6 follow-up must be exactly seven whitespace-separated words.')

    expected_kernel_id = kaggle_kernel_id()
    recorded_kernel_id = str(pending.get('kaggle_kernel_id', '')).strip()
    if not recorded_kernel_id or recorded_kernel_id != expected_kernel_id:
        raise RuntimeError('Kaggle kernel identity mismatch. Correct the account/slug before Scene 6 follow-up.')
    configure_kaggle_cli()
    remote_status, remote_output = kaggle_status(recorded_kernel_id)
    if remote_status != 'COMPLETE':
        raise RuntimeError(
            f'Kaggle source run must be COMPLETE before Scene 6 follow-up '
            f'(status={remote_status}). {remote_output[-600:]}'
        )

    pending['scene6_voiceover_followup_attempts'] = int(pending.get('scene6_voiceover_followup_attempts', 0) or 0) + 1
    pending['scene6_voiceover_followup'] = {
        'status': 'in_progress',
        'scene_index': 6,
        'reported_original_ratio': reported_ratio,
        'original_voiceover': scene6_previous,
        'replacement_voiceover': scene6_replacement,
        'replacement_word_count': replacement_words,
        'method': 'regenerate Scene 6 Hindi TTS only; reuse all six completed Kaggle MP4s; rerun full final QA; no GPU dispatch',
        'requested_at_ist': datetime.now(TZ).isoformat(timespec='seconds'),
        'new_kaggle_gpu_dispatch': False,
    }
    prior_repair['status'] = 'completed_with_followup_rewrite'
    beats[5]['voiceover'] = scene6_replacement
    pending['status'] = 'gpu_complete'
    pending.pop('finalize_error', None)
    write_json(PENDING, pending)

    os.environ['BSK_ALLOW_TINY_VO_TEMPO_FIT'] = '1'
    log(
        f'Starting one final bounded Scene 6 voiceover shortening for Reel {reel_id}; '
        'all six completed Kaggle MP4s will be reused, no GPU dispatch.'
    )
    try:
        result = poll_and_finalize()
    except Exception:
        # poll_and_finalize persists qa_rejected/finalize_failed and then re-raises.
        # Persist the repair outcome here as well; otherwise the attempt remains
        # misleadingly marked in_progress and recovery gates cannot diagnose it.
        latest = load_json(PENDING, {}) or {}
        if latest.get('status') == 'qa_rejected':
            latest.setdefault('scene6_voiceover_followup', {})['status'] = 'qa_rejected_again'
            latest['scene6_voiceover_followup']['final_qa_rejection_reason'] = str(latest.get('qa_rejection_reason', ''))[:1200]
            write_json(PENDING, latest)
        elif latest.get('status') == 'finalize_failed':
            latest.setdefault('scene6_voiceover_followup', {})['status'] = 'finalize_failed_retryable'
            latest['scene6_voiceover_followup']['finalize_error'] = str(latest.get('finalize_error', ''))[:1200]
            write_json(PENDING, latest)
        raise
    latest = load_json(PENDING, {}) or {}
    if latest.get('status') == 'delivered':
        latest.setdefault('scene6_voiceover_followup', {})['status'] = 'completed'
        latest['scene6_voiceover_followup']['completed_at_ist'] = datetime.now(TZ).isoformat(timespec='seconds')
        write_json(PENDING, latest)
    elif latest.get('status') == 'qa_rejected':
        latest.setdefault('scene6_voiceover_followup', {})['status'] = 'qa_rejected_again'
        latest['scene6_voiceover_followup']['final_qa_rejection_reason'] = str(latest.get('qa_rejection_reason', ''))[:1200]
        write_json(PENDING, latest)
    elif latest.get('status') == 'finalize_failed':
        latest.setdefault('scene6_voiceover_followup', {})['status'] = 'finalize_failed_retryable'
        latest['scene6_voiceover_followup']['finalize_error'] = str(latest.get('finalize_error', ''))[:1200]
        write_json(PENDING, latest)
    return result


def rebuild_rejected_timing() -> int:
    """Re-finalize one timing-only QA rejection using the existing completed Kaggle scenes.

    This is deliberately narrow: it cannot bypass visual/technical QA, cannot dispatch
    a new GPU job, is limited to one undelivered Reel, and can run only once.
    """
    pending = load_json(PENDING, {}) or {}
    if pending.get('status') != 'qa_rejected':
        raise RuntimeError(
            f"Timing rebuild requires qa_rejected state (current={pending.get('status', 'none')})."
        )
    reason = str(pending.get('qa_rejection_reason', ''))
    lowered = reason.lower()
    if 'would require excessive speed change' not in lowered:
        raise RuntimeError('This recovery is only for the recorded narration/video timing rejection.')
    if any(marker in lowered for marker in ('critical visual defect', 'too short', 'black frame', 'freeze defect')):
        raise RuntimeError('A visual, black-frame, freeze or too-short rejection cannot use timing-only recovery.')
    if int(pending.get('timing_rebuild_attempts', 0) or 0) >= 1:
        raise RuntimeError('The one permitted timing-only rebuild has already been used.')

    reels = pending.get('reels') if isinstance(pending.get('reels'), list) else []
    if len(reels) != 1:
        raise RuntimeError('Timing-only recovery is restricted to a single-Reel GPU job.')
    reel = reels[0]
    reel_id = pending.get('active_finalizing_reel_id')
    if not reel_id or reel.get('reel_id') != reel_id or reel.get('delivery_status') == 'delivered':
        raise RuntimeError('The active undelivered Reel could not be uniquely verified.')

    configure_kaggle_cli()
    remote_status, remote_output = kaggle_status(pending.get('kaggle_kernel_id', ''))
    if remote_status != 'COMPLETE':
        raise RuntimeError(
            f'Existing Kaggle output is not confirmed COMPLETE (status={remote_status}); '
            f'no new GPU job was started. {remote_output[-800:]}'
        )

    pending['timing_rebuild_attempts'] = int(pending.get('timing_rebuild_attempts', 0) or 0) + 1
    pending['timing_rebuild'] = {
        'status': 'in_progress',
        'reel_id': reel_id,
        'original_qa_rejection_reason': reason[:1200],
        'requested_at_ist': datetime.now(TZ).isoformat(timespec='seconds'),
        'new_kaggle_gpu_dispatch': False,
        'method': 'reuse the completed six-scene Kaggle output; apply bounded video timing and audio padding in finalization',
    }
    pending['status'] = 'gpu_complete'
    pending.pop('qa_rejection_reason', None)
    pending.pop('qa_rejected_at_ist', None)
    write_json(PENDING, pending)
    log(f'Rebuilding timing-only QA rejection for {reel_id} from existing Kaggle output; no GPU dispatch.')

    try:
        result = poll_and_finalize()
    except Exception:
        latest = load_json(PENDING, {}) or {}
        recovery = latest.setdefault('timing_rebuild', {})
        recovery['status'] = (
            'qa_rejected_again' if latest.get('status') == 'qa_rejected'
            else 'finalize_failed' if latest.get('status') == 'finalize_failed'
            else 'recovery_failed'
        )
        recovery['finished_at_ist'] = datetime.now(TZ).isoformat(timespec='seconds')
        recovery['final_qa_rejection_reason'] = str(latest.get('qa_rejection_reason', ''))[:1200]
        write_json(PENDING, latest)
        raise

    latest = load_json(PENDING, {}) or {}
    recovery = latest.setdefault('timing_rebuild', {})
    recovery['status'] = 'delivered' if latest.get('status') == 'delivered' else (
        'qa_rejected_again' if latest.get('status') == 'qa_rejected' else 'finalize_failed'
    )
    recovery['finished_at_ist'] = datetime.now(TZ).isoformat(timespec='seconds')
    recovery['final_qa_rejection_reason'] = str(latest.get('qa_rejection_reason', ''))[:1200]
    write_json(PENDING, latest)
    return result


def retry_finalize() -> int:
    pending = load_json(PENDING, {}) or {}
    if pending.get('status') not in {'finalize_failed', 'finalizing', 'gpu_failed'}:
        raise RuntimeError(f"There is no failed or interrupted finalization to retry (status={pending.get('status', 'none')}).")
    # A GPU output failure itself cannot be repaired by re-running the finalizer. Only retry when Kaggle completed.
    status, raw = kaggle_status(pending.get('kaggle_kernel_id', ''))
    if status != 'COMPLETE':
        raise RuntimeError(f"Kaggle kernel is not COMPLETE (status={status}). Inspect the GPU worker and use plan-week only after resolving the prior batch. {raw[-800:]}")
    pending['status'] = 'gpu_running'
    pending['retry_finalization_count'] = int(pending.get('retry_finalization_count', 0)) + 1
    pending['retry_requested_at_ist'] = datetime.now(TZ).isoformat(timespec='seconds')
    pending.pop('finalize_error', None)
    write_json(PENDING, pending)
    log('Explicit manual finalization retry requested. Previously delivered Reels will be skipped.')
    return poll_and_finalize()

def self_test() -> int:
    # Offline checks for dispatch manifest integrity and API graph fields without GPU/API calls.
    import importlib.util
    runner_path = ROOT / 'scripts' / 'kaggle_gpu_runner.py'
    runner_source = runner_path.read_text(encoding='utf-8').replace('__MANIFEST_JSON__', "json.loads('{}')")
    tmp_runner = ROOT / 'scripts' / '_kaggle_gpu_runner_test_import.py'
    tmp_runner.write_text(runner_source, encoding='utf-8')
    try:
        spec = importlib.util.spec_from_file_location('bsk_kaggle_runner_test', tmp_runner)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        tmp_runner.unlink(missing_ok=True)
    build_api_workflow = module.build_api_workflow
    mock_object_info = {}
    schema = {
        'UnetLoaderGGUF': ['unet_name'],
        'CLIPLoader': ['clip_name', 'type', 'device'], 'VAELoader': ['vae_name'],
        'ModelSamplingSD3': ['model', 'shift'], 'CLIPTextEncode': ['text', 'clip'],
        'Wan22ImageToVideoLatent': ['width', 'height', 'length', 'batch_size', 'vae', 'start_image'],
        'KSampler': ['seed', 'steps', 'cfg', 'sampler_name', 'scheduler', 'denoise', 'model', 'positive', 'negative', 'latent_image'],
        'VAEDecode': ['samples', 'vae'], 'CreateVideo': ['images', 'fps'],
        'SaveVideo': ['video', 'filename_prefix', 'format', 'codec'],
    }
    for node, keys in schema.items():
        required_keys = [k for k in keys if not (node == 'Wan22ImageToVideoLatent' and k == 'start_image')]
        optional_keys = ['start_image'] if node == 'Wan22ImageToVideoLatent' else []
        mock_object_info[node] = {'input': {'required': {k: [] for k in required_keys}, 'optional': {k: [] for k in optional_keys}}}
    demo = {'reel_id': 'reel_01_test', 'visual_bible': 'Natural practical light, consistent charcoal jacket, anonymous partial profile.', 'beats': []}
    beat = {'video_prompt': 'Photoreal vertical close-up of a phone placed on a scratched wooden desk, hand slowly turns it face down, warm practical lamp light, subtle handheld movement, realistic texture, no readable text or logos.'}
    graph = build_api_workflow(mock_object_info, beat, demo, 1, 'bsk/reel_01_test/scene_01')
    if len(graph) != 11 or graph['55']['inputs']['length'] != 81 or graph['55']['inputs']['width'] != 704 or graph['55']['inputs']['height'] != 1280:
        raise RuntimeError('Offline GPU graph validation failed.')
    pending = load_json(PENDING, {})
    if pending and pending.get('status') in {'dispatching', 'gpu_running'} and not pending.get('manifest', {}).get('reels'):
        raise RuntimeError('Pending state exists without a Reel manifest.')
    log('OFFLINE STUDIO PREFLIGHT PASSED: graph schema, 720p portrait dimensions, 81-frame (~3.4s) clip, pending state shape. No API keys/network/GPU used.')
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['plan', 'plan-one', 'poll-finalize', 'retry-finalize', 'repair-rhythm-finalize', 'repair-scene-voiceover-finalize', 'repair-scene-6-voiceover-finalize', 'repair-scene-6-voiceover-followup-finalize', 'rebuild-rejected-timing', 'retry-gpu', 'resume-checkpoint', 'resolve-dispatch-running', 'resolve-dispatch-not-started', 'preflight'])
    args = parser.parse_args()
    try:
        if args.command == 'preflight':
            return self_test()
        if args.command == 'plan':
            return plan_week(3)
        if args.command == 'plan-one':
            return plan_week(1)
        if args.command == 'retry-finalize':
            return retry_finalize()
        if args.command == 'repair-rhythm-finalize':
            return repair_rhythm_finalize()
        if args.command == 'repair-scene-voiceover-finalize':
            return repair_scene_5_voiceover_finalize()
        if args.command == 'repair-scene-6-voiceover-finalize':
            return repair_scene_6_voiceover_finalize()
        if args.command == 'repair-scene-6-voiceover-followup-finalize':
            return repair_scene_6_voiceover_followup_finalize()
        if args.command == 'rebuild-rejected-timing':
            return rebuild_rejected_timing()
        if args.command == 'retry-gpu':
            return retry_failed_gpu()
        if args.command == 'resume-checkpoint':
            return resume_saved_checkpoint()
        if args.command == 'resolve-dispatch-running':
            return resolve_dispatch_unknown(confirm_running=True)
        if args.command == 'resolve-dispatch-not-started':
            return resolve_dispatch_unknown(confirm_running=False)
        return poll_and_finalize()
    except Exception as exc:
        log(f'ERROR: {type(exc).__name__}: {exc}')
        alert_failure(f'BINA SHOR KE Studio pipeline error ({args.command}): {type(exc).__name__}: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
