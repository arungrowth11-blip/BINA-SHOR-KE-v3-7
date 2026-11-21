#!/usr/bin/env python3
"""Kaggle GPU worker. Manifest is injected by studio_pipeline.py before a Kaggle run."""
from __future__ import annotations
import hashlib
import json
import re
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

MANIFEST = __MANIFEST_JSON__
if not isinstance(MANIFEST, dict):
    raise TypeError(f'Injected MANIFEST must be a dict, got {type(MANIFEST).__name__}.')
WORK = Path('/kaggle/working')
COMFY = WORK / 'ComfyUI'
OUT = WORK / 'bsk_output'
KAGGLE_INPUT_ROOT = Path('/kaggle/input')
HF_CACHE = Path('/kaggle/temp/bsk-hf-cache')
NEGATIVE = (
    "text, subtitles, caption, watermark, logo, words, signs with readable text, "
    "photoreal skin pores, live-action footage, glossy plastic 3D, waxy face, over-smoothing, over-sharpening, "
    "warped architecture, flicker, strobing, jitter, rubber motion, morphing objects, "
    "extra fingers, malformed hands, fused fingers, duplicated people, distorted faces, "
    "unrealistic physics, unnatural reflections, blurry, low-resolution, oversaturated, inconsistent clothing"
)

PRIMARY_25D_PIPELINE = "primary_25d_motion_comic_v2"
LEGACY_25D_PIPELINE = "hybrid_25d_motion_comic_v1"


def is_25d_pipeline(value) -> bool:
    return str(value or "") in {PRIMARY_25D_PIPELINE, LEGACY_25D_PIPELINE}


def run(cmd, cwd=None, timeout=1800):
    p = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f"Command failed ({p.returncode}): {' '.join(map(str, cmd))}\n{p.stdout[-5000:]}")
    return p.stdout


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def verify_model_file_sha256(path: Path, expected_sha256: str, model_name: str) -> str:
    """Verify a downloaded model blob against an independently published file digest."""
    expected = str(expected_sha256 or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError(f"Invalid expected SHA-256 for model {model_name}: {expected!r}")
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(
            f"{model_name} model file SHA-256 mismatch: expected {expected}, got {actual}."
        )
    return actual


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def valid_scene_file(path: Path, max_duration: float = 8.0) -> tuple[bool, float]:
    if not path.is_file() or path.stat().st_size < 100_000 or shutil.which('ffprobe') is None:
        return False, 0.0
    probe = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=45,
    )
    if probe.returncode:
        return False, 0.0
    try:
        duration = float(probe.stdout.strip())
    except (TypeError, ValueError):
        return False, 0.0
    return 2.5 <= duration <= max_duration, duration


def checkpoint_entries_from_output(result_manifest: dict) -> list[dict]:
    """Rebuild a safe inventory from files actually present, including on worker failure."""
    known = {(str(x.get('reel_id')), int(x.get('scene_index', 0))): x for x in result_manifest.get('scenes', []) if x.get('reel_id') and x.get('scene_index')}
    entries = []
    for reel in MANIFEST.get('reels', []):
        reel_id = str(reel.get('reel_id', ''))
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', reel_id):
            continue
        for scene_index in range(1, len(reel.get('beats', [])) + 1):
            path = OUT / reel_id / f'scene_{scene_index:02d}.mp4'
            is_valid, duration = valid_scene_file(path)
            if not is_valid:
                continue
            old = known.get((reel_id, scene_index), {})
            entries.append({
                'reel_id': reel_id, 'scene_index': scene_index,
                'file': f'{reel_id}__scene_{scene_index:02d}.mp4',
                'relative_path': str(path.relative_to(OUT)),
                'bytes': path.stat().st_size, 'sha256': sha256_file(path),
                'duration_seconds': round(duration, 3),
                'generation_elapsed_seconds': float(old.get('generation_elapsed_seconds', 0) or 0),
                'prompt_id': old.get('prompt_id'),
            })
    return entries


