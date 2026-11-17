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
    "cartoon, illustration, CGI, plastic skin, waxy face, over-smoothing, over-sharpening, "
    "warped architecture, flicker, strobing, jitter, rubber motion, morphing objects, "
    "extra fingers, malformed hands, fused fingers, duplicated people, distorted faces, "
    "unrealistic physics, unnatural reflections, blurry, low-resolution, oversaturated"
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
            'duration_seconds_target': 81/24, 'generation_elapsed_seconds': float(item.get('generation_elapsed_seconds', 0) or 0),
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
    write_json(OUT / 'GPU_JOB_ERROR.json', {
        'status': 'failed', 'error_type': type(exc).__name__, 'error': str(exc)[:5000],
        'stage': 'kaggle_gpu_render', 'manifest_id': MANIFEST.get('job_id'),
    })


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
        "tokenizers", "einops", "torchsde", "requests",
    )
    observed = {}
    for package in distributions:
        try:
            observed[package] = version(package)
        except PackageNotFoundError:
            observed[package] = "not-installed"
    return observed

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

    # Resolve large licensed model files into Hugging Face cache and symlink them into ComfyUI model folders.
    from huggingface_hub import hf_hub_download
    paths = {
        'unet': ('timfromhcs/Wan2.2-TI2V-5B-GGUF', 'Wan2.2-TI2V-5B-Q4_K_M.gguf', COMFY / 'models' / 'unet' / 'Wan2.2-TI2V-5B-Q4_K_M.gguf'),
        'clip': ('Comfy-Org/Wan_2.1_ComfyUI_repackaged', 'split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors', COMFY / 'models' / 'text_encoders' / 'umt5_xxl_fp8_e4m3fn_scaled.safetensors'),
        'vae': ('Comfy-Org/Wan_2.2_ComfyUI_Repackaged', 'split_files/vae/wan2.2_vae.safetensors', COMFY / 'models' / 'vae' / 'wan2.2_vae.safetensors'),
    }
    model_revisions = {}
    locked_revisions = lock.get('model_revisions') if isinstance(lock.get('model_revisions'), dict) else {}
    for key, (repo, filename, dest) in paths.items():
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() or dest.is_symlink():
            # This worker starts fresh each run; a pre-existing link is unexpected and must not silently change revision.
            if dest.is_symlink():
                model_revisions[key] = Path(dest.resolve()).parent.name
                continue
            raise RuntimeError(f'Model path already exists as a non-symlink; refusing to guess revision: {dest}')
        revision = locked_revisions.get(key)
        print(f'Downloading model component: {key} ({repo}/{filename})' + (f' at locked revision {revision}' if revision else ' at current revision for first lock'))
        kwargs = {'repo_id': repo, 'filename': filename, 'cache_dir': str(HF_CACHE)}
        if revision:
            kwargs['revision'] = revision
        cached = Path(hf_hub_download(**kwargs))
        model_revisions[key] = cached.parent.name
        dest.symlink_to(cached)
    return {
        'gpu': gpu_name,
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
    total_scenes = len(story.get('beats', [])) or 6
    coverage = shot_coverage_instruction(scene_index, total_scenes)
    style = (
        'Photoreal live-action cinema, physically plausible natural movement, realistic skin and material texture, '
        'subtle sensor grain, practical motivated lighting, restrained film colour science, natural imperfect detail. '
        'Vertical 9:16 composition, one clear action, clean visual hierarchy. No text or typography is to appear in-frame. '
    )
    full_prompt = (
        f"{style}\nCONTINUITY / LOOK BIBLE: {bible}"
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
        'width': 704, 'height': 1280, 'length': 81, 'batch_size': 1, 'vae': ['39', 0]
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


def wait_prompt(prompt_id, timeout=2700, base='http://127.0.0.1:8188'):
    import requests
    deadline = time.time() + timeout
    last_status = None
    while time.time() < deadline:
        try:
            r = requests.get(f'{base}/history/{prompt_id}', timeout=20)
            r.raise_for_status()
            data = r.json()
            if prompt_id in data:
                item = data[prompt_id]
                status = item.get('status', {})
                last_status = status
                if status.get('completed') is True or status.get('status_str') == 'success':
                    return item
                if status.get('status_str') in ('error', 'failed'):
                    raise RuntimeError('ComfyUI generation failed: ' + json.dumps(status, ensure_ascii=False)[:3000])
        except requests.RequestException:
            pass
        time.sleep(8)
    raise TimeoutError(f'ComfyUI scene generation timed out after {timeout}s. Last status={last_status}')


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


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    result_manifest = {
        'job_id': MANIFEST.get('job_id'), 'status': 'running', 'model': 'Wan2.2 TI2V 5B Q4_K_M GGUF',
        'license_note': 'Wan2.2 upstream is Apache-2.0; this quantized derivative has its own attribution/notice. Review licenses before commercial use.',
        'scenes': [], 'started_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    server = None
    worker_started = time.monotonic()
    try:
        toolchain_info = install_comfyui()
        result_manifest['gpu'] = toolchain_info['gpu']
        result_manifest['comfyui_commit'] = toolchain_info['comfyui_commit']
        result_manifest['comfyui_gguf_commit'] = toolchain_info['comfyui_gguf_commit']
        result_manifest['model_revisions'] = toolchain_info['model_revisions']
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
                print(f"Queued {reel_id} scene {i}/{len(reel['beats'])}: {prompt_id}", flush=True)
                history = wait_prompt(prompt_id)
                source = latest_video(output_dir, before, prefix)
                transcode_scene(source, final_out)
                result_manifest['scenes'].append({
                    'reel_id': reel_id, 'scene_index': i, 'path': str(final_out.relative_to(WORK)),
                    'bytes': final_out.stat().st_size, 'duration_seconds_target': 81/24,
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
