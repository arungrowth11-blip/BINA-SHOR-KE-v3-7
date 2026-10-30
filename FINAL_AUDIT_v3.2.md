# BINA SHOR KE — Independent Final Audit v3.2

## What was re-reviewed

- All source files and both GitHub Actions workflows.
- Kaggle worker dispatch, ComfyUI graph construction, model downloads, output retrieval, retry/finalization state, Telegram checkpointing, TTS cache, history and manual insight ingestion.
- The 32-test v3.1 suite; the v3.2 package adds a 10k-ambition editorial readiness rubric and benchmark-gated weekly dispatch.
- Current official model, Meta originality, Gemini TTS and Kaggle session documentation.

## New v3.2 safeguards

1. **10k-view ambition Director index:** `quality_report.json` and `publish.txt` now include a weighted 0–100 editorial readiness index. It assesses hook, progression, payoff, originality, meaningful creative contribution, share value, visual prompt quality, continuity, voice rhythm, readability and safety. It explicitly outputs no probability or forecast of 10,000 views. A high score is a pre-publish quality screen, not a promise of reach.
2. **GPU runtime benchmark:** the Kaggle worker records per-scene generation time and total worker time. After a successful one-Reel run, the system estimates a conservative three-Reel batch time using a 1.5x safety factor. `plan-week` is blocked until that benchmark exists and estimates no more than 8 hours, leaving buffer against Kaggle's documented 12-hour notebook session ceiling. This is still an estimate; check actual account quota and GPU availability.
3. **No silent degradation:** no paid endpoint, CPU video-generation fallback, or automatic Facebook publishing. Failures alert and preserve state for diagnosis.

## Important remaining limits / risks

- **No live integration has been executed.** Offline tests cannot validate the user's Kaggle account, API token, model download availability, free quota, ComfyUI's live node schema, actual GPU memory/time, Gemini free quota or Telegram delivery.
- **One-Reel qualification is mandatory.** Do not run `plan-week` before `plan-one` succeeds and the GPU benchmark is stored. The first model download can consume substantial time and disk.
- **Static graphics are not yet FLUX-generated.** Existing custom graphics/overlays/covers are locally rendered with Pillow/FFmpeg and reliable Hindi typography. This is not equivalent to a photorealistic image-generation model. FLUX.1 [schnell] is a commercially usable Apache-2.0 open-weight still-image candidate, but integrating it into the same free Kaggle worker adds model download, RAM/VRAM, storage and session-time risks. Keep it as a separately qualified optional stage; do not block the reliable base pipeline on it.
- **Kling is primarily a video-generation product.** Compare generated video with video models, and static key art with image models. A static graphics engine cannot replace temporal video generation.
- **Wan2.2 TI2V-5B Q4_K_M:** 704x1280 scene generation is a serious open-weight trial, not a guarantee of artifact-free realism or Higgsfield parity. Export upscaling does not create native detail. Inspect the whole moving clip, not only six sampled frames.
- **Kaggle quota/session:** official docs describe up to 30 GPU hours/week (sometimes variable) and a 12-hour notebook session maximum; GPU access may queue or be unavailable. One 3-Reel job is now benchmark-gated, but no free service is guaranteed for a year.
- **AI editorial roles are not 10,000 independent human reviewers.** They are structured role-based passes. The final full-video review on a phone remains mandatory.
- **Meta distribution:** no internal rubric can know Meta's per-viewer ranking or guarantee 10k views, shares, recommendations or monetization. Meta's own 2026 engineering describes interest matching, novelty, audio, production style and viewer feedback—not a public creator formula.

## Recommended production operating rule

1. Run `preflight`.
2. Run `plan-one` and wait for the actual Telegram package.
3. Review every second of video and audio on a phone; reject visible AI defects.
4. Only if the one-Reel run is successful and its measured benchmark is <=8h for the estimated 3-Reel batch, try `plan-week` once.
5. If the batch takes too long or fails, keep one Reel per run; never create parallel Kaggle sessions to evade quota.
6. Log `/published` only after actual manual publishing; enter real 24h and 7d metrics. Never train/adapt from guessed numbers.

## Offline verification

- `python -m unittest discover -s tests -v`
- `python -m py_compile scripts/*.py`
- Both workflow YAML files parse in the offline validation used for this release.

Offline checks are not a live GPU/API end-to-end test.