def write_checkpoint_manifest(result_manifest: dict, status: str):
    """Atomically inventory hash-verified MP4 scenes or first-class still images."""
    if any(is_25d_pipeline(reel.get('visual_pipeline')) for reel in MANIFEST.get('reels', [])):
        entries = []
        from PIL import Image
        for reel in MANIFEST.get('reels', []):
            reel_id = str(reel.get('reel_id', ''))
            for scene_index in range(1, len(reel.get('beats', [])) + 1):
                path = OUT / reel_id / f'scene_{scene_index:02d}.png'
                if not path.is_file() or path.stat().st_size < 100_000:
                    continue
                try:
                    with Image.open(path) as image:
                        image.verify()
                    with Image.open(path) as image:
                        width, height = image.size
                except Exception:
                    continue
                entries.append({
                    'reel_id': reel_id, 'scene_index': scene_index,
                    'file': f'{reel_id}__scene_{scene_index:02d}.png',
                    'relative_path': str(path.relative_to(OUT)),
                    'bytes': path.stat().st_size, 'sha256': sha256_file(path),
                    'media_type': 'image/png', 'width': width, 'height': height,
                })
        checkpoint = {
            'schema_version': 2, 'job_id': MANIFEST.get('job_id'), 'status': status,
            'model': 'FLUX.1-schnell Q4_K_S GGUF + Depth Anything V2',
            'expected_scenes': sum(len(r.get('beats', [])) for r in MANIFEST.get('reels', [])),
            'completed_scenes': len(entries), 'scenes': entries,
            'updated_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        }
    else:
        entries = checkpoint_entries_from_output(result_manifest)
        checkpoint = {
            'schema_version': 1, 'job_id': MANIFEST.get('job_id'), 'status': status,
            'model': 'Wan2.2 TI2V-5B Q4_K_M GGUF',
            'expected_scenes': sum(len(r.get('beats', [])) for r in MANIFEST.get('reels', [])),
            'completed_scenes': len(entries), 'scenes': entries,
            'updated_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        }
    write_json(OUT / 'gpu_checkpoint_manifest.json', checkpoint)
    return entries


def restore_checkpoint_dataset(result_manifest: dict):
    """Restore only manifest-listed, SHA-256 verified video or PNG checkpoints."""
    dataset_id = str(MANIFEST.get('resume_dataset_id', '')).strip()
    if not dataset_id:
        return
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,50}/[A-Za-z0-9_-]{1,50}', dataset_id):
        raise RuntimeError('Resume dataset id has an invalid Kaggle owner/slug format.')
    source = KAGGLE_INPUT_ROOT / dataset_id.split('/', 1)[1]
    index_path = source / 'checkpoint_manifest.json'
    if not index_path.is_file():
        raise RuntimeError(f'Resume checkpoint dataset is mounted but {index_path.name} is missing.')
    checkpoint = json.loads(index_path.read_text(encoding='utf-8'))
    if checkpoint.get('job_id') != MANIFEST.get('job_id'):
        raise RuntimeError('Resume checkpoint belongs to a different production job; refusing to mix scene files.')
    allowed = {str(r['reel_id']): len(r.get('beats', [])) for r in MANIFEST.get('reels', [])}
    restored = []
    from PIL import Image
    for item in checkpoint.get('scenes', []):
        reel_id = str(item.get('reel_id', ''))
        scene_index = int(item.get('scene_index', 0))
        if reel_id not in allowed or not (1 <= scene_index <= allowed[reel_id]):
            continue
        image_checkpoint = item.get('media_type') == 'image/png'
        extension = '.png' if image_checkpoint else '.mp4'
        filename = f'{reel_id}__scene_{scene_index:02d}{extension}'
        src = source / filename
        if not src.is_file() or src.stat().st_size != int(item.get('bytes', -1)):
            continue
        if sha256_file(src) != item.get('sha256'):
            continue
        if image_checkpoint:
            try:
                with Image.open(src) as image:
                    image.verify()
                with Image.open(src) as image:
                    width, height = image.size
                if (width, height) != (704, 1280):
                    continue
            except Exception:
                continue
            dest = OUT / reel_id / f'scene_{scene_index:02d}.png'
        else:
            ok, duration = valid_scene_file(src)
            if not ok:
                continue
            dest = OUT / reel_id / f'scene_{scene_index:02d}.mp4'
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        row = {
            'reel_id': reel_id, 'scene_index': scene_index,
            'path': str(dest.relative_to(WORK)), 'bytes': dest.stat().st_size,
            'media_type': 'image/png' if image_checkpoint else 'video/mp4',
            'sha256': sha256_file(dest), 'restored_from_checkpoint': True,
        }
        if image_checkpoint:
            row.update({'width': width, 'height': height})
        else:
            row.update({
                'duration_seconds_target': float(item.get('duration_seconds_target', duration)),
                'generation_elapsed_seconds': float(item.get('generation_elapsed_seconds', 0) or 0),
                'prompt_id': item.get('prompt_id'),
            })
        restored.append(row)
    result_manifest['scenes'].extend(restored)
    entries = write_checkpoint_manifest(result_manifest, 'resumed')
    print(f'Restored {len(entries)} verified scene checkpoints from private Kaggle dataset {dataset_id}.', flush=True)


def send_failure_file(exc: Exception, result_manifest: dict | None = None):
    OUT.mkdir(parents=True, exist_ok=True)
    if result_manifest is not None:
        try:
            write_checkpoint_manifest(result_manifest, 'partial')
        except Exception as checkpoint_exc:
            print(f'Checkpoint inventory warning: {checkpoint_exc}', flush=True)
    diagnostic = {
        'status': 'failed', 'error_type': type(exc).__name__, 'error': str(exc)[:5000],
        'stage': 'kaggle_gpu_render', 'manifest_id': MANIFEST.get('job_id'),
    }
    if isinstance(result_manifest, dict) and isinstance(result_manifest.get('current_scene'), dict):
        diagnostic['current_scene'] = result_manifest['current_scene']
    # Preserve the ComfyUI server tail in Kaggle output; the prior worker deleted it on exit,
    # leaving only a generic timeout and making GPU failures impossible to diagnose.
    server_log = WORK / 'comfy_server.log'
    if server_log.is_file():
        try:
            diagnostic['comfy_server_log_tail'] = server_log.read_text(encoding='utf-8', errors='replace')[-20000:]
        except OSError as log_exc:
            diagnostic['comfy_server_log_read_error'] = str(log_exc)[:500]
    write_json(OUT / 'GPU_JOB_ERROR.json', diagnostic)


def clone_and_pin_repo(repo_url: str, destination: Path, revision: str | None) -> str:
    """Clone a repo, then use a previously proven commit when one is recorded."""
    if not destination.exists():
        run(['git', 'clone', '--depth', '1', repo_url, str(destination)], timeout=900)
    if revision:
        current = run(['git', 'rev-parse', 'HEAD'], cwd=destination, timeout=60).strip()
        if current != revision:
            # Fail closed if the previously proven object is no longer fetchable.
            run(['git', 'fetch', '--depth', '1', 'origin', revision], cwd=destination, timeout=900)
            run(['git', 'checkout', '--detach', revision], cwd=destination, timeout=120)
    return run(['git', 'rev-parse', 'HEAD'], cwd=destination, timeout=60).strip()



def runtime_package_versions() -> dict[str, str]:
    """Capture packages most likely to alter GPU graph/model behavior between runs."""
    from importlib.metadata import PackageNotFoundError, version
    distributions = (
        "torch", "torchvision", "torchaudio", "numpy", "Pillow", "safetensors",
        "gguf", "transformers", "accelerate", "huggingface-hub", "sentencepiece",
        "tokenizers", "einops", "torchsde", "requests", "opencv-python", "opencv-python-headless",
    )
    observed = {}
    for package in distributions:
        try:
            observed[package] = version(package)
        except PackageNotFoundError:
            observed[package] = "not-installed"
    return observed

def hf_cache_revision(path) -> str:
    """Extract the immutable Hugging Face snapshot SHA, not the model subfolder name."""
    candidate = os.path.abspath(os.fspath(path))

    def from_snapshot(raw_path: str) -> str | None:
        parts = Path(raw_path).parts
        for index, part in enumerate(parts[:-1]):
            if part == 'snapshots':
                revision = parts[index + 1]
                if re.fullmatch(r'[0-9a-f]{40}', revision):
                    return revision
                raise RuntimeError(
                    f'Hugging Face cache snapshot has an invalid revision component: {revision!r}'
                )
        return None

    revision = from_snapshot(candidate)
    if revision:
        return revision
    if os.path.islink(candidate):
        target = os.readlink(candidate)
        if not os.path.isabs(target):
            target = os.path.join(os.path.dirname(candidate), target)
        revision = from_snapshot(os.path.abspath(target))
        if revision:
            return revision
    raise RuntimeError(
        f'Could not determine a 40-character Hugging Face snapshot SHA from model path: {candidate}'
    )


def install_comfyui():
    import torch
    from huggingface_hub import hf_hub_download, model_info

    primary_image_first = bool(MANIFEST.get('reels')) and all(
        str(reel.get('visual_pipeline') or '') == PRIMARY_25D_PIPELINE
        for reel in MANIFEST.get('reels', [])
    )
    if any(
        is_25d_pipeline(reel.get('visual_pipeline'))
        and str(reel.get('visual_pipeline') or '') != PRIMARY_25D_PIPELINE
        for reel in MANIFEST.get('reels', [])
    ):
        # Legacy hybrid manifests are Wan video-first and must keep their original
        # ComfyUI graph/model family. They are not aliases for image-first production.
        primary_image_first = False
    if not torch.cuda.is_available():
        raise RuntimeError('Kaggle did not provide a CUDA GPU. No CPU fallback was attempted because it would be too slow and low quality.')
    gpu_name = torch.cuda.get_device_name(0)
    total_vram_gib = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    minimum_vram_gib = 12.0 if primary_image_first else 7.5
    if total_vram_gib < minimum_vram_gib:
        raise RuntimeError(
            f'GPU {gpu_name} has only {total_vram_gib:.1f} GiB VRAM; '
            f'the selected {"FLUX image-first" if primary_image_first else "legacy Wan"} mode '
            f'requires at least {minimum_vram_gib:.1f} GiB as a safety floor. No CPU or paid fallback was attempted.'
        )
    free = shutil.disk_usage(WORK).free / (1024**3)
    min_disk = 18.0 if primary_image_first else 14.5
    if free < min_disk:
        raise RuntimeError(f'Only {free:.1f} GiB free disk space; the selected open-weight model, text encoders, VAE and depth model need about {min_disk:.1f} GiB plus runtime/output. Aborting before download.')
    print(f'GPU={gpu_name}; total_vram={total_vram_gib:.1f} GiB; free_disk={free:.1f} GiB; mode={"image-first-primary-2.5d" if primary_image_first else "legacy-wan-video"}', flush=True)

    lock = MANIFEST.get('toolchain_lock') if isinstance(MANIFEST.get('toolchain_lock'), dict) else {}
    comfy_sha = clone_and_pin_repo(
        'https://github.com/Comfy-Org/ComfyUI.git', COMFY, lock.get('comfyui_commit')
    )
    (COMFY / 'custom_nodes').mkdir(parents=True, exist_ok=True)
    gguf_dir = COMFY / 'custom_nodes' / 'ComfyUI-GGUF'
    gguf_sha = clone_and_pin_repo(
        'https://github.com/city96/ComfyUI-GGUF.git', gguf_dir, lock.get('comfyui_gguf_commit')
    )
    os.environ['BSK_COMFYUI_SHA'] = comfy_sha
    os.environ['BSK_COMFYUI_GGUF_SHA'] = gguf_sha

    # Install node dependencies while preserving Kaggle's CUDA-enabled Torch.
    run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(COMFY / 'requirements.txt')], timeout=1800)
    req = gguf_dir / 'requirements.txt'
    if req.exists():
        run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(req)], timeout=900)
    else:
        run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', 'gguf'], timeout=900)

    if shutil.which('ffmpeg') is None:
        run(['bash', '-lc', 'apt-get update -qq && apt-get install -y ffmpeg'], timeout=900)
    run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', 'huggingface_hub'], timeout=900)

    try:
        import cv2  # noqa: F401
    except ImportError:
        run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', 'opencv-python-headless==4.10.0.84'], timeout=900)
    try:
        import transformers  # noqa: F401
    except ImportError:
        run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', 'transformers>=4.46,<5'], timeout=900)

    if primary_image_first:
        # One image-generation model only: do not download Wan into the same Kaggle
        # session. This keeps disk use predictable and makes the primary path truly
        # still-first rather than video-first with a parallax keyframe afterthought.
        paths = {
            'unet': ('city96/FLUX.1-schnell-gguf', 'flux1-schnell-Q4_K_S.gguf',
                     COMFY / 'models' / 'unet' / 'flux1-schnell-Q4_K_S.gguf'),
            'clip_l': ('comfyanonymous/flux_text_encoders', 'clip_l.safetensors',
                       COMFY / 'models' / 'text_encoders' / 'clip_l.safetensors'),
            't5xxl': ('comfyanonymous/flux_text_encoders', 't5xxl_fp8_e4m3fn_scaled.safetensors',
                      COMFY / 'models' / 'text_encoders' / 't5xxl_fp8_e4m3fn_scaled.safetensors'),
            # The official BFL Schnell repo is gated. This public Apache-2.0
            # mirror identifies ae.safetensors as an unmodified copy and publishes
            # the original file SHA-256; verify bytes before accepting it.
            'vae': ('nick911/flux1-schnell-normal', 'ae.safetensors',
                    COMFY / 'models' / 'vae' / 'ae.safetensors'),
        }
        expected_image_file_hashes = {
            'vae': 'afc8e28272cd15db3919bacdb6918ce9c1ed22e96cb12c4d5ed0fba823529e38',
        }
        locked_revisions = MANIFEST.get('image_toolchain_lock')
        locked_revisions = locked_revisions.get('model_revisions', {}) if isinstance(locked_revisions, dict) else {}
        model_revisions: dict[str, str] = {}
        for key, (repo, filename, destination) in paths.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            expected_revision = str(locked_revisions.get(key, '') or '').strip()
            if expected_revision and not re.fullmatch(r'[0-9a-f]{40}', expected_revision):
                raise RuntimeError(f'Image toolchain lock has an invalid {key} snapshot SHA: {expected_revision!r}')
            if destination.is_symlink():
                resolved = hf_cache_revision(destination)
                if expected_revision and resolved != expected_revision:
                    raise RuntimeError(f'Existing {key} model snapshot {resolved} differs from locked {expected_revision}.')
                expected_file_sha = expected_image_file_hashes.get(key)
                if expected_file_sha:
                    verify_model_file_sha256(destination, expected_file_sha, key)
                model_revisions[key] = resolved
                continue
            if destination.exists():
                raise RuntimeError(f'Image model path exists but is not a Hugging Face cache symlink: {destination}')
            info = model_info(repo, revision=expected_revision or None)
            revision = str(getattr(info, 'sha', '') or '').strip()
            if not re.fullmatch(r'[0-9a-f]{40}', revision):
                raise RuntimeError(f'Could not resolve immutable Hugging Face revision for {repo}.')
            if expected_revision and revision != expected_revision:
                raise RuntimeError(f'{repo} revision drift: expected {expected_revision}, got {revision}.')
            cached = Path(hf_hub_download(
                repo_id=repo, filename=filename, revision=revision, cache_dir=str(HF_CACHE)
            ))
            resolved = hf_cache_revision(cached)
            if resolved != revision:
                raise RuntimeError(f'{key} model cache snapshot {resolved} differs from resolved revision {revision}.')
            expected_file_sha = expected_image_file_hashes.get(key)
            if expected_file_sha:
                verify_model_file_sha256(cached, expected_file_sha, key)
            destination.symlink_to(cached)
            model_revisions[key] = resolved
    else:
        paths = {
            'unet': ('timfromhcs/Wan2.2-TI2V-5B-GGUF', 'Wan2.2-TI2V-5B-Q4_K_M.gguf', COMFY / 'models' / 'unet' / 'Wan2.2-TI2V-5B-Q4_K_M.gguf'),
            'clip': ('Comfy-Org/Wan_2.2_ComfyUI_Repackaged', 'split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors', COMFY / 'models' / 'text_encoders' / 'umt5_xxl_fp8_e4m3fn_scaled.safetensors'),
            'vae': ('Comfy-Org/Wan_2.2_ComfyUI_Repackaged', 'split_files/vae/wan2.2_vae.safetensors', COMFY / 'models' / 'vae' / 'wan2.2_vae.safetensors'),
        }
        model_revisions = {}
        locked_revisions = lock.get('model_revisions') if isinstance(lock.get('model_revisions'), dict) else {}
        for key, (repo, filename, dest) in paths.items():
            dest.parent.mkdir(parents=True, exist_ok=True)
            revision = locked_revisions.get(key)
            if revision and not re.fullmatch(r'[0-9a-f]{40}', str(revision)):
                raise RuntimeError(f'Invalid locked Hugging Face revision for {key}: {revision!r}.')
            if dest.exists() or dest.is_symlink():
                if dest.is_symlink():
                    model_revisions[key] = hf_cache_revision(dest)
                    if revision and model_revisions[key] != revision:
                        raise RuntimeError(f'Existing {key} model symlink differs from locked revision.')
                    continue
                raise RuntimeError(f'Model path already exists as a non-symlink; refusing to guess revision: {dest}')
            info = model_info(repo, revision=revision or None)
            resolved = str(getattr(info, 'sha', '') or '').strip()
            if not re.fullmatch(r'[0-9a-f]{40}', resolved):
                raise RuntimeError(f'Could not resolve immutable Hugging Face revision for {repo}.')
            cached = Path(hf_hub_download(
                repo_id=repo, filename=filename, revision=resolved, cache_dir=str(HF_CACHE)
            ))
            model_revisions[key] = hf_cache_revision(cached)
            if model_revisions[key] != resolved:
                raise RuntimeError(f'{key} model cache SHA differs from resolved commit.')
            dest.symlink_to(cached)

    depth_revision = None
    if primary_image_first:
        lock_depth = locked_revisions.get('depth')
        depth_info = model_info('depth-anything/Depth-Anything-V2-Small-hf', revision=lock_depth or None)
        depth_revision = str(getattr(depth_info, 'sha', '') or '').strip()
        if not re.fullmatch(r'[0-9a-f]{40}', depth_revision):
            raise RuntimeError('Depth Anything V2 model did not resolve to an immutable commit SHA.')
        if lock_depth and depth_revision != lock_depth:
            raise RuntimeError(f'Depth model revision drift: expected {lock_depth}, resolved {depth_revision}.')
        model_revisions['depth'] = depth_revision
    else:
        depth_revision = locked_revisions.get('depth')
        depth_info = model_info('depth-anything/Depth-Anything-V2-Small-hf', revision=depth_revision)
        depth_revision = str(getattr(depth_info, 'sha', '') or '').strip()
        if not re.fullmatch(r'[0-9a-f]{40}', depth_revision):
            raise RuntimeError('Depth Anything V2 model did not resolve to an immutable commit SHA.')
        if locked_revisions.get('depth') and depth_revision != locked_revisions.get('depth'):
            raise RuntimeError('Depth model revision drift detected.')
        model_revisions['depth'] = depth_revision
    return {
        'gpu': gpu_name,
        'model_family': 'flux_1_schnell_gguf' if primary_image_first else 'wan22_ti2v_5b_gguf',
        'depth_model_revision': depth_revision,
        'comfyui_commit': comfy_sha,
        'comfyui_gguf_commit': gguf_sha,
        'model_revisions': model_revisions,
        'runtime_packages': runtime_package_versions(),
    }


