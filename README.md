# BINA SHOR KE — AI Cinematic Story Factory v3.7 P0 Reliability

A private GitHub Actions + Kaggle GPU pipeline for original Hindi faceless Reels. The selected primary architecture is **image-first 2.5D motion-comic cinema**: write and approve the story, generate and measure Hindi speaker WAVs, produce one illustrated FLUX still per narrative beat, derive Depth Anything V2 maps, create deterministic 2.5D parallax clips, then assemble a 30 FPS Reel. Wan2.2 remains as a backward-compatible legacy path for older manifests only. The new image-first path is implemented in this feature branch but is **not yet live GPU-qualified**. Automated editorial, post-production, OCR/visual/audio QA, checkpoint recovery and private Telegram delivery remain in scope. **Facebook publishing stays manual.**

## Architecture

- **Primary writer:** Gemini 3.8 Flash Free Tier.
- **Optional text failover / independent editor:** Groq `openai/gpt-oss-120b` Free, Mistral `ministral-8b-latest` in Studio Free mode, and Cloudflare Workers AI `@cf/meta/llama-3.1-8b-instruct` only with explicit Free-plan opt-in. Requests fail over sequentially; there is no paid route or parallel prompt fan-out.
- **Narration:** Gemini 3.8 Flash-Lite TTS generates separate character dialogue turns with speaker-specific voice IDs. Each WAV is validated and measured before the final editorial shot prompts and image-first still/parallax dispatch. Voice mappings are candidates requiring Hindi listening review; they are not guarantees of a character's exact age or acting quality.
- **Primary visual generation:** FLUX.1 Schnell Q4_K_S GGUF through ComfyUI, 4-step still-image graphs, one vertical 704×1280 still per narrative beat. Pinned Depth Anything V2 Small estimates depth; OpenCV/FFmpeg generates camera-driven parallax motion. Editorial master is 1080×1920 at 30 FPS. The default story plan routes 100% of editorial shots through depth-parallax and dispatches no Wan video calls.
- **Legacy renderer:** Wan2.2 TI2V-5B Q4_K_M GGUF remains available for already-created legacy jobs and older manifests; it is not the default generation route.
- **Qualification status:** image-first workflow has offline code/tests but still requires a real Kaggle one-Reel render, model/runtime lock, measured GPU benchmark, output inspection and human visual approval before weekly batch qualification.
- **Post:** FFmpeg/Pillow, custom typography, subtitles, overlays, cover and locally synthesized ambience.
- **Delivery/learning:** private Telegram; `/approve` or `/reject` records the final owner decision; manual publishing; `/published` and `/insights` feed measured history.

## Voice-first dialogue and 3D pilot

- Script/cast and dialogue turns are locked first. Each speaker turn gets its own TTS request and a cache key that includes exact text, acting direction and voice ID.
- Final visual beats and editorial shot timing are generated only after WAV durations and speaker timestamps are measured. FLUX stills are narrative keyframes; depth-parallax clips are encoded against the exact voice-beat duration. Dialogue is never shortened to fit a fixed clip.
- The persistent character registry stores metadata and explicit reuse IDs. FLUX prompts receive the same per-Reel visual bible and character appearance/wardrobe descriptions. **True image-conditioned character-sheet locking across all generated stills and across episodes is not yet qualified**; it remains a visual QA and asset-library gap. Binary Blender assets remain outside Git.
- Blender is an isolated stylised two-character pilot only. Its current mouth movement is amplitude-driven, not phoneme-accurate Hindi lip-sync. It is not part of the primary 2.5D renderer.

## Storytelling quality system

Twelve rotating narrative devices reduce repeated formula. Every concept requires a small lived-in human detail, a character contradiction, the cost of a choice and an emotional aftertaste. An independent critic scores human specificity, emotional resonance, dialogue naturalness, originality, payoff, story progression, visual feasibility and platform safety. Weak concepts are revised once, then rejected. The 0–100 “10K-ambition” index is an editorial readiness rubric, **not a view prediction**.

## No-code setup

See [`README_HINDI.md`](README_HINDI.md) for the Windows/GitHub Desktop walkthrough. Required Actions secrets:

