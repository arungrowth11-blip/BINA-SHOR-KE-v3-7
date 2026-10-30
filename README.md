# BINA SHOR KE — AI Cinematic Story Factory v3.7 P0 Reliability

A private GitHub Actions + Kaggle free-GPU pipeline for original Hindi faceless Reels. The target cadence is three Reels/week, but the workflow requires a successful one-Reel GPU qualification before a weekly batch. It automates editorial planning, multi-provider text generation and critique, Wan2.2 video scene generation through ComfyUI, Hindi TTS, branded post-production, local Hindi ASR, full-video black/freeze diagnostics, beat-stratified visual QA, scene checkpoint recovery and Telegram delivery. **Facebook publishing stays manual.**

## Architecture

- **Primary writer:** Gemini 3.8 Flash Free Tier.
- **Optional text failover / independent editor:** Groq `openai/gpt-oss-120b` Free, Mistral `ministral-8b-latest` in Studio Free mode, and Cloudflare Workers AI `@cf/meta/llama-3.1-8b-instruct` only with explicit Free-plan opt-in. Requests fail over sequentially; there is no paid route or parallel prompt fan-out.
- **Narration:** Gemini 3.8 Flash-Lite TTS remains the only qualified production Hindi voice. Local Whisper ASR checks transcript alignment; it is not a TTS fallback.
- **Video:** Wan2.2 TI2V-5B Q4_K_M GGUF on Kaggle free GPU through ComfyUI. Model output 704×1280 / 24fps; final render is upscaled to 1080×1920.
- **Post:** FFmpeg/Pillow, custom typography, subtitles, overlays, cover and locally synthesized ambience.
- **Delivery/learning:** private Telegram; `/approve` or `/reject` records the final owner decision; manual publishing; `/published` and `/insights` feed measured history.

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

No guarantee of artifact-free video, audience distribution, 10,000 views, monetization or Meta recommendation eligibility. Sampled-frame QA and technical motion checks supplement (but do not replace) one full human playback. If Kaggle exposes output after a failed run, verified scenes may be saved to a private Kaggle dataset and resumed; hard infrastructure loss may still prevent recovery. Gemini Free Tier prompts/responses may be used to improve Google products; only invented, public-safe stories belong in this workflow. Review the Wan2.2 upstream and quantization model license/NOTICE before commercial use.

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
- Weekly three-Reel planning now requires a successfully finalized Reel, passed technical QA, all four Telegram delivery steps, and an owner `/approve` record. The GPU runtime benchmark remains an additional independent gate.
- Telegram feedback drain and persistence steps are skipped unless `TELEGRAM_BOT_TOKEN` is configured.
- Empty/unset `KAGGLE_KERNEL_SLUG` values resolve to the safe default `bina-shor-ke-studio-video`.
- New plans are blocked while a resumable `gpu_checkpoint_saved` state exists.
- Added adversarial integration tests for generated worker manifest type, Telegram approval qualification, same-run feedback reload, missing-token workflow conditions, empty kernel slug, and checkpoint protection.

This release is offline-tested only. No live Kaggle GPU, external API, or Telegram production run was performed.