def wait_for_comfy(base='http://127.0.0.1:8188', timeout=600, *, primary_image_first: bool = False):
    deadline = time.time() + timeout
    last_error = None
    if primary_image_first:
        required = [
            'UnetLoaderGGUF', 'DualCLIPLoader', 'VAELoader', 'CLIPTextEncodeFlux',
            'ConditioningZeroOut', 'EmptySD3LatentImage', 'KSampler',
            'VAEDecode', 'SaveImage',
        ]
    else:
        required = [
            'UnetLoaderGGUF', 'CLIPLoader', 'VAELoader', 'CLIPTextEncode',
            'ModelSamplingSD3', 'KSampler', 'Wan22ImageToVideoLatent',
            'VAEDecode', 'CreateVideo', 'SaveVideo',
        ]
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + '/object_info', timeout=5) as r:
                if r.status == 200:
                    body = json.loads(r.read().decode('utf-8'))
                    missing = [name for name in required if name not in body]
                    if missing:
                        raise RuntimeError('ComfyUI did not register required nodes for the selected mode: ' + ', '.join(missing))
                    return body
        except RuntimeError:
            raise
        except Exception as exc:
            last_error = str(exc)
        time.sleep(5)
    raise RuntimeError(f'ComfyUI API did not become ready within {timeout}s. Last error: {last_error}')


def node_prompt(objects, node_type, inputs):
    """Fail fast if a ComfyUI version changes the required node schema."""
    info = objects[node_type]
    allowed = set()
    schema = info.get('input', {})
    required = set((schema.get('required') or {}).keys())
    optional = set((schema.get('optional') or {}).keys())
    allowed = required | optional
    unsupported = [k for k in inputs if k not in allowed]
    missing = sorted(required - set(inputs))
    if unsupported or missing:
        raise RuntimeError(
            f'ComfyUI node {node_type} schema changed; '
            f'unsupported inputs={unsupported}; missing required inputs={missing}; supported={sorted(allowed)}'
        )
    return {'class_type': node_type, 'inputs': inputs}


