# BINA SHOR KE — Final Deep Review v3.4

**Verdict: strong, safer prototype / controlled pilot; not yet a production-certified autonomous studio.** This release improves failure handling, memory integrity, measurement hygiene and annual maintenance. It does not claim unbeatable distribution, 10K views, or unlimited free capacity.

## 1. Design objective
The target is a durable, zero-paid-fallback Hindi storytelling factory: three original Reels per week, cinematic AI-generated vertical visuals, natural Hindi voice, premium edit, measurable learning, and explicit human publication approval. The guiding brand system remains: “कम शब्द। साफ़ कहानी। ऐसा अर्थ जो याद रहे।”

## 2. What the source audit found and what v3.4 changes

### A. Anti-repeat memory was incomplete
The concept generator referenced recent narrative devices and details, but the real GPU workflow did not consistently write all those fields back to long-lived history. v3.4 persists narrative engine, emotional aftertaste, human detail, contradiction and cost of choice when concepts are planned and when a Reel is delivered. This makes originality constraints durable rather than merely prompt-local. A deterministic near-duplicate check now also rejects repeated lived-in detail anchors in addition to title/theme similarity.

### B. Kaggle dispatch could become ambiguous
A client timeout can happen after a remote push is accepted. Automatically retrying may create duplicate GPU work; permanently locking the project is also poor UX. v3.4 keeps ambiguous pushes locked and adds two explicit owner-confirmation actions in the poll workflow. The owner must inspect Kaggle run/version history first. The system does not infer a result from an ambiguous network error.

### C. Polling used too much GitHub runner setup
A two-hour poll schedule can produce many no-op runs. v3.4 checks the saved pending state with standard Python before installing Python dependencies, FFmpeg/fonts, and Kaggle CLI. Expensive setup is skipped when there is no active/retry/resolution task. A minimal checkout/state-check still consumes some workflow runtime. GitHub's included Actions minutes depend on account/repository plan and usage; check repository billing and disable paid overage.

### D. Insight data could overfit to missing values
The previous parser could treat omitted engagement fields as zero. v3.4 records missing values as `null`, excludes sparse rows from the internal score, uses medians, and requires at least five observations per comparison group before adapting. The fixed weights/scales are still a heuristic and not Meta's recommendation algorithm. Keep one experiment slot to avoid overfitting.

### E. Provider quota exhaustion could cause repeated retries
Text routing now uses a per-run circuit breaker: quota responses cool down a provider; transient failures use a shorter cooldown; invalid model/key/config errors disable that provider for the current run. All fallbacks remain configured free providers only. TTS and image QA still rely on Gemini; text backups do not cover those modalities.

### F. State files could be left partially written
Creative history and Telegram update cursor use temporary files plus atomic replace. This reduces corrupt-state risk after an interrupted runner. First successful GPU qualification records key runtime package versions; future runs reject silent dependency drift until a deliberate requalification. GitHub workflow commits remain the persistence layer; keep the repository private and back up the data files.

### G. Maintenance was not sufficiently systematic
Added CI quality gates for Python syntax, tests and workflow YAML parse. Added monthly Dependabot pull requests for dependencies and Actions. Updates are review-only: no auto-merge and no automatic model upgrade. Every change to ComfyUI, model, runtime or dependencies must pass CI, offline preflight, one real Reel and human review before weekly batches resume.

## 3. Current architecture
- **Editorial/text:** Gemini 3.8 Flash by default; Groq GPT-OSS 120B and Mistral Ministral 8B as configured free backups/independent critic; Cloudflare Workers AI disabled unless explicitly enabled after Free-plan confirmation.
- **Speech:** Gemini 3.8 Flash-Lite TTS; TTS cache and spoken-delivery directions; WAV verification and audio loudness normalization.
- **Video:** Wan2.2 TI2V-5B Q4_K_M GGUF in ComfyUI on Kaggle GPU; 704×1280, 24fps, 81-frame shots; final 1080×1920 export.
- **Post:** local FFmpeg/Pillow typography, custom overlay, subtitle, sound bed, cover, publish kit.
- **QA:** duration/file-size/fps/stream checks; six evenly spaced frame samples to Gemini when available; hard rejection for obvious visual defects; manual full-video phone review remains mandatory.
- **Delivery:** private Telegram. Facebook upload is deliberately manual; no password, cookie or auto-post integration.
- **Learning:** owner-entered `/published` and 24-hour `/insights`; missing metrics remain unknown; median and minimum sample guard.

## 4. Free-service reality and cost controls
- **Gemini:** quota is per project/model/tier and changes with account; consult AI Studio's active limit page. Free usage is not unlimited.
- **Groq:** model/org rate limits include RPM, RPD, TPM and TPD; official limits page currently shows `openai/gpt-oss-120b` at 30 RPM and 1,000 RPD, but the live organization dashboard is authoritative.
- **Mistral:** Free mode is evaluation/prototyping with low limits; model enablement and limits must be checked on the account. No paid plan should be enabled.
- **Cloudflare:** 10,000 Neurons/day on Workers Free; Paid overage can incur cost. Leave disabled unless account plan is verified.
- **Kaggle:** current docs describe 12-hour notebook sessions, 20 GB `/kaggle/working` autosaved space, and limited/queued free GPU access. Weekly free allocation can vary. One-Reel runtime qualification and 8-hour 3-Reel estimate gate stay mandatory.
- **GitHub Actions:** no-op poll setup is reduced, but workflow runs still use included minutes. Keep paid overage disabled and monitor actual repository usage.

