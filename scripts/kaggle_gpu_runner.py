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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def valid_scene_file(path: Path) -> tuple[bool, float]:
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
    return 2.5 <= duration <= 8.0, duration


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
    """Restore only manifest-listed, SHA-256 verified MP4s from a private Kaggle dataset."""
    dataset_id = str(MANIFEST.get('resume_dataset_id', '')).strip()
    if not dataset_id:
        return
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,50}/[A-Za-z0-9_-]{1,50}', dataset_id):
        raise RuntimeError('Resume dataset id has an invalid Kaggle owner/slug format.')
    slug = dataset_id.split('/', 1)[1]
    source = KAGGLE_INPUT_ROOT / slug
    index_path = source / 'checkpoint_manifest.json'
    if not index_path.is_file():
        raise RuntimeError(f'Resume checkpoint dataset is mounted but {index_path.name} is missing.')
    checkpoint = json.loads(index_path.read_text(encoding='utf-8'))
    if checkpoint.get('job_id') != MANIFEST.get('job_id'):
        raise RuntimeError('Resume checkpoint belongs to a different production job; refusing to mix scene files.')
    allowed = {str(r['reel_id']): len(r.get('beats', [])) for r in MANIFEST.get('reels', [])}
    restored = []
    for item in checkpoint.get('scenes', []):
        reel_id = str(item.get('reel_id', ''))
        scene_index = int(item.get('scene_index', 0))
        if reel_id not in allowed or not (1 <= scene_index <= allowed[reel_id]):
            continue
        filename = f'{reel_id}__scene_{scene_index:02d}.mp4'
        src = source / filename
        if not src.is_file() or src.stat().st_size != int(item.get('bytes', -1)):
            continue
        if sha256_file(src) != item.get('sha256'):
            continue
        ok, duration = valid_scene_file(src)
        if not ok:
            continue
        dest = OUT / reel_id / f'scene_{scene_index:02d}.mp4'
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        restored.append({
            'reel_id': reel_id, 'scene_index': scene_index,
            'path': str(dest.relative_to(WORK)), 'bytes': dest.stat().st_size,
            'duration_seconds_target': float(item.get('duration_seconds_target', duration)), 'generation_elapsed_seconds': float(item.get('generation_elapsed_seconds', 0) or 0),
            'prompt_id': item.get('prompt_id'), 'restored_from_checkpoint': True,
        })
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
    if not torch.cuda.is_available():
        raise RuntimeError('Kaggle did not provide a CUDA GPU. No CPU fallback was attempted because it would be too slow and low quality.')
    gpu_name = torch.cuda.get_device_name(0)
    total_vram_gib = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    if total_vram_gib < 7.5:
        raise RuntimeError(f'GPU {gpu_name} has only {total_vram_gib:.1f} GiB VRAM. The Wan2.2 5B Q4 path requires a larger GPU; no CPU or paid fallback was attempted.')
    free = shutil.disk_usage(WORK).free / (1024**3)
    if free < 14.5:
        raise RuntimeError(f'Only {free:.1f} GiB free disk space; the open-weight 5B GGUF + text encoder + VAE need about 11 GiB plus runtime/output. Aborting before download.')
    print(f'GPU={gpu_name}; total_vram={total_vram_gib:.1f} GiB; free_disk={free:.1f} GiB')

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

    # Install runtime/node dependencies while allowing the Kaggle image's CUDA-enabled Torch to satisfy existing requirements.
    run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(COMFY / 'requirements.txt')], timeout=1800)
    req = gguf_dir / 'requirements.txt'
    if req.exists():
        run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(req)], timeout=900)
    else:
        run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', 'gguf'], timeout=900)

    # FFmpeg exists in many Kaggle images; install only if missing.
    if shutil.which('ffmpeg') is None:
        run(['bash', '-lc', 'apt-get update -qq && apt-get install -y ffmpeg'], timeout=900)

    # Ensure the one download helper exists without changing the notebook's CUDA-enabled Torch.
    run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', 'huggingface_hub'], timeout=900)
    try:
        import cv2  # noqa: F401
    except ImportError:
        run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', 'opencv-python-headless==4.10.0.84'], timeout=900)
    try:
        import transformers  # noqa: F401
    except ImportError:
        run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', 'transformers>=4.46,<5'], timeout=900)

    # Resolve large licensed model files into Hugging Face cache and symlink them into ComfyUI model folders.
    from huggingface_hub import hf_hub_download, model_info
    paths = {
        'unet': ('timfromhcs/Wan2.2-TI2V-5B-GGUF', 'Wan2.2-TI2V-5B-Q4_K_M.gguf', COMFY / 'models' / 'unet' / 'Wan2.2-TI2V-5B-Q4_K_M.gguf'),
        # The Wan2.2 repackaged snapshot contains the compatible UMT5 text encoder and Wan2.2 VAE.
        'clip': ('Comfy-Org/Wan_2.2_ComfyUI_Repackaged', 'split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors', COMFY / 'models' / 'text_encoders' / 'umt5_xxl_fp8_e4m3fn_scaled.safetensors'),
        'vae': ('Comfy-Org/Wan_2.2_ComfyUI_Repackaged', 'split_files/vae/wan2.2_vae.safetensors', COMFY / 'models' / 'vae' / 'wan2.2_vae.safetensors'),
    }
    model_revisions = {}
    locked_revisions = lock.get('model_revisions') if isinstance(lock.get('model_revisions'), dict) else {}
    for key, (repo, filename, dest) in paths.items():
        dest.parent.mkdir(parents=True, exist_ok=True)
        revision = locked_revisions.get(key)
        if revision and not re.fullmatch(r'[0-9a-f]{40}', str(revision)):
            raise RuntimeError(
                f'Invalid locked Hugging Face revision for {key}: {revision!r}. '
                'Expected an immutable 40-character snapshot commit SHA, not a model folder name.'
            )
        if dest.exists() or dest.is_symlink():
            # Reuse only a real snapshot link whose immutable commit can be independently recovered.
            if dest.is_symlink():
                model_revisions[key] = hf_cache_revision(dest)
                if revision and model_revisions[key] != revision:
                    raise RuntimeError(
                        f'Existing {key} model symlink resolves to {model_revisions[key]}, '
                        f'but the manifest locks {revision}.'
                    )
                continue
            raise RuntimeError(f'Model path already exists as a non-symlink; refusing to guess revision: {dest}')
        print(f'Downloading model component: {key} ({repo}/{filename})' + (f' at locked revision {revision}' if revision else ' at current revision for first lock'))
        kwargs = {'repo_id': repo, 'filename': filename, 'cache_dir': str(HF_CACHE)}
        if revision:
            kwargs['revision'] = revision
        cached = Path(hf_hub_download(**kwargs))
        model_revisions[key] = hf_cache_revision(cached)
        if revision and model_revisions[key] != revision:
            raise RuntimeError(
                f'Downloaded {key} snapshot {model_revisions[key]} does not match the locked SHA {revision}.'
            )
        dest.symlink_to(cached)
    depth_revision = locked_revisions.get('depth')
    depth_info = model_info('depth-anything/Depth-Anything-V2-Small-hf', revision=depth_revision)
    resolved_depth_revision = str(getattr(depth_info, 'sha', '') or '').strip()
    if not re.fullmatch(r'[0-9a-f]{40}', resolved_depth_revision):
        raise RuntimeError('Depth Anything V2 model did not resolve to an immutable commit SHA.')
    if depth_revision and resolved_depth_revision != depth_revision:
        raise RuntimeError(f'Depth model revision drift: expected {depth_revision}, resolved {resolved_depth_revision}.')
    model_revisions['depth'] = resolved_depth_revision
    return {
        'gpu': gpu_name,
        'depth_model_revision': resolved_depth_revision,
        'comfyui_commit': comfy_sha,
        'comfyui_gguf_commit': gguf_sha,
        'model_revisions': model_revisions,
        'runtime_packages': runtime_package_versions(),
    }