SHOT_COVERAGE = {
    1: (
        "ESTABLISHING COVERAGE: use a medium-wide or wide vertical composition to establish the real location, "
        "the main subject or meaningful object, and the opening action. Keep the subject readable against the environment."
    ),
    2: (
        "ACTION COVERAGE: move to a medium or compatible over-shoulder composition that brings the viewer closer "
        "to the same subject and the next causal action. Do not invent a second person or new event."
    ),
    3: (
        "DETAIL INSERT: use a close detail of the story-bearing object, practical action or restrained hand gesture "
        "that adds new information. Do not create readable writing, phone UI or extra props."
    ),
    4: (
        "CONSEQUENCE COVERAGE: show the consequence or changed relationship through a compatible medium-close, "
        "profile, silhouette or environmental composition. Keep the same people, clothing and location."
    ),
    5: (
        "TURNING-POINT COVERAGE: use a tighter reaction or meaningful gesture to make the choice visible; "
        "keep acting restrained and physically natural, with no exaggerated facial performance."
    ),
    6: (
        "PAYOFF / VISUAL ECHO: compose a deliberate closing image that echoes the opening subject, object or space "
        "with its meaning changed by the story. Resolve the beat; do not introduce an unrelated final scene."
    ),
}


def shot_coverage_instruction(scene_index, total_scenes):
    """Return camera grammar for the six-beat story without changing its events or characters."""
    if isinstance(scene_index, bool) or not isinstance(scene_index, int):
        raise ValueError("scene_index must be an integer.")
    if isinstance(total_scenes, bool) or not isinstance(total_scenes, int) or total_scenes < 1:
        raise ValueError("total_scenes must be a positive integer.")
    if not 1 <= scene_index <= total_scenes:
        raise ValueError(f"scene_index {scene_index} is outside 1..{total_scenes}.")
    if total_scenes == 6:
        return SHOT_COVERAGE[scene_index]
    if scene_index == 1:
        return "ESTABLISHING COVERAGE: choose a clear wide or medium-wide composition that introduces this story."
    if scene_index == total_scenes:
        return "CLOSING COVERAGE: choose a deliberate visual payoff that resolves this story without adding events."
    return (
        "INTERMEDIATE COVERAGE: choose a distinct, beat-appropriate shot size and camera angle; "
        "preserve the same subject, clothing, setting and physical action."
    )


def build_flux_image_workflow(objects, beat, story, scene_index, prefix):
    """Build a validated FLUX.1 Schnell still-image graph for the primary 2.5D path."""
    style_profile = story.get('visual_style_profile') if isinstance(story.get('visual_style_profile'), dict) else {}
    bible = str(story.get('visual_bible') or '').strip()
    character_lines = []
    for character in story.get('characters', []):
        if not isinstance(character, dict):
            continue
        character_lines.append(
            f"{character.get('display_name', character.get('character_id', 'Character'))}: "
            f"{character.get('visual_age_description', '')}; {character.get('appearance', '')}; "
            f"wardrobe and distinguishing features must remain unchanged."
        )
    style = (
        "High-end semi-painterly Indian graphic-novel film still, illustrated not photorealistic, "
        "tactile brush texture, clean intentional ink contours, expressive adult characters, "
        "credible Indian environments and objects, cinematic composition, deep but readable tonal separation. "
        f"Art direction: {style_profile.get('surface_language', 'painterly Indian graphic-novel cinema')}. "
        f"Palette: {style_profile.get('palette', 'warm tungsten amber, muted earth and monsoon teal')}. "
        f"Lighting: {style_profile.get('lighting', 'motivated practical lighting, soft falloff')}. "
        "Vertical 9:16 shot, subject clearly readable on a phone screen, strong foreground/midground/background "
        "separation for depth estimation, no text, captions, typography, logos or watermark."
    )
    prompt = (
        f"{style}\nVISUAL BIBLE: {bible}\nRECURRING CAST: "
        + " ".join(character_lines)
        + f"\nNARRATIVE ROLE: {beat.get('narrative_role', 'story beat')}."
        + f"\nSTATE CHANGE: {beat.get('state_change', beat.get('visual_direction', 'Show the approved action clearly.'))}"
        + f"\nCAUSAL LINK: {beat.get('causal_link', 'Preserve the screenplay order and story logic.')}"
        + f"\nSHOT: {beat.get('video_prompt', beat.get('visual_query', ''))}"
    )
    if len(prompt.strip()) < 80:
        raise ValueError(f"Scene {scene_index} image prompt is too short to establish a coherent illustrated shot.")
    seed = int(hashlib.sha256(
        f"{MANIFEST.get('job_id')}|{story['reel_id']}|{scene_index}|{prompt}".encode()
    ).hexdigest()[:15], 16) % (2**63 - 1)
    g = {}
    g['37'] = node_prompt(objects, 'UnetLoaderGGUF', {
        'unet_name': 'flux1-schnell-Q4_K_S.gguf',
    })
    g['38'] = node_prompt(objects, 'DualCLIPLoader', {
        'clip_name1': 'clip_l.safetensors',
        'clip_name2': 't5xxl_fp8_e4m3fn_scaled.safetensors',
        'type': 'flux',
        'device': 'default',
    })
    g['39'] = node_prompt(objects, 'VAELoader', {'vae_name': 'ae.safetensors'})
    g['27'] = node_prompt(objects, 'EmptySD3LatentImage', {
        'width': 704, 'height': 1280, 'batch_size': 1,
    })
    g['41'] = node_prompt(objects, 'CLIPTextEncodeFlux', {
        'clip': ['38', 0], 'clip_l': prompt, 't5xxl': prompt, 'guidance': 3.5,
    })
    g['42'] = node_prompt(objects, 'ConditioningZeroOut', {'conditioning': ['41', 0]})
    g['31'] = node_prompt(objects, 'KSampler', {
        'seed': seed, 'steps': 4, 'cfg': 1.0,
        'sampler_name': 'euler', 'scheduler': 'simple', 'denoise': 1.0,
        'model': ['37', 0], 'positive': ['41', 0], 'negative': ['42', 0],
        'latent_image': ['27', 0],
    })
    g['8'] = node_prompt(objects, 'VAEDecode', {'samples': ['31', 0], 'vae': ['39', 0]})
    g['9'] = node_prompt(objects, 'SaveImage', {
        'images': ['8', 0], 'filename_prefix': prefix,
    })
    return g