No provider should ever be configured with billing simply to solve throttling. When all free options fail, the factory stops and reports the failure.

## 5. Story quality: the real competitive moat
The moat is not a model name. It is a growing library of distinct human observations, restrained storytelling, natural spoken Hindi, and disciplined quality selection. Every story should have: a specific social/physical detail; a character who wants one thing but behaves another way; a small credible cost; an emotionally earned turn; and an ending that makes an earlier detail mean something new. Reject moral lectures, artificial tragedy, generic twist endings, copied viral templates, stock-footage narration and filler.

Use cinematic restraint: one motivated action per shot, natural practical light, physical camera movement only where useful, fewer cuts, readable negative space, sound that supports rather than manipulates, and character continuity. A story that cannot be understood without reading tiny subtitles or watching twice should be revised.

## 6. Visual model strategy
Wan2.2 remains the baseline because it is already wired and measured in the factory, not because it has been proven superior to every open model. It is an independent text-conditioned shot workflow; the visual bible cannot guarantee the same face/clothes/props through all six shots. Final upscaling does not create native 1080p detail. The full video must be reviewed for flicker, warping, continuity, temporal rhythm, and realism.

**Future controlled pilot:** HunyuanVideo-1.5 offers T2V/I2V and an official stated minimum of about 14 GB VRAM with offloading, but it is a larger 8.3B model with heavier dependency/model setup. Test separately against a fixed 10-prompt visual/motion benchmark; do not replace the base until measured runtime, output quality, licensing and disk budget beat the current Wan path.

## 7. Voice model strategy
Keep Gemini TTS as the production voice until a replacement passes a native-Hindi listening test. Indic-Speak from Bodhan AI/AI4Bharat is a promising 2026 self-hosted model with Hindi and code-mixed support, multiple contracted voices, and no hosted inference provider listed on its model card. But its own card describes style control as preview-quality, it is a 3.78B-parameter BF16 model and requires Transformers 5. Indic Parler-TTS is an older comparison candidate; its card points users to Indic-Speak. Neither should be silently added to the base. Conduct an A/B set of at least 20 scripts across Hindi names, numbers, Hinglish and emotionally restrained narration; judge pronunciation, breath/pacing, voice identity, artefacts, generation time and human preference.

## 8. What still prevents production certification
1. No live provider keys/quota checks or live API schemas verified in the owner's accounts.
2. No actual Kaggle GPU end-to-end render completed in this audit.
3. No full MP4 acoustic/visual human review can be automated here.
4. No robust cross-run remote checkpoint export exists for partially rendered Kaggle scenes; if a kernel fails before outputs are committed, some GPU work may be lost.
5. The one-Reel benchmark is a simple estimate from one run with a 1.5× safety factor, not a confidence interval; remeasure after Kaggle hardware, ComfyUI, model, or dependency changes.
6. Manual Facebook publishing and manual Insights capture remain required; there is no Meta API integration.
7. Editorial score scales/weights are heuristics and must be recalibrated only after a much larger data sample.

## 9. Annual operating standards
- Every week: three planned Reels maximum; reject weak output instead of posting for quota.
- Every month: review creator insights, provider usage, Kaggle GPU consumption, GitHub Actions minutes, Dependabot PRs, output file sizes and model/API deprecations.
- Every quarter: re-check Meta originality and AI-disclosure rules; verify all model/quantization licenses; audit secrets and repository collaborators; back up history and toolchain lock.
- Every model/runtime update: CI → preflight → one-Reel GPU qualification → phone review → weekly batch unlock.
- Maintain an evergreen 10-story backlog and a “do-not-repeat” ledger of story premise, human detail, character contradiction, narrative device and emotional aftertaste.
- Do not sacrifice originality or quality to maintain cadence. A missed post is better than an unpublishable Reel.

## 10. Validation performed in this build
- Python compileall: passed.
- Offline unit/orchestration tests: **49 passed**.
- GitHub Actions workflow YAML parse: passed.
- `producer.py --self-test`: passed.
- `studio_pipeline.py preflight`: passed (mock graph/shape; no API or GPU).
- Archive integrity: checked after packaging.

These prove offline code paths only, not production behavior.

## 11. Official sources checked on 30 October 2026
- Meta original creator guidance: https://about.fb.com/news/2026/03/rewarding-original-creators-on-facebook/
- Kaggle notebooks / GPU / session limits: https://www.kaggle.com/docs/notebooks
- GitHub Actions workflow timezone syntax: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- Gemini API rate limits: https://ai.google.dev/gemini-api/docs/rate-limits
- Groq rate limits: https://console.groq.com/docs/rate-limits
- Mistral Free-mode API limits: https://help.mistral.ai/en/articles/698531-why-am-i-hitting-api-rate-limits-and-how-do-i-increase-them
- Cloudflare Workers AI pricing: https://developers.cloudflare.com/workers-ai/platform/pricing/
- Indic-Speak model card/conditions: https://huggingface.co/bodhan-ai/indic-speak
- Indic Parler-TTS model card: https://huggingface.co/ai4bharat/indic-parler-tts
- HunyuanVideo-1.5 source: https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5
- Wan2.2 TI2V 5B Q4_K_M model: https://huggingface.co/timfromhcs/Wan2.2-TI2V-5B-GGUF
