# BINA SHOR KE — AI Cinematic Story Factory v3.7 P0 Reliability

A public GitHub source repository with GitHub Actions + Kaggle GPU automation for original Hindi faceless Reels. The selected primary architecture is **image-first 2.5D motion-comic cinema**: write and approve the story, generate and measure Hindi speaker WAVs, produce one illustrated FLUX still per narrative beat, derive Depth Anything V2 maps, create deterministic 2.5D parallax clips, then assemble a 30 FPS Reel. Wan2.2 remains as a backward-compatible legacy path for older manifests only. The new image-first path is implemented in this feature branch but is **not yet live GPU-qualified**. Automated editorial, post-production, OCR/visual/audio QA, checkpoint recovery and private Telegram delivery remain in scope. **Facebook publishing stays manual.**

## Architecture

- **Primary writer:** Gemini 3.8 Flash Free Tier.
- **Optional text failover / independent editor:** Groq `openai/gpt-oss-120b` Free, Mistral `ministral-8b-latest` in Studio Free mode, and Cloudflare Workers AI `@cf/meta/llama-3.1-8b-instruct` only with explicit Free-plan opt-in. Requests fail over sequentially; there is no paid route or parallel prompt fan-out.
- **Narration:** Gemini 3.8 Flash-Lite TTS generates separate character dialogue turns with speaker-specific voice IDs. Each WAV is validated and measured before the final editorial shot prompts and image-first still/parallax dispatch. Voice mappings are candidates requiring Hindi listening review; they are not guarantees of a character's exact age or acting quality.
- **Primary visual generation:** FLUX.1 Schnell Q4_K_S GGUF through ComfyUI, 4-step still-image graphs, one vertical 704×1280 still per narrative beat. Pinned Depth Anything V2 Small estimates depth; OpenCV/FFmpeg generates camera-driven parallax motion. Editorial master is 1080×1920 at 30 FPS. The default story plan routes 100% of editorial shots through depth-parallax and dispatches no Wan video calls.
- **Legacy renderer:** Wan2.2 TI2V-5B Q4_K_M GGUF remains available for already-created legacy jobs and older manifests; it is not the default generation route.
- **Qualification status:** image-first workflow has offline code/tests but still requires a real Kaggle one-Reel render, model/runtime lock, measured GPU benchmark, output inspection and human visual approval before weekly batch qualification.
- **Post:** FFmpeg/Pillow, custom typography, subtitles, overlays, cover and locally synthesized ambience.
- **Final AAC audio QA:** after the final encode, FFmpeg measures integrated loudness and true peak on the actual output file. Accepted range is -18 to -14 LUFS with a -1 dBTP ceiling. At most one 48 kHz AAC remaster is allowed (target -16 LUFS / -2.5 dBTP); the encoded result is measured again. If measurement is unavailable or the remaster remains outside limits, delivery fails closed.
- **Delivery/learning:** private Telegram; `/approve` or `/reject` records the final owner decision; manual publishing; `/published` and `/insights` feed measured history.

## Voice-first dialogue and 3D pilot

- Script/cast and dialogue turns are locked first. Each speaker turn gets its own TTS request and a cache key that includes exact text, acting direction and voice ID.
- Final visual beats and editorial shot timing are generated only after WAV durations and speaker timestamps are measured. FLUX stills are narrative keyframes; depth-parallax clips are encoded against the exact voice-beat duration. Dialogue is never shortened to fit a fixed clip.
- The persistent character registry stores metadata and explicit reuse IDs. FLUX prompts receive the same per-Reel visual bible and character appearance/wardrobe descriptions. **True image-conditioned character-sheet locking across all generated stills and across episodes is not yet qualified**; it remains a visual QA and asset-library gap. Binary Blender assets remain outside Git.
- Blender is an isolated stylised two-character pilot only. Its current mouth movement is amplitude-driven, not phoneme-accurate Hindi lip-sync. It is not part of the primary 2.5D renderer.

## Storytelling quality system

Twelve rotating narrative devices reduce repeated formula. Every concept requires a small lived-in human detail, a character contradiction, the cost of a choice and an emotional aftertaste. An independent critic scores human specificity, emotional resonance, dialogue naturalness, originality, payoff, story progression, visual feasibility and platform safety. Weak concepts are revised once, then rejected. The 0–100 “10K-ambition” index is an editorial readiness rubric, **not a view prediction**.