def build_api_workflow(objects, beat, story, scene_index, prefix):
    prompt_text = str(beat['video_prompt']).strip()
    bible = str(story.get('visual_bible', '')).strip()
    voice_timing = beat.get('voice_timing') if isinstance(beat.get('voice_timing'), dict) else {}
    target_frames = beat.get('target_frames', voice_timing.get('target_frames', 81))
    if isinstance(target_frames, bool) or not isinstance(target_frames, int):
        raise ValueError(f"Scene {scene_index} target_frames must be an integer.")
    if target_frames < 61 or target_frames > 193 or (target_frames - 1) % 4:
        raise ValueError(
            f"Scene {scene_index} target_frames={target_frames} is outside Wan's qualified "
            "61..193 frame, 4n+1 window. Dialogue must be re-storyboarded; never shortened."
        )
    fps = int(voice_timing.get('fps', 24))
    if fps != 24:
        raise ValueError("Voice-first Wan scenes must use the qualified 24 FPS timeline.")
    total_scenes = len(story.get('beats', [])) or 6
    coverage = shot_coverage_instruction(scene_index, total_scenes)
    reference_image = str(story.get('character_reference_image') or '').strip()
    narrative_role = str(beat.get('narrative_role') or ('hook' if scene_index == 1 else 'payoff' if scene_index == total_scenes else 'intermediate')).strip().lower()
    state_change = str(beat.get('state_change') or beat.get('visual_direction') or 'Preserve the beat-specific action and visual meaning.').strip()
    causal_link = str(beat.get('causal_link') or 'Preserve the approved order and causal relationship of the screenplay.').strip()
    if not narrative_role or len(state_change.split()) < 3 or len(causal_link.split()) < 3:
        raise ValueError(f'Scene {scene_index} is missing its narrative role, state change or causal link.')
    style_profile = story.get('visual_style_profile') if isinstance(story.get('visual_style_profile'), dict) else {}
    style_palette = str(style_profile.get('palette') or 'warm tungsten amber, muted earth and monsoon teal shadows')
    style_lighting = str(style_profile.get('lighting') or 'motivated practical lighting with soft falloff')
    style_camera = str(style_profile.get('camera_grammar') or 'motivated push-ins, lateral drift and expressive reaction close-ups')
    style_surface = str(style_profile.get('surface_language') or 'semi-painterly Indian graphic-novel illustration with tactile brush grain')
    style = (
        'Mature illustrated 2.5D Indian motion-comic cinema, clearly graphic-novel art rather than photoreal live action, '
        'layered foreground/midground/background cues, tactile brush-textured surfaces, consistent expressive character design, '
        f'{style_surface}. PALETTE: {style_palette}. LIGHTING: {style_lighting}. CAMERA LANGUAGE: {style_camera}. '
        'Physically plausible subtle movement, coherent cinematic colour, vertical 9:16 composition, one clear action, '
        'clean visual hierarchy. No text, subtitles or typography may appear in-frame. '
    )
    full_prompt = (
        f"{style}\nCONTINUITY / LOOK BIBLE: {bible}"
        f"\nNARRATIVE ROLE: {narrative_role}."
        f"\nSTATE CHANGE THIS SHOT MUST COMMUNICATE: {state_change}"
        f"\nCAUSAL LINK TO THE STORY: {causal_link}"
        f"\nSHOT FUNCTION / CAMERA COVERAGE: {coverage}"
        f"\nSHOT {scene_index}: {prompt_text}"
        "\nCamera coverage is guidance only: preserve the exact beat, action and subject from the shot prompt. "
        "Do not add people, props, dialogue or events merely to satisfy the shot function. "
        "Keep the same character appearance, clothing, environment and restrained visual treatment across scenes. "
        "No readable text, subtitles, logos or watermarks."
    )
    if reference_image and scene_index > 1:
        full_prompt += f"\nVISUAL IDENTITY ANCHOR: the supplied first-scene image is a continuity reference for recurring character face, age, hair, clothing and palette. Animate the requested new action; do not copy the previous pose or freeze the reference composition."
    seed = int(hashlib.sha256(f"{MANIFEST.get('job_id')}|{story['reel_id']}|{scene_index}|{prompt_text}".encode()).hexdigest()[:15], 16) % (2**63 - 1)

    g = {}
    g['37'] = node_prompt(objects, 'UnetLoaderGGUF', {'unet_name': 'Wan2.2-TI2V-5B-Q4_K_M.gguf'})
    g['38'] = node_prompt(objects, 'CLIPLoader', {
        'clip_name': 'umt5_xxl_fp8_e4m3fn_scaled.safetensors', 'type': 'wan', 'device': 'default'
    })
    g['39'] = node_prompt(objects, 'VAELoader', {'vae_name': 'wan2.2_vae.safetensors'})
    g['48'] = node_prompt(objects, 'ModelSamplingSD3', {'model': ['37', 0], 'shift': 8})
    g['6'] = node_prompt(objects, 'CLIPTextEncode', {'text': full_prompt, 'clip': ['38', 0]})
    g['7'] = node_prompt(objects, 'CLIPTextEncode', {'text': NEGATIVE, 'clip': ['38', 0]})
    latent_inputs = {
        'width': 704, 'height': 1280, 'length': target_frames, 'batch_size': 1, 'vae': ['39', 0]
    }
    uses_hybrid_reference = scene_index > 1 and is_25d_pipeline(story.get('visual_pipeline'))
    if uses_hybrid_reference:
        if not reference_image or Path(reference_image).name != reference_image:
            raise RuntimeError(
                f"Scene {scene_index} is missing its safe first-scene character anchor; "
                "refusing to generate a text-only continuity fallback."
            )
        g['59'] = node_prompt(objects, 'LoadImage', {'image': reference_image})
        latent_inputs['start_image'] = ['59', 0]
    elif reference_image and Path(reference_image).name != reference_image:
        raise ValueError("character_reference_image must be a safe ComfyUI input filename.")
    g['55'] = node_prompt(objects, 'Wan22ImageToVideoLatent', latent_inputs)
    # The ComfyUI API KSampler schema exposes `seed` but not the UI-only
    # `control_after_generate` widget value. Determinism is already guaranteed by
    # the explicit per-scene seed computed above.
    g['3'] = node_prompt(objects, 'KSampler', {
        'seed': seed, 'steps': 20, 'cfg': 5,
        'sampler_name': 'uni_pc', 'scheduler': 'simple', 'denoise': 1,
        'model': ['48', 0], 'positive': ['6', 0], 'negative': ['7', 0], 'latent_image': ['55', 0]
    })
    g['8'] = node_prompt(objects, 'VAEDecode', {'samples': ['3', 0], 'vae': ['39', 0]})
    g['57'] = node_prompt(objects, 'CreateVideo', {'images': ['8', 0], 'fps': 24})
    save_inputs = {'video': ['57', 0], 'filename_prefix': prefix, 'format': 'auto', 'codec': 'auto'}
    g['58'] = node_prompt(objects, 'SaveVideo', save_inputs)
    return g


def post_prompt(graph, base='http://127.0.0.1:8188'):
    import requests
    response = requests.post(base + '/prompt', json={'prompt': graph, 'client_id': 'bina-shor-ke-studio'}, timeout=120)
    if response.status_code != 200:
        raise RuntimeError(f'ComfyUI rejected a scene prompt (HTTP {response.status_code}): {response.text[:3000]}')
    body = response.json()
    if body.get('error'):
        raise RuntimeError('ComfyUI prompt error: ' + json.dumps(body, ensure_ascii=False)[:3000])
    return body['prompt_id']


DEFAULT_PROMPT_TIMEOUT_SECONDS = 5400


def _queue_prompt_ids(items) -> set[str]:
    """Return prompt IDs from ComfyUI's queue tuples or dictionary-shaped responses."""
    found: set[str] = set()
    if not isinstance(items, list):
        return found
    for item in items:
        if isinstance(item, (list, tuple)) and len(item) > 1:
            found.add(str(item[1]))
        elif isinstance(item, dict) and item.get('prompt_id'):
            found.add(str(item['prompt_id']))
    return found


def wait_prompt(prompt_id, timeout=DEFAULT_PROMPT_TIMEOUT_SECONDS, base='http://127.0.0.1:8188'):
    """Wait for a ComfyUI prompt, tracking its queue state while history is not yet persisted.

    ComfyUI history may remain empty while a prompt is still queued/running. Polling only
    /history therefore loses useful state and can report a missing status for a live job.
    Keep both endpoints in the timeout diagnostic and allow up to 90 minutes per scene.
    """
    import requests
    deadline = time.monotonic() + timeout
    last_status = {'status_str': 'not_seen', 'history_entry': False, 'queue_state': 'unknown'}
    while time.monotonic() < deadline:
        try:
            response = requests.get(f'{base}/history/{prompt_id}', timeout=20)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and prompt_id in data:
                item = data[prompt_id]
                status = item.get('status', {}) if isinstance(item, dict) else {}
                last_status = {'history_entry': True, **(status if isinstance(status, dict) else {})}
                if status.get('completed') is True or status.get('status_str') == 'success':
                    return item
                if status.get('status_str') in ('error', 'failed'):
                    raise RuntimeError('ComfyUI generation failed: ' + json.dumps(status, ensure_ascii=False)[:3000])
            else:
                # /history is populated after execution; /queue shows active and pending prompts.
                queue_response = requests.get(f'{base}/queue', timeout=10)
                queue_response.raise_for_status()
                queue = queue_response.json()
                running = _queue_prompt_ids(queue.get('queue_running', [])) if isinstance(queue, dict) else set()
                pending = _queue_prompt_ids(queue.get('queue_pending', [])) if isinstance(queue, dict) else set()
                if prompt_id in running:
                    queue_state = 'running'
                elif prompt_id in pending:
                    queue_state = 'queued'
                else:
                    queue_state = 'not_visible_in_history_or_queue'
                last_status = {
                    'history_entry': False,
                    'queue_state': queue_state,
                    'running_count': len(running),
                    'pending_count': len(pending),
                }
        except requests.RequestException as exc:
            last_status = {
                'history_entry': False,
                'queue_state': 'endpoint_error',
                'endpoint_error': str(exc)[:500],
            }
        time.sleep(8)
    raise TimeoutError(
        f'ComfyUI scene generation timed out after {timeout}s for prompt {prompt_id}. '
        f'Last observed state={json.dumps(last_status, ensure_ascii=False)[:2000]}'
    )


def latest_image(output_dir: Path, before: float, prefix: str) -> Path:
    """Find the exact scene PNG created by this ComfyUI prompt, never a stale image."""
    parts = [part.lower() for part in prefix.split('/') if part]
    files = []
    for path in output_dir.rglob('*'):
        if not path.is_file() or path.suffix.lower() not in {'.png', '.webp'} or path.stat().st_mtime < before - 1:
            continue
        normalized = [part.lower() for part in path.parts]
        if parts and not all(any(token in actual for actual in normalized) for token in parts):
            continue
        files.append(path)
    if not files:
        raise RuntimeError(f'ComfyUI completed but no matching still-image output found after prompt prefix {prefix}.')
    return max(files, key=lambda path: path.stat().st_mtime)