def wait_for_comfy(base='http://127.0.0.1:8188', timeout=600):
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + '/object_info', timeout=5) as r:
                if r.status == 200:
                    body = json.loads(r.read().decode('utf-8'))
                    required = ['UnetLoaderGGUF', 'CLIPLoader', 'VAELoader', 'CLIPTextEncode', 'ModelSamplingSD3', 'KSampler', 'Wan22ImageToVideoLatent', 'VAEDecode', 'CreateVideo', 'SaveVideo']
                    missing = [name for name in required if name not in body]
                    if missing:
                        raise RuntimeError('ComfyUI did not register required native/custom nodes: ' + ', '.join(missing))
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
    narrative_role = str(beat.get('narrative_role') or ('hook' if scene_index == 1 else 'payoff' if scene_index == total_scenes else 'intermediate')).strip().lower()
    state_change = str(beat.get('state_change') or beat.get('visual_direction') or 'Preserve the beat-specific action and visual meaning.').strip()
    causal_link = str(beat.get('causal_link') or 'Preserve the approved order and causal relationship of the screenplay.').strip()
    if not narrative_role or len(state_change.split()) < 3 or len(causal_link.split()) < 3:
        raise ValueError(f'Scene {scene_index} is missing its narrative role, state change or causal link.')
    style = (
        'Mature semi-painterly 2.5D Indian graphic-novel motion-comic cinema, clearly illustrated rather than photoreal live action, '
        'layered foreground/midground/background cues, tactile brush-textured surfaces, restrained expressive character design, '
        'warm tungsten interiors, monsoon blues and rich shadows when appropriate, physically plausible subtle movement, '
        'motivated practical lighting, coherent cinematic colour. Vertical 9:16 composition, one clear action, clean visual hierarchy. '
        'No text or typography is to appear in-frame. '
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
    g['55'] = node_prompt(objects, 'Wan22ImageToVideoLatent', {
        'width': 704, 'height': 1280, 'length': target_frames, 'batch_size': 1, 'vae': ['39', 0]
    })
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


def create_25d_parallax_clip(source: Path, destination: Path, duration: float, depth_estimator):
    """Extract, stylize and depth-warp one scene keyframe into a real parallax video."""
    import math
    import numpy as np
    import cv2
    from PIL import Image, ImageFilter, ImageOps

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

    width, height, fps = 704, 1280, 24
    frame_count = max(61, int(math.ceil(duration * fps)))
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
        for frame_index in range(frame_count):
            progress = frame_index / max(1, frame_count - 1)
            eased = math.sin(math.pi * progress)
            zoom = 1.0 + 0.018 * progress
            parallax_x = disparity * (14.0 * eased)
            parallax_y = disparity * (6.0 * eased)
            map_x = ((grid_x - center_x) / zoom + center_x + parallax_x).astype(np.float32)
            map_y = ((grid_y - center_y) / zoom + center_y + parallax_y).astype(np.float32)
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
    valid, measured = valid_scene_file(temporary)
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
        "camera_motion": "depth-displaced parallax + 1.8% eased push-in",
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    result_manifest = {
        'job_id': MANIFEST.get('job_id'), 'status': 'running', 'model': 'Wan2.2 TI2V 5B Q4_K_M GGUF',
        'license_note': 'Wan2.2 upstream is Apache-2.0; this quantized derivative has its own attribution/notice. Review licenses before commercial use.',
        'scenes': [], 'parallax_scenes': [], 'visual_pipeline': 'hybrid_25d_motion_comic_v1',
        'depth_model': 'depth-anything/Depth-Anything-V2-Small-hf', 'depth_model_license': 'Apache-2.0',
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
        objects = wait_for_comfy()
        result_manifest['comfy_nodes_checked'] = True
        for reel in MANIFEST.get('reels', []):
            reel_id = reel['reel_id']
            for i, beat in enumerate(reel['beats'], start=1):
                final_out = OUT / reel_id / f'scene_{i:02d}.mp4'
                if final_out.exists() and final_out.stat().st_size > 100_000:
                    continue
                prefix = f"bsk/{reel_id}/scene_{i:02d}"
                before = time.time()
                scene_started = time.monotonic()
                graph = build_api_workflow(objects, beat, reel, i, prefix)
                prompt_id = post_prompt(graph)
                result_manifest['current_scene'] = {
                    'reel_id': reel_id, 'scene_index': i, 'target_frames': int(beat.get('target_frames', 81)),
                    'prompt_id': prompt_id, 'queued_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                }
                write_json(OUT / 'gpu_output_manifest.json', result_manifest)
                print(f"Queued {reel_id} scene {i}/{len(reel['beats'])}: {prompt_id}", flush=True)
                history = wait_prompt(prompt_id)
                result_manifest.pop('current_scene', None)
                source = latest_video(output_dir, before, prefix)
                transcode_scene(source, final_out)
                result_manifest['scenes'].append({
                    'reel_id': reel_id, 'scene_index': i, 'path': str(final_out.relative_to(WORK)),
                    'bytes': final_out.stat().st_size, 'duration_seconds_target': float(beat.get('target_frames', 81)) / 24.0,
                    'generation_elapsed_seconds': round(time.monotonic() - scene_started, 2),
                    'prompt_id': prompt_id, 'comfy_history_status': history.get('status', {}),
                })
                # Persist an atomic, hash-verified checkpoint after EVERY completed scene.
                write_checkpoint_manifest(result_manifest, 'running')
                # Delete ComfyUI's own large intermediate source after the compressed clip is verified.
                try:
                    source.unlink()
                except OSError:
                    pass
        depth_estimator = None
        for reel in MANIFEST.get('reels', []):
            reel_id = reel['reel_id']
            for scene_index in range(1, len(reel.get('beats', [])) + 1):
                source = OUT / reel_id / f'scene_{scene_index:02d}.mp4'
                parallax = OUT / reel_id / f'scene_{scene_index:02d}_25d.mp4'
                valid_source, scene_duration = valid_scene_file(source)
                if not valid_source:
                    raise RuntimeError(f'Missing Wan source scene for 2.5D derivation: {source}')
                valid_parallax, existing_duration = valid_scene_file(parallax)
                if valid_parallax:
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
                metadata = create_25d_parallax_clip(source, parallax, scene_duration, depth_estimator)
                result_manifest['parallax_scenes'].append({
                    'reel_id': reel_id, 'scene_index': scene_index,
                    'depth_model_revision': toolchain_info['depth_model_revision'],
                    'path': str(parallax.relative_to(WORK)), **metadata,
                })
                write_json(OUT / 'gpu_output_manifest.json', result_manifest)
                print(f"Created depth-parallax scene {reel_id} {scene_index}: {metadata['duration_seconds']:.2f}s", flush=True)
        expected = sum(len(r.get('beats', [])) for r in MANIFEST.get('reels', []))
        found = sum(1 for r in MANIFEST.get('reels', []) for i in range(1, len(r.get('beats', [])) + 1) if (OUT / r['reel_id'] / f'scene_{i:02d}.mp4').exists())
        if found != expected:
            raise RuntimeError(f'Only {found}/{expected} AI scene clips passed generation; refusing to deliver partial batch.')
        result_manifest.update({
            'status': 'complete', 'expected_scenes': expected,
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
        # Keep exit 1 so Kaggle status exposes the failed run; output JSON remains for diagnosis.
        raise
    finally:
        if server and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=30)
            except subprocess.TimeoutExpired:
                server.kill()
        # Do not include the large ComfyUI repository, model symlinks or HF cache in kernel outputs.
        if COMFY.exists():
            shutil.rmtree(COMFY, ignore_errors=True)


if __name__ == '__main__':
    main()