- `GEMINI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `KAGGLE_USERNAME`
- `KAGGLE_KEY`

Recommended optional free text keys: `GROQ_API_KEY` and `MISTRAL_API_KEY`. Cloudflare uses `CF_ACCOUNT_ID`, `CF_API_TOKEN`, and exact opt-in secret `CF_WORKERS_AI_FREE_ONLY=YES`; it is OFF by default because Workers Paid usage above the free allocation can be billable. Do not enable it unless you have confirmed the account is on Workers Free. Do not configure billing/Pay-as-you-go for Gemini, Groq or Mistral. Disable GitHub Actions paid overage.

Run: `preflight` → `plan-one` → confirm the Reel is QA-passed and delivered to Telegram → send `/approve title=Exact Reel Title` → run `plan-week`. The workflow re-checks Telegram updates and requires the persistent one-Reel qualification record plus a qualified GPU benchmark before dispatching a weekly batch. The system has not yet been live-tested against your API/GPU/Telegram accounts. Free provider quotas and Kaggle GPU availability may change; the software stops rather than selecting a paid fallback.

## Important limitations

No guarantee of artifact-free video, audience distribution, 10,000 views, monetization or Meta recommendation eligibility. VLM frame review, 1 FPS OCR sampling and full-video black/freeze diagnostics supplement (but do not replace) one full human playback. Image-first PNG stills and legacy MP4 scene checkpoints are hash-verified for private Kaggle recovery; hard infrastructure loss may still prevent recovery. Gemini Free Tier prompts/responses may be used to improve Google products; only invented, public-safe stories belong in this workflow. Review FLUX Schnell/quantization, encoder, VAE, ComfyUI-GGUF and Depth Anything licences/notices before commercial use.

## References

- [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) · [Gemini speech generation](https://ai.google.dev/gemini-api/docs/speech-generation)
- [Groq models](https://console.groq.com/docs/models) · [Groq rate limits](https://console.groq.com/docs/rate-limits)
- [Mistral Free mode](https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key)
- [Cloudflare Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/) · [OpenAI-compatible endpoints](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/)
- [Hugging Face Inference Providers pricing](https://huggingface.co/docs/inference-providers/pricing)
- [Kaggle GPU usage](https://www.kaggle.com/docs/efficient-gpu-usage) · [Wan2.2 TI2V-5B GGUF and license/NOTICE](https://huggingface.co/timfromhcs/Wan2.2-TI2V-5B-GGUF)


## v3.5 recovery and candidate lab

- Each completed Kaggle scene is atomically written and inventoried with SHA-256, byte size and duration. After a GPU failure, the poller attempts a private Kaggle Dataset checkpoint and hash-verified restore. Auto resume is <=4h estimate, owner-triggered <=8h, maximum two attempts; ambiguous pushes require owner confirmation. This is best-effort, not guaranteed recovery.
- Local faster-whisper large-v3-turbo CPU int8 compares Hindi narration to intended script. FFmpeg scans full video for black and frozen intervals; visual AI QA samples up to 18 frames across beats. None proves natural voice acting or catches every temporal artifact.
- `docs/MODEL_LAB_BENCHMARK_HINDI.md` documents isolated tests for HunyuanVideo-1.5 (video), FLUX.1 schnell (stills) and Indic-Speak (local TTS). Candidates need 10 paired samples, rights review, quality uplift, runtime guard and three shadow runs before promotion. They are not installed into weekly production.
- Run `python scripts/model_lab.py template --candidate hunyuanvideo-1.5 --output output/model_lab/hunyuan.json` (or `flux.1-schnell` / `indic-speak`) to make a scorecard.


## v3.7 P0 reliability corrections

- Fixed Kaggle worker manifest injection so the generated `MANIFEST` is a dictionary; the worker also validates the injected type at startup.
- Weekly three-Reel planning now requires a successfully finalized image-first 2.5D Reel, passed VLM/OCR/motion/technical QA, all four Telegram delivery steps, and an owner `/approve` record. The separate FLUX + depth image-first GPU runtime benchmark remains an independent gate; the old Wan benchmark cannot qualify the new renderer.
- Telegram feedback drain and persistence steps are skipped unless `TELEGRAM_BOT_TOKEN` is configured.
- Empty/unset `KAGGLE_KERNEL_SLUG` values resolve to the safe default `bina-shor-ke-studio-video`.
- New plans are blocked while a resumable `gpu_checkpoint_saved` state exists.
- Added adversarial integration tests for generated worker manifest type, Telegram approval qualification, same-run feedback reload, missing-token workflow conditions, empty kernel slug, and checkpoint protection.

This release is offline-tested only. No live Kaggle GPU, external API, or Telegram production run was performed.


## v3.8 adaptive narration timing and rejected-scene recovery

- AI scenes are never accelerated beyond 1.38x. Short narration keeps the source scene at natural speed and pads the audio to the scene boundary; longer narration may use a <=1.20s cloned end-frame hold, below the full-video freeze detector threshold. Longer mismatches still fail closed.
- A one-time `rebuild-rejected-timing` action can re-finalize a single Reel rejected only for narration/video timing, but only after confirming the existing Kaggle kernel is COMPLETE. It reuses the existing scene outputs, does not dispatch another GPU run, and still runs full technical/visual QA and Telegram delivery gates.
- Visual defects, black frames, freeze defects and too-short scenes cannot use this recovery. A repeat timing rebuild is blocked.
- This change does not resolve GitHub-hosted runner provisioning/account-level failures; those must be confirmed by a successful Actions job start.

## Selective upgrades from the separate AI Comedy Factory blueprint

- **Legacy Wan route only:** the six Wan scene prompts receive consistent, story-aware coverage roles. The primary image-first FLUX route now uses the same per-Reel visual bible, cast appearance, wardrobe, narrative role, state change and causal link in every still prompt; true image-conditioned multi-angle character-sheet locking remains outstanding.
- The complete narration + ambience master bus now receives final integrated loudness normalization at -16 LUFS, a -1.5 dBTP target and a final sample limiter. This adapts the source blueprint's broadcast-mastering idea while preserving BINA SHOR KE's quieter mix target.
- Existing provider failover, TTS retry/cache, subtitles/overlays, per-scene continuity bible, checkpoint recovery and technical/visual QA were retained. The new primary FLUX still + Depth Anything parallax path is implemented but not yet live-GPU qualified; Wan2.2 remains only for older manifests.
