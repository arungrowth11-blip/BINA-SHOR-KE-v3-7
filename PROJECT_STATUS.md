# BINA SHOR KE — Current Project Status

**As of 24 November 2026 (Asia/Kolkata).** This file describes the current feature branch, not a production release. PR #10 and PR #11 remain draft/open and are not merged.

## Selected architecture

The selected primary renderer is **image-first, primarily 2.5D illustrated motion-comic cinema**:
- FLUX.1 Schnell Q4_K_S produces one 704×1280 illustrated still for each source story beat.
- Depth Anything V2 produces depth maps; OpenCV/FFmpeg create genuine parallax motion from the stills.
- The primary storyboard routes 100% of editorial shots to depth-parallax. It does not generate Wan video clips.
- Final editorial output is 1080×1920, 30 FPS.
- Wan2.2 remains only as a backward-compatible legacy route for older manifests/recovery. It is not the default renderer.
- Human review remains required; the factory does not auto-publish to Facebook/Instagram/YouTube.

## Implemented in the feature branch

- Voice-first screenplay/timing and speaker-specific Hindi WAV generation.
- Adaptive story duration/shot planning and genre-specific colour, lighting and camera grammar.
- FLUX still-image ComfyUI graph, immutable model-revision capture, vertical image validation and SHA-256 manifests.
- Depth Anything V2 parallax generation directly from still PNGs; pure-parallax FFmpeg assembly without dummy hero-video inputs.
- Separate image-first toolchain lock and runtime benchmark logic; legacy Wan lock is kept separate.
- Private Kaggle PNG still checkpoint save/restore, hash validation and regeneration of missing parallax assets. Recovery manifests now also preserve the exact ComfyUI/GGUF commits, FLUX/CLIP/T5/VAE/Depth revisions and runtime package versions; a resumed worker refuses to mix checkpoints with a different model/runtime build.
- Image-first recovery estimates rebuild the parallax phase from restored PNG stills. At least five measured per-scene parallax timings are required; without enough measurements the estimate is unknown/unsafe and automatic resume is blocked rather than assuming a 1.5-hour placeholder.
- VLM schema validation (finite numeric 1–5 scores, mandatory boolean critical flag), full-video black/freeze scan, 1 FPS Hindi+English Tesseract OCR for leaked internal labels, and fail-closed delivery/approval gate. Gemini visual-review outages may use the explicitly labelled local-pass/manual-review route only when deterministic local frame QA, OCR and full-video motion QA pass.
- Final encoded AAC is measured after export for integrated loudness (-18 to -14 LUFS) and true peak (≤ -1 dBTP). One 48 kHz remaster is allowed, followed by a second measurement; a second failure blocks delivery.
- Weekly 3-Reel plan gate requires one complete image-first Reel, VLM/OCR/motion/technical QA, all four Telegram delivery receipts, owner /approve and a qualified image-first GPU estimate.
- English/Hindi README, pilot design note, and operator notes updated for the new default and explicit qualification gaps.
- FLUX AE VAE uses a public mirror with a fixed SHA-256 check to avoid relying on a gated BFL repository/token.

## CI and live qualification status

- PR #11 exact-head Offline Quality Gates run **45372103267**, head **8d62bf2f4fc5688c073a452c1dc951ec73151cae**: **284 tests passed**, Python compilation passed, and all six workflow YAML files validated.
- PR #10 exact-head Offline Quality Gates run **45311586221**: success. These offline checks are not proof of a live production Reel.
- Live image-first FLUX/Kaggle render: one real attempt ran on 23 November 2026 and produced a Reel/cover artifact. Finalization stopped because Gemini visual QA returned HTTP 503; the Reel was not delivered to Telegram or owner-approved. This is an attempted render, not a qualified production success.
- Image-first ComfyUI/model toolchain lock and measured GPU benchmark: **not yet recorded**; the file data/image_toolchain_lock.json is created only after a complete live worker manifest is returned and verified.
- Historical Wan benchmark remains about 10.32 hours for a 3-Reel batch and is unqualified. It is not valid evidence for the FLUX image-first renderer.
- Historical Reel “मग का कर्ज” was produced using the previous Wan-based path and delivered to Telegram for manual review. It has not been owner-approved as a new image-first qualification Reel.
- No successful image-first Telegram delivery receipt or owner approval exists yet. The generated MP4/cover were retained in the GitHub Actions artifact for diagnosis.
- Six-Reel controlled experiment and actual platform analytics feedback have not been completed.
- Target 18–28 minutes per Reel is a research target, not a measured runtime.

## Explicit remaining engineering gaps

1. True image-conditioned character-sheet/reference conditioning across all generated stills and across episodes. Current FLUX prompts repeat the cast description/wardrobe and VLM checks sampled continuity, but prompt repetition is not an identity lock.
2. The current plan produces one source still per story beat (six source beats), then expands these into 12–16 editorial cuts using camera crops/retiming. It does not yet produce 12–16 independent still keyframes.
3. Live GPU memory/disk/model-node compatibility, end-to-end FLUX still generation, parallax encoding and total runtime must be qualified on Kaggle.
4. Full one-Reel QA, physical full-video playback, three independent manual Pass/Fail reviews, owner approval and successful Telegram delivery must pass before weekly planning unlocks.
5. Six-Reel experiment, 72-hour per-platform analytics, story-category performance and style/voice A/B tests remain pending.
6. Pre-baked immutable container / dependency-cache optimisation to remove the previous cold-start bottleneck is not yet implemented or benchmarked.
7. Human review remains essential for Hindi pronunciation, dialect nuance, story taste, visual identity, cultural context and platform disclosure.

## Persistent data / safety

- data/toolchain_lock.json: legacy Wan toolchain lock only.
- data/image_toolchain_lock.json: separate primary FLUX/Depth toolchain lock; not yet generated by a live qualified run.
- data/pending_gpu_job.json and data/job_archive/: preserve pending/failed job state and recovery evidence.
- data/history.json: stores approved/rejected story and owner qualification state.
- Do not manually mark a GPU benchmark qualified, manually fabricate VLM/OCR/motion pass evidence, or reuse old Wan footage as a new image-first pass.
- No paid model fallback. No automatic publishing. Do not merge/promote without explicit owner approval.