## Human Reality QA and independent audience review

Every finalized Reel receives a reproducible **10,000-profile synthetic audience simulation** using all 13 editorial-critic dimensions and all 8 rendered-frame VLM dimensions, plus objective technical gates. It reports strengths, weak dimensions and preference-segment reactions. The seed is stable for the same Reel/evidence, and missing evidence is not fabricated. These profiles are simulated preferences, **not real people**; intent percentages are not reach, watch-time, virality or view predictions. This is an evidence-conditioned Monte Carlo model, not 10,000 independent LLM essays or a calibrated platform-performance predictor.

**Normal path:** complete AI evidence and technical QA must pass. The owner must watch the full Reel, obtain separate Pass responses from three independent external viewers, fix any reported shortcomings, and only then send /approve.

**Manual external-review fallback:** if AI semantic evidence is incomplete, delivery is allowed only when deterministic local visual-integrity checks pass, technical checks pass, the full-video motion/black/freeze scan passes, and metadata OCR passes. The Reel is explicitly labelled **AI EVIDENCE INCOMPLETE**. This path is not an AI-QA pass and cannot override a failed objective gate.

The owner watches the entire Reel and asks **three independent external people** to watch it separately. Ask each only for Pass/Fail and what was lacking. No name, Telegram ID, numeric score or other reviewer identity is collected by the bot or stored in the repository. If anyone says Fail, do not approve: send the shortcomings for correction and repeat the review on the corrected Reel. Only when all three pass and the owner has watched the full Reel may the owner send /approve title=Exact Reel Title.

For this fallback, /approve records an explicit **owner-reported attestation** that three independent viewers passed. It is marked owner_attested_not_bot_verified; the software does not claim to have authenticated or independently received their votes. No extra reviewer secrets or Telegram panel setup are required. Facebook publishing remains manual; nothing auto-publishes.

A human opinion cannot override failed technical checks, missing full-video motion diagnostics, OCR failure, corrupt frames or other hard QA failures.
## Telegram state privacy

The Telegram owner chat binding is encrypted at rest in `data/telegram_state.json` using Fernet. Its key is deterministically derived from the already-required `TELEGRAM_BOT_TOKEN` with domain separation, so no additional GitHub secret is required. The numeric update cursor remains persisted beside the ciphertext, preserving Telegram polling and duplicate-update protection. The migration keeps the existing owner binding and cursor; it does not delete or reset either value.

A push that changes `scripts/producer.py` on `feature/human-reality-qa-engine` automatically runs the Telegram feedback workflow, which first migrates any legacy plaintext owner binding and commits the encrypted state before polling updates. Normal weekly/GPU/sync writes also keep the owner binding encrypted. If the bot token is rotated, state decryption fails closed rather than silently discarding the owner binding or cursor; migrate the state before rotating that token.

**Historical privacy limitation:** earlier public commits may still contain the legacy plaintext Telegram chat identifier. This change protects the current state and future commits; it does not rewrite public Git history. The identifier is not a bot credential, but its historical exposure cannot be undone without a separate history rewrite and coordinated clone recovery. This change deliberately does not rewrite history, change repository visibility, or remove any tracked state.

## No-code setup

See [`README_HINDI.md`](README_HINDI.md) for the Windows/GitHub Desktop walkthrough. Required Actions secrets:

- `GEMINI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `KAGGLE_USERNAME`
- `KAGGLE_KEY`

Recommended optional free text keys: `GROQ_API_KEY` and `MISTRAL_API_KEY`. Cloudflare uses `CF_ACCOUNT_ID`, `CF_API_TOKEN`, and exact opt-in secret `CF_WORKERS_AI_FREE_ONLY=YES`; it is OFF by default because Workers Paid usage above the free allocation can be billable. Do not enable it unless you have confirmed the account is on Workers Free. Do not configure billing/Pay-as-you-go for Gemini, Groq or Mistral. Disable GitHub Actions paid overage.

Run: `preflight` → `plan-one` → receive the Reel in Telegram → complete the owner full-playback and three-person Pass/Fail review → send `/approve title=Exact Reel Title` → run `plan-week`. The workflow re-checks Telegram updates and requires the persistent one-Reel qualification record plus a qualified GPU benchmark before dispatching a weekly batch. The system has not yet been live-tested against your API/GPU/Telegram accounts. Free provider quotas and Kaggle GPU availability may change; the software stops rather than selecting a paid fallback.

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
