# BINA SHOR KE — Annual Operations Playbook (Primary 2.5D)

## हर Reel के लिए
1. Original Hindi story with a concrete human detail, believable contradiction, causal chain and meaningful payoff.
2. Generate/validate script and dialogue; lock voice direction and actual WAV durations before visuals.
3. Generate FLUX stills (one per source beat), create Depth Anything maps and deterministic camera-driven 2.5D clips.
4. Validate hashes, audio/subtitle sync, final duration, resolution/FPS, VLM scorecard, OCR and full-video motion diagnostics.
5. Send only a fully QA-passed package to Telegram. Watch/listen to the whole Reel. Owner approval is required before any manual upload.
6. Record actual platform performance only after publication; missing metrics remain unknown, never zero.

## हर सप्ताह
- Start with one image-first `plan-one` Reel only.
- Confirm it used FLUX still generation + Depth Anything parallax, not Wan video generation.
- Verify full visual/audio QA, all four Telegram delivery steps and owner approval.
- Do not run `plan-week` until the separate image-first GPU benchmark is measured and the conservative three-Reel estimate is <=8h.
- Prior Wan2.2 benchmark (10.32h for three Reels) does not qualify or disqualify the new FLUX renderer; it is a different compute path.
- No quota bypass, parallel account trick, paid fallback or automatic social publishing.

## हर महीने
- Review current-head GitHub Actions tests and logs. Check the current PR head, not a stale successful run.
- Review Kaggle GPU availability, VRAM/disk preflight, runtime timings and model revision locks.
- Back up `data/history.json`, `data/performance_log.csv`, `data/telegram_state.json`, `data/toolchain_lock.json`, `data/image_toolchain_lock.json` (once created), and `data/pending_gpu_job.json` privately.
- Review Telegram delivery and feedback-sync receipts. Don't infer delivery from an offline test.
- Audit model repo revisions, exact quantized derivative notices, ComfyUI/GGUF compatibility and VAE checksum.

## हर तीन महीने
- Review platform originality and AI disclosure requirements.
- Review model/library licences and third-party notices before any commercial use.
- Compare style variation: palette, lighting and camera grammar should differ by story genre to reduce aesthetic fatigue.
- Run the controlled six-Reel experiment and analyse shares/sends, saves, watch time, completion and follows per view. Don't alter the factory based on one Reel.
- Compare AI Hindi TTS against a short human voice recording; only change the voice system after a measured paired test and owner review.
- Review character consistency across the sample. Prompt repetition is not equivalent to image-conditioned reference locking.

## Failure and recovery
- GPU failure: use the saved private checkpoint only if the exact job identity, hashes and expected output are verified. FLUX stills are PNG; old Wan jobs are MP4. Never mix them.
- OCR/VLM/motion QA incomplete or unavailable: delivery remains blocked; don't mark it as manual pass.
- Character drift, wrong clothing, mangled anatomy, broken Devanagari or leaked internal labels: reject/regenerate the affected assets, then rerun all relevant QA.
- Incomplete image-first model lock or missing GPU measurement: one-Reel qualification remains pending; weekly production stays locked.
- Failed/ambiguous Kaggle dispatch: verify private kernel history before choosing any recovery action. Never create a duplicate GPU run based on assumption.
- Hard infrastructure loss may make an unfinished remote output unrecoverable; checkpointing is best-effort, not a guarantee.

## Production principles
**Quality > cadence. Story causality > random twist. Natural Hindi > heavy vocabulary. Character continuity > one-off spectacle. Saves/shares and actual retention > vanity likes. Human judgement remains the final release gate.**