def prepare_scene_still(source: Path, destination: Path) -> dict:
    """Validate and crop a generated still to the pinned 9:16 motion-comic working canvas."""
    from PIL import Image, ImageOps
    if not source.is_file() or source.stat().st_size < 100_000:
        raise RuntimeError(f'ComfyUI still is missing or too small: {source}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.stem + '.partial.png')
    temporary.unlink(missing_ok=True)
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image).convert('RGB')
        target_ratio = 704 / 1280
        width, height = image.size
        if width <= 0 or height <= 0:
            raise RuntimeError('Generated still has invalid image dimensions.')
        current_ratio = width / height
        if current_ratio > target_ratio:
            new_width = max(1, int(round(height * target_ratio)))
            left = (width - new_width) // 2
            image = image.crop((left, 0, left + new_width, height))
        else:
            new_height = max(1, int(round(width / target_ratio)))
            top = (height - new_height) // 2
            image = image.crop((0, top, width, top + new_height))
        image = image.resize((704, 1280), Image.Resampling.LANCZOS)
        image.save(temporary, format='PNG', optimize=True)
    with Image.open(temporary) as check:
        check.verify()
    temporary.replace(destination)
    with Image.open(destination) as final:
        width, height = final.size
    return {
        'bytes': destination.stat().st_size,
        'sha256': sha256_file(destination),
        'width': width,
        'height': height,
        'format': 'PNG',
    }


def latest_video(output_dir: Path, before: float, prefix: str) -> Path:
    # Restrict matching to this Reel/scene so parallel or stale outputs cannot be mixed.
    parts = [part.lower() for part in prefix.split('/') if part]
    files = []
    for p in output_dir.rglob('*'):
        if not p.is_file() or p.suffix.lower() not in {'.mp4', '.webm', '.mkv'} or p.stat().st_mtime < before - 1:
            continue
        normalized = [part.lower() for part in p.parts]
        if parts and not all(any(token in actual for actual in normalized) for token in parts):
            continue
        files.append(p)
    if not files:
        raise RuntimeError(f'ComfyUI completed but no matching video output found after prompt prefix {prefix}.')
    return max(files, key=lambda p: p.stat().st_mtime)


def create_character_reference_image(source: Path, destination: Path, duration: float) -> dict:
    """Extract and verify a first-scene identity anchor for reference-conditioned later Wan scenes."""
    import math
    from PIL import Image

    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(float(duration)) or duration <= 0.5:
        raise ValueError("Character reference extraction requires a finite source scene longer than 0.5 seconds.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.stem + ".partial.png")
    temporary.unlink(missing_ok=True)
    timestamp = min(max(0.1, float(duration) * 0.45), float(duration) - 0.05)
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{timestamp:.3f}", "-i", str(source),
        "-frames:v", "1", "-vf", "scale=704:1280:flags=lanczos,format=rgb24",
        str(temporary),
    ], timeout=180)
    if not temporary.is_file() or temporary.stat().st_size < 1_024:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("First-scene identity anchor was not extracted as a non-empty PNG.")
    try:
        with Image.open(temporary) as frame:
            frame.verify()
        with Image.open(temporary) as frame:
            if frame.size != (704, 1280):
                raise RuntimeError(f"Character reference has unexpected dimensions {frame.size}; expected 704x1280.")
            frame.load()
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    temporary.replace(destination)
    return {
        "filename": destination.name,
        "width": 704,
        "height": 1280,
        "timestamp_seconds": round(timestamp, 3),
        "bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
        "conditioning": "ComfyUI LoadImage -> Wan22ImageToVideoLatent.start_image for later scenes",
    }


def persist_character_reference(reel: dict, reel_id: str, scene_path: Path, result_manifest: dict) -> dict:
    """Save a per-Reel first-scene visual anchor; this is not a permanent cast portrait."""
    valid, duration = valid_scene_file(scene_path)
    if not valid:
        raise RuntimeError(f"Cannot derive a character identity anchor from invalid Scene 1: {scene_path}")
    safe_reel_id = re.sub(r"[^A-Za-z0-9_-]+", "_", reel_id)
    reference_path = COMFY / "input" / f"{safe_reel_id}_identity_anchor.png"
    metadata = create_character_reference_image(scene_path, reference_path, duration)
    reel["character_reference_image"] = metadata["filename"]
    record = {
        "reel_id": reel_id,
        "source_scene_index": 1,
        "path": str(reference_path.relative_to(COMFY)),
        "sha256": metadata["sha256"],
        "bytes": metadata["bytes"],
        "width": metadata["width"],
        "height": metadata["height"],
        "timestamp_seconds": metadata["timestamp_seconds"],
        "used_for_scenes": list(range(2, len(reel.get("beats", [])) + 1)),
        "conditioning": metadata["conditioning"],
    }
    references = result_manifest.setdefault("character_references", [])
    references[:] = [item for item in references if item.get("reel_id") != reel_id]
    references.append(record)
    write_json(OUT / "gpu_output_manifest.json", result_manifest)
    print(
        f"Saved {reel_id} first-scene identity anchor ({metadata['width']}x{metadata['height']}, "
        f"SHA-256 {metadata['sha256'][:12]}) for later Wan scenes.",
        flush=True,
    )
    return record


def transcode_scene(source: Path, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.stem + '.partial.mp4')
    temporary.unlink(missing_ok=True)
    run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source), '-an', '-vf', 'scale=704:1280:flags=lanczos,fps=24', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '19', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(temporary)], timeout=900)
    valid, duration = valid_scene_file(temporary)
    if not valid:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f'Transcoded scene failed file/duration verification: {destination} (duration={duration:.2f}s)')
    temporary.replace(destination)


def load_depth_estimator(revision: str):
    """Load a small Apache-2.0 monocular depth model on CPU to protect Wan GPU memory."""
    import torch
    from transformers import pipeline
    torch.set_num_threads(2)
    print("Loading Depth Anything V2 Small (Apache-2.0) on CPU for 2.5D parallax.", flush=True)
    return pipeline(
        "depth-estimation",
        model="depth-anything/Depth-Anything-V2-Small-hf",
        revision=revision,
        device=-1,
        model_kwargs={"cache_dir": str(HF_CACHE)},
    )


def create_25d_parallax_clip(
    source: Path, destination: Path, duration: float, depth_estimator,
    *, camera_move: str = "gentle_push",
):
    """Extract, stylize and depth-warp one scene keyframe into a real parallax video."""
    import math
    import numpy as np
    import cv2
    from PIL import Image, ImageFilter, ImageOps

    if source.suffix.lower() == ".png":
        # Image-first production: the AI-generated still is the source asset;
        # no Wan clip is created merely to extract a keyframe.
        keyframe_path = source
    else:
        scratch = WORK / "motion_comic_tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        keyframe_path = scratch / f"{destination.stem}_keyframe.png"
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{max(0.1, duration * 0.45):.3f}", "-i", str(source),
            "-frames:v", "1", "-vf", "scale=704:1280:flags=lanczos", str(keyframe_path),
        ], timeout=180)
    with Image.open(keyframe_path) as original:
        image = original.convert("RGB").filter(ImageFilter.MedianFilter(3))
        image = ImageOps.posterize(image, bits=5)
        edges = image.filter(ImageFilter.FIND_EDGES).convert("L")
        edge_mask = edges.point(lambda value: max(0, min(105, int((value - 30) * 1.8))))
        outline = Image.new("RGB", image.size, (25, 29, 38))
        image = Image.composite(outline, image, edge_mask)
        keyframe = image.copy()
    prediction = depth_estimator(keyframe)
    depth_image = prediction.get("depth") if isinstance(prediction, dict) else None
    if depth_image is None:
        raise RuntimeError("Depth Anything did not return a depth image for the illustrated keyframe.")
    if not isinstance(depth_image, Image.Image):
        raise RuntimeError("Depth Anything returned an unsupported depth-image type.")
    depth_array = np.asarray(depth_image.convert("L").resize((704, 1280), Image.Resampling.BICUBIC), dtype=np.uint8)
    colour = np.asarray(keyframe, dtype=np.uint8)
    frame = cv2.cvtColor(colour, cv2.COLOR_RGB2BGR)
    if frame.shape[:2] != (1280, 704):
        raise RuntimeError(f"Illustrated keyframe has an unexpected shape: {frame.shape}.")
    depth = cv2.normalize(depth_array, None, 0.0, 1.0, cv2.NORM_MINMAX, dtype=cv2.CV_32F)
    depth = cv2.GaussianBlur(depth, (0, 0), sigmaX=2.0)
    if float(depth.std()) < 0.015:
        raise RuntimeError("Depth Anything produced a nearly flat depth map; refusing fake 2.5D movement.")

    # The source Wan generation stays 24 FPS; the derived primary 2.5D motion master is 30 FPS.
    width, height, fps = 704, 1280, 30
    frame_count = max(1, int(round(duration * fps)))
    grid_x, grid_y = np.meshgrid(
        np.arange(width, dtype=np.float32),
        np.arange(height, dtype=np.float32),
    )
    center_x, center_y = (width - 1) / 2.0, (height - 1) / 2.0
    temporary = destination.with_name(destination.stem + ".partial.mp4")
    temporary.unlink(missing_ok=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo", "-pix_fmt", "bgr24",
        "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temporary),
    ]
    encoder = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        if encoder.stdin is None:
            raise RuntimeError("FFmpeg did not expose a raw-video input pipe.")
        disparity = (depth - 0.5)
        # Distinct camera grammar per beat keeps 2.5D shots alive and story-led.
        camera_profiles = {
            "punch_in": (0.045, 0.0, 0.0),
            "reveal_left": (0.025, -13.0, 0.0),
            "wide_drift_right": (0.010, 12.0, 0.0),
            "gentle_push": (0.020, 0.0, 0.0),
            "reaction_close": (0.038, 0.0, -4.0),
            "slow_push": (0.024, 0.0, 0.0),
            "track_left": (0.014, -20.0, 1.5),
            "track_right": (0.014, 20.0, 1.5),
            "detail_insert": (0.040, 4.0, 8.0),
            "reveal_push": (0.045, 0.0, 0.0),
            "clue_insert": (0.035, 4.0, 7.0),
            "emotional_hold": (0.020, 0.0, -2.0),
            "slow_pull_frame": (-0.008, 0.0, 0.0),
        }
        zoom_delta, drift_x, drift_y = camera_profiles.get(camera_move, camera_profiles["gentle_push"])
        for frame_index in range(frame_count):
            progress = frame_index / max(1, frame_count - 1)
            eased = progress * progress * (3.0 - 2.0 * progress)
            depth_breath = math.sin(math.pi * progress)
            zoom = 1.0 + zoom_delta * eased
            parallax_x = disparity * (14.0 * depth_breath)
            parallax_y = disparity * (6.0 * depth_breath)
            camera_x = drift_x * eased
            camera_y = drift_y * eased
            map_x = ((grid_x - center_x) / zoom + center_x + parallax_x + camera_x).astype(np.float32)
            map_y = ((grid_y - center_y) / zoom + center_y + parallax_y + camera_y).astype(np.float32)
            warped = cv2.remap(
                frame, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_REFLECT_101,
            )
            encoder.stdin.write(warped.tobytes())
        encoder.stdin.close()
        return_code = encoder.wait(timeout=900)
        error_text = encoder.stderr.read().decode("utf-8", errors="replace") if encoder.stderr else ""
        if return_code:
            raise RuntimeError(f"FFmpeg depth-parallax encode failed ({return_code}): {error_text[-2500:]}")
    except Exception:
        encoder.kill()
        encoder.wait(timeout=30)
        temporary.unlink(missing_ok=True)
        raise
    finally:
        if encoder.stderr:
            encoder.stderr.close()
    valid, measured = valid_scene_file(
        temporary, max_duration=8.1 if source.suffix.lower() == ".png" else 8.0
    )
    if not valid or abs(measured - duration) > 0.20:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"2.5D parallax clip failed media validation: valid={valid}, target={duration:.3f}s, actual={measured:.3f}s.")
    temporary.replace(destination)
    return {
        "duration_seconds": round(measured, 3),
        "bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
        "depth_model": "depth-anything/Depth-Anything-V2-Small-hf",
        "depth_model_license": "Apache-2.0",
        "keyframe_style": "posterized painterly graphic-novel",
        "source_asset_type": "AI-generated image-first still" if source.suffix.lower() == ".png" else "legacy Wan video keyframe",
        "camera_motion": camera_move,
        "camera_motion_model": "eased genre-role camera move + depth-displaced foreground/midground/background parallax",
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    primary_image_first = bool(MANIFEST.get('reels')) and all(
        str(reel.get('visual_pipeline') or '') == PRIMARY_25D_PIPELINE
        for reel in MANIFEST.get('reels', [])
    )
    if not primary_image_first:
        if any(is_25d_pipeline(reel.get('visual_pipeline')) for reel in MANIFEST.get('reels', [])):
            raise RuntimeError('A single GPU batch cannot mix image-first primary 2.5D and legacy Wan pipelines.')
    result_manifest = {
        'job_id': MANIFEST.get('job_id'),
        'status': 'running',
        'model': 'FLUX.1-schnell Q4_K_S GGUF (image-first)' if primary_image_first else 'Wan2.2 TI2V 5B Q4_K_M GGUF (legacy video)',
        'license_note': (
            'FLUX.1 Schnell quantized GGUF is Apache-2.0; verify upstream and quantization notices before commercial use.'
            if primary_image_first else
            'Wan2.2 upstream is Apache-2.0; this quantized derivative has its own attribution/notice. Review licenses before commercial use.'
        ),
        'scenes': [], 'parallax_scenes': [], 'character_references': [],
        'visual_pipeline': PRIMARY_25D_PIPELINE if primary_image_first else LEGACY_25D_PIPELINE,
        'generation_mode': 'still_image_first' if primary_image_first else 'wan_video_first_legacy',
        'depth_model': 'depth-anything/Depth-Anything-V2-Small-hf',
        'depth_model_license': 'Apache-2.0',
        'started_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    server = None
    worker_started = time.monotonic()
    try:
        toolchain_info = install_comfyui()
        result_manifest['gpu'] = toolchain_info['gpu']
        result_manifest['comfyui_commit'] = toolchain_info['comfyui_commit']
        result_manifest['comfyui_gguf_commit'] = toolchain_info['comfyui_gguf_commit']
        result_manifest['model_revisions'] = toolchain_info['model_revisions']
        result_manifest['depth_model_revision'] = toolchain_info['depth_model_revision']
        result_manifest['runtime_packages'] = toolchain_info['runtime_packages']
        restore_checkpoint_dataset(result_manifest)
        output_dir = COMFY / 'output'
        (COMFY / 'models' / 'unet').mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True'
        server_log = WORK / 'comfy_server.log'
        log_handle = server_log.open('w', encoding='utf-8')
        server = subprocess.Popen([
            sys.executable, 'main.py', '--listen', '127.0.0.1', '--port', '8188', '--disable-auto-launch'
        ], cwd=COMFY, env=env, stdout=log_handle, stderr=subprocess.STDOUT)
        objects = wait_for_comfy(primary_image_first=primary_image_first)
        result_manifest['comfy_nodes_checked'] = True

        for reel in MANIFEST.get('reels', []):
            reel_id = reel['reel_id']
            for scene_index, beat in enumerate(reel['beats'], start=1):
                extension = '.png' if primary_image_first else '.mp4'
                final_out = OUT / reel_id / f'scene_{scene_index:02d}{extension}'
                scene_started = time.monotonic()
                if primary_image_first:
                    if final_out.exists() and final_out.stat().st_size > 100_000:
                        image_meta = prepare_scene_still(final_out, final_out)
                        elapsed = 0.0
                        prompt_id = None
                        history = {'status': {'checkpoint': 'reused'}}
                    else:
                        prefix = f"bsk/{reel_id}/scene_{scene_index:02d}"
                        before = time.time()
                        graph = build_flux_image_workflow(objects, beat, reel, scene_index, prefix)
                        prompt_id = post_prompt(graph)
                        result_manifest['current_scene'] = {
                            'reel_id': reel_id, 'scene_index': scene_index, 'asset_type': 'still_image',
                            'prompt_id': prompt_id, 'queued_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                        }
                        write_json(OUT / 'gpu_output_manifest.json', result_manifest)
                        print(f"Queued image-first still {reel_id} scene {scene_index}/{len(reel['beats'])}: {prompt_id}", flush=True)
                        history = wait_prompt(prompt_id)
                        result_manifest.pop('current_scene', None)
                        source = latest_image(output_dir, before, prefix)
                        image_meta = prepare_scene_still(source, final_out)
                        try:
                            source.unlink()
                        except OSError:
                            pass
                        elapsed = round(time.monotonic() - scene_started, 2)
                    result_manifest['scenes'] = [
                        row for row in result_manifest['scenes']
                        if not (row.get('reel_id') == reel_id and int(row.get('scene_index', 0)) == scene_index)
                    ]
                    result_manifest['scenes'].append({
                        'reel_id': reel_id, 'scene_index': scene_index,
                        'path': str(final_out.relative_to(WORK)),
                        'media_type': 'image/png',
                        **image_meta,
                        'generation_elapsed_seconds': elapsed,
                        'prompt_id': prompt_id,
                        'comfy_history_status': history.get('status', {}),
                    })
                    write_checkpoint_manifest(result_manifest, 'running')
                    write_json(OUT / 'gpu_output_manifest.json', result_manifest)
                    print(f"Verified FLUX still {reel_id} {scene_index}: {image_meta['width']}x{image_meta['height']} ({image_meta['bytes']} bytes)", flush=True)
                else:
                    if final_out.exists() and final_out.stat().st_size > 100_000:
                        if scene_index == 1 and is_25d_pipeline(reel.get('visual_pipeline')):
                            persist_character_reference(reel, reel_id, final_out, result_manifest)
                        continue
                    prefix = f"bsk/{reel_id}/scene_{scene_index:02d}"
                    before = time.time()
                    graph = build_api_workflow(objects, beat, reel, scene_index, prefix)
                    prompt_id = post_prompt(graph)
                    result_manifest['current_scene'] = {
                        'reel_id': reel_id, 'scene_index': scene_index,
                        'target_frames': int(beat.get('target_frames', 81)),
                        'prompt_id': prompt_id, 'queued_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                    }
                    write_json(OUT / 'gpu_output_manifest.json', result_manifest)
                    print(f"Queued legacy Wan scene {reel_id} scene {scene_index}/{len(reel['beats'])}: {prompt_id}", flush=True)
                    history = wait_prompt(prompt_id)
                    result_manifest.pop('current_scene', None)
                    source = latest_video(output_dir, before, prefix)
                    transcode_scene(source, final_out)
                    if scene_index == 1 and is_25d_pipeline(reel.get('visual_pipeline')):
                        persist_character_reference(reel, reel_id, final_out, result_manifest)
                    result_manifest['scenes'].append({
                        'reel_id': reel_id, 'scene_index': scene_index, 'path': str(final_out.relative_to(WORK)),
                        'bytes': final_out.stat().st_size, 'duration_seconds_target': float(beat.get('target_frames', 81)) / 24.0,
                        'generation_elapsed_seconds': round(time.monotonic() - scene_started, 2),
                        'prompt_id': prompt_id, 'comfy_history_status': history.get('status', {}),
                    })
                    write_checkpoint_manifest(result_manifest, 'running')
                    try:
                        source.unlink()
                    except OSError:
                        pass

        depth_estimator = None
        for reel in MANIFEST.get('reels', []):
            reel_id = reel['reel_id']
            for scene_index, beat in enumerate(reel.get('beats', []), start=1):
                source = OUT / reel_id / (f'scene_{scene_index:02d}.png' if primary_image_first else f'scene_{scene_index:02d}.mp4')
                parallax = OUT / reel_id / f'scene_{scene_index:02d}_25d.mp4'
                if primary_image_first:
                    from PIL import Image
                    try:
                        with Image.open(source) as image:
                            image.verify()
                        with Image.open(source) as image:
                            if image.size != (704, 1280):
                                raise RuntimeError(f'Image-first still dimensions must be 704x1280; got {image.size}.')
                    except Exception as exc:
                        raise RuntimeError(f'Missing or invalid FLUX still for {reel_id} scene {scene_index}: {exc}') from exc
                    voice_timing = beat.get('voice_timing') if isinstance(beat.get('voice_timing'), dict) else {}
                    scene_duration = float(voice_timing.get('target_duration_seconds') or (int(beat.get('target_frames', 81)) / 24.0))
                    if not 2.5 <= scene_duration <= 8.1:
                        raise RuntimeError(f'Voice-locked parallax duration {scene_duration:.3f}s is outside the 2.5–8.1s image-first encoder contract.')
                    valid_parallax, existing_duration = valid_scene_file(parallax, max_duration=8.1)
                else:
                    valid_source, scene_duration = valid_scene_file(source)
                    if not valid_source:
                        raise RuntimeError(f'Missing Wan source scene for legacy parallax derivation: {source}')
                    valid_parallax, existing_duration = valid_scene_file(parallax)

                if valid_parallax:
                    result_manifest['parallax_scenes'] = [
                        row for row in result_manifest['parallax_scenes']
                        if not (row.get('reel_id') == reel_id and int(row.get('scene_index', 0)) == scene_index)
                    ]
                    result_manifest['parallax_scenes'].append({
                        'reel_id': reel_id, 'scene_index': scene_index,
                        'depth_model_revision': toolchain_info['depth_model_revision'],
                        'path': str(parallax.relative_to(WORK)),
                        'duration_seconds': round(existing_duration, 3),
                        'bytes': parallax.stat().st_size,
                        'sha256': sha256_file(parallax),
                        'depth_model': 'depth-anything/Depth-Anything-V2-Small-hf',
                        'depth_model_license': 'Apache-2.0',
                        'reused_existing': True,
                    })
                    write_json(OUT / 'gpu_output_manifest.json', result_manifest)
                    continue

                if depth_estimator is None:
                    depth_estimator = load_depth_estimator(toolchain_info['depth_model_revision'])
                editorial_shots = beat.get('editorial_shots', []) if isinstance(beat, dict) else []
                depth_shots = [
                    shot for shot in editorial_shots
                    if isinstance(shot, dict) and shot.get('source') == 'depth_parallax'
                ]
                camera_move = str(
                    depth_shots[0].get('camera_move') if depth_shots
                    else (beat.get('narrative_role', 'gentle_push') if isinstance(beat, dict) else 'gentle_push')
                )
                metadata = create_25d_parallax_clip(
                    source, parallax, scene_duration, depth_estimator,
                    camera_move=camera_move,
                )
                result_manifest['parallax_scenes'] = [
                    row for row in result_manifest['parallax_scenes']
                    if not (row.get('reel_id') == reel_id and int(row.get('scene_index', 0)) == scene_index)
                ]
                result_manifest['parallax_scenes'].append({
                    'reel_id': reel_id, 'scene_index': scene_index,
                    'depth_model_revision': toolchain_info['depth_model_revision'],
                    'path': str(parallax.relative_to(WORK)),
                    'source_asset_type': 'still_image' if primary_image_first else 'wan_video_keyframe',
                    **metadata,
                })
                write_json(OUT / 'gpu_output_manifest.json', result_manifest)
                print(f"Created depth-parallax scene {reel_id} {scene_index}: {metadata['duration_seconds']:.2f}s", flush=True)

        expected = sum(len(r.get('beats', [])) for r in MANIFEST.get('reels', []))
        extension = '.png' if primary_image_first else '.mp4'
        found = sum(
            1 for reel in MANIFEST.get('reels', [])
            for scene_index in range(1, len(reel.get('beats', [])) + 1)
            if (OUT / reel['reel_id'] / f'scene_{scene_index:02d}{extension}').is_file()
        )
        parallax_found = len({
            (str(row.get('reel_id')), int(row.get('scene_index', 0)))
            for row in result_manifest['parallax_scenes']
        })
        if found != expected or parallax_found != expected:
            raise RuntimeError(
                f'Incomplete visual assets: {found}/{expected} source assets and '
                f'{parallax_found}/{expected} depth-parallax videos; refusing partial output.'
            )
        result_manifest.update({
            'status': 'complete', 'expected_scenes': expected,
            'source_asset_count': found,
            'source_video_generation_count': 0 if primary_image_first else expected,
            'still_image_generation_count': expected if primary_image_first else 0,
            'parallax_video_count': parallax_found,
            'total_elapsed_seconds': round(time.monotonic() - worker_started, 2),
            'completed_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        })
        write_checkpoint_manifest(result_manifest, 'complete')
        write_json(OUT / 'gpu_output_manifest.json', result_manifest)
    except Exception as exc:
        send_failure_file(exc, result_manifest)
        result_manifest.update({'status': 'failed', 'error': str(exc)[:5000], 'completed_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
        write_json(OUT / 'gpu_output_manifest.json', result_manifest)
        print('STUDIO_GPU_FAILURE: ' + str(exc), flush=True)
        raise
    finally:
        if server and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=30)
            except subprocess.TimeoutExpired:
                server.kill()
        if COMFY.exists():
            shutil.rmtree(COMFY, ignore_errors=True)


if __name__ == '__main__':
    main()
