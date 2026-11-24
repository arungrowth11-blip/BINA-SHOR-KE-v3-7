# BINA SHOR KE — v3.7 Primary 2.5D Reliability Factory

यह v3.6 पर आधारित v3.7 P0 Reliability build है। पुराने setup का backup रखें और इस release को अलग branch/copy में qualify करें। मुख्य लक्ष्य वही है: बिना paid fallback के हर सप्ताह 3 original, premium Hindi Reels बनाने की कोशिश; पहले live one-Reel qualification जरूरी है।

## वर्तमान architecture: voice-first, image-first 2.5D (v3.7 feature branch)

यह मौजूदा **Public GitHub repository** original Hindi story writing, voice-first timing, illustrated FLUX still generation, Depth Anything V2 depth maps, deterministic 2.5D parallax, branded post-production, fail-closed QA और private Telegram delivery को automate करती है। **Primary visual architecture 100% 2.5D parallax है; default path में Wan video generation नहीं है।** Wan2.2 केवल पुराने manifests की backward-compatible legacy route है। Facebook पर auto-publish नहीं होता।

> **साफ़ सीमा:** इस package को offline tests पर verify किया गया है; तुम्हारे Google/GitHub/Kaggle/Telegram accounts पर live API/GPU run अभी नहीं हुआ है। Free GPU availability, quotas और generated video quality की guarantee नहीं है। Workflow paid fallback नहीं लेगा; unavailable quota/hardware पर fail/alert करेगा।

## 1. Final niche: universal, लेकिन पहचान वाला

**BINA SHOR KE = रोजमर्रा के इंसानी फैसलों पर cinematic Hindi stories.** “सबके लिए सब कुछ” नहीं, बल्कि हर उम्र और gender के Hindi-speaking viewers के लिए एक common promise: कम शब्द, साफ़ कहानी, ऐसा payoff जो कहानी के बाद भी याद रहे.

- **60% — एक पल, एक फैसला:** भरोसा, जिम्मेदारी, दोस्ती, परिवार, work-life, गलतफहमी और self-respect पर original fictional micro-stories.
- **25% — जो दिखा, पूरा सच नहीं:** छोटी cinematic stories / reveal / perspective-shift; केवल सुंदर footage + vague quote नहीं.
- **15% — छोटी बात, बड़ा असर:** communication, attention, routine, digital habits और low-risk practical insights.

Men's style इस Page का मुख्य niche नहीं है; वह कभी-कभी useful insight के रूप में आ सकता है। यही breadth universal appeal देती है, जबकि repeated storytelling format brand को recognizable रखता है।

## 2. Production architecture — image-first 2.5D

1. **Primary Director (Gemini Free Tier):** title/theme history, pillar balance, posting slot, script, hook, beat-by-beat shot prompts, caption/hashtags और genuine share-reason बनाता है.
2. **Multi-provider writer fallback:** Gemini के transient outage/quota पर configured होने पर Groq, फिर Mistral Free, फिर केवल explicit opt-in पर Cloudflare Workers AI. किसी भी paid provider का endpoint या automatic billing fallback नहीं है.
3. **Independent Editorial Critic:** पहले Groq, फिर Mistral, फिर enabled Cloudflare, और अंत में Gemini. इसलिए Groq/Mistral key जोड़ने पर reviewer primary Gemini model से अलग provider family में critique करता है; बिना backup key के यह अलग model/provider की guarantee नहीं देता.
4. **Primary image-first visual worker (FLUX.1 Schnell Q4_K_S GGUF + ComfyUI on Kaggle GPU):** हर source beat के लिए एक 704×1280 illustrated PNG still बनती है। Wan video clip बनाकर keyframe निकालने की जरूरत नहीं.
5. **2.5D motion worker (Depth Anything V2 + OpenCV/FFmpeg):** हर still से depth map, eased camera push/drift और parallax MP4 बनता है। Default editorial coverage 100% depth-parallax है; 1080×1920, 30 FPS master तैयार होता है। पुरानी Wan 24 FPS route केवल legacy manifests के लिए है.
6. **QA:** editorial score + strict schema, voice/audio validation, MP4 dimensions/codecs/fps/duration/size checks, sampled VLM frame review, full-video black/freeze diagnostics, 1 FPS Tesseract OCR (Hindi + English) for leaked prompt labels, and local Hindi Whisper transcript QA. AI semantic evidence अधूरा हो तो manual-review fallback सिर्फ तभी मिलेगा जब deterministic local visual checks, technical QA, full-video motion scan और OCR सभी pass हों; इनमें से कोई objective gate fail हुआ तो delivery रुक जाएगी. हर Reel पर तीन independent लोगों का Pass/Fail review और owner का पूरा playback भी /approve से पहले जरूरी है.
7. **Telegram delivery:** MP4, cover, copy-ready caption, hashtags, suggested slot, visual prompts, credits और QA report. Facebook posting remains manual.

**Manual human review (कोई reviewer ID या extra secret नहीं):** यदि Reel AI EVIDENCE INCOMPLETE के साथ आती है, तो पहले पूरा वीडियो खुद देखें और तीन भरोसेमंद independent लोगों से अलग-अलग देखवाएं। उनसे सिर्फ Pass/Fail और कमी पूछें; नाम, Telegram ID या numeric ratings न लें। तीनों Pass हों और सभी कमियाँ ठीक हों तभी Telegram में /approve title=Exact Reel Title भेजें। एक भी Fail हो तो approve न करें—feedback लेकर Reel सुधारें और दोबारा review कराएं। /approve software में owner-attested manual review दर्ज करता है, bot-verified votes नहीं. Technical, motion या OCR failure को कोई human override नहीं कर सकता.
8. **Adaptive feedback:** अलग `Telegram Feedback Sync` workflow हर 6 घंटे में `/approve`, `/reject`, `/published` और `/insights` commands को private history में सुरक्षित करता है—GPU batch के बिना भी. `/insights` metrics पर्याप्त sample होने पर pillar mix और lunch/evening test slots को धीरे-धीरे adapt करते हैं. यह Meta Insights API integration नहीं है.

## 3. Zero-spend controls

- Primary text: `gemini-3.8-flash`; optional independent/recovery text providers: `openai/gpt-oss-120b` via Groq Free, `ministral-8b-latest` as the Mistral Studio Free-mode candidate (model access must be checked in the account), and Cloudflare `@cf/meta/llama-3.1-8b-instruct` only after explicit opt-in. Hindi voice: `gemini-3.8-flash-lite-tts`. These free quotas are limited and can change; fallback means a different free provider, not unlimited capacity. No automatic paid provider is configured.
- Primary visuals: FLUX.1 Schnell Q4_K_S GGUF + FLUX CLIP-L/T5 encoders + FLUX AE VAE, plus Depth Anything V2 Small on Kaggle CUDA. First successful complete image-first Reel stores immutable ComfyUI/GGUF/model/runtime revisions in `data/image_toolchain_lock.json`. The legacy Wan model/ComfyUI lock stays separate in `data/toolchain_lock.json`; do not copy or reuse the old Wan benchmark as proof for FLUX. Review upstream and quantization licenses/notices before commercial use. Current primary preflight requires at least 12 GiB VRAM and 18 GiB free disk; actual Kaggle model load/render still needs a live qualification run.
- Automation: repository Public ही रहेगा। Standard GitHub-hosted runners (जैसे ubuntu-latest) पर public repository के workflows free और unlimited हैं; private repository के monthly included compute minutes की जरूरत नहीं पड़ती। Larger runners paid हैं—इस project में उन्हें इस्तेमाल न करें.
- TTS calls are conservatively paced (about one request every 21 seconds). Each beat carries a restrained actor direction (pace, warmth, pause and emotional restraint) into Gemini speech metadata; cache keys include both exact narration and voice direction, so a changed performance is not accidentally reused. Validated WAV files are cached across GitHub workflow reruns. The cache is private workflow cache data, not committed to the repository.
- Telegram Bot API is the delivery route; WhatsApp Cloud API is deliberately excluded from the zero-cost baseline because account/setup/usage terms may change.
- No Pexels, stock-video subscription, paid image API, paid audio library, or paid video API is used by the strict production workflow.
- कोई billing key, API token, bot token, password या निजी पहचान repository, source files, prompts, issues या logs में न डालें। Source repository Public रहेगा; credentials केवल GitHub Actions Secrets में रखें.
- Gemini Free Tier prompts/responses may be used to improve Google products. Send only fictional, public-safe stories. Never paste real police information, case details, identifiable people, personal information or confidential material.
- “₹0 intended spend” is enforced by design only while account settings/free quotas remain as configured. No platform can promise free service or GPU availability forever.

## 4. One-time setup (Windows, no coding)

### A. Existing Public GitHub repository

1. मौजूदा repository arungrowth11-blip/BINA-SHOR-KE-v3-7 को **Public** ही रहने दें। नया duplicate या Private repository न बनाएं.
2. इस project में सामान्य ubuntu-latest GitHub-hosted runner ही इस्तेमाल होगा; paid Larger Runner या बाहरी paid runner अपने-आप enable नहीं होगा.
3. GitHub Actions → Secrets and variables → Actions में API credentials रखें। कोई token या private identifier source files में commit न करें.
### B. Free Gemini key (no billing)

1. Open https://aistudio.google.com/app/apikey, sign in and create an API key.
2. Use only the Gemini API **Free Tier**. Do **not** link Google Cloud Billing or enable a paid tier.
3. If the AI Studio page says Free Tier unavailable, do not upgrade to paid; pause this pipeline.
4. Free-tier inputs may be used to improve Google products. Use invented characters and invented everyday situations only—never police/case data.

### C. Telegram bot

1. In Telegram, open the verified `@BotFather` account and send `/newbot`.
2. Follow its steps and save the bot token privately.
3. Open the new bot and send **`/start` in a private chat**. It must be this exact bot, not BotFather.

### D. Kaggle free GPU API key

1. Sign in at https://www.kaggle.com/ and make sure the account can use GPU notebooks and Internet access.
2. Open Kaggle Settings/Profile → API → create/download a current API token. Keep its username and token/key private.
3. Kaggle's available accelerator/quota is account- and demand-dependent. The code does not attach paid GPU infrastructure; it stops if no CUDA GPU, insufficient VRAM or disk space is available.

### E. Add repository secrets

मौजूदा GitHub repository में: **Settings → Secrets and variables → Actions → New repository secret**. Add these four names exactly:

- `GEMINI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `KAGGLE_USERNAME`
- `KAGGLE_KEY`

No quotes around values. Do not add `PEXELS_API_KEY`, Meta password, Facebook cookies or any billing key.

**Optional free text-provider backups (recommended: Groq + Mistral):**

- `GROQ_API_KEY`: create a key at https://console.groq.com/keys. Keep the account on its free usage; the default independent critic prefers Groq, and text generation can fail over to it. Groq model/organization limits can change; check the exact figures in the account Limits page before launch. The app reads rate-limit errors and tries the next configured free provider; it does not assume a fixed quota.
- `MISTRAL_API_KEY`: create a key in https://console.mistral.ai/ while Studio is in **Free mode**. Mistral documents that API access in Free mode needs no credit card, but its low limits are meant for evaluation/prototyping; confirm that `ministral-8b-latest` is enabled for your account before depending on this fallback. Do not enable Pay-as-you-go or add payment details.
- Cloudflare is an optional third/fourth fallback and is **OFF by default**. Only set `CF_ACCOUNT_ID`, `CF_API_TOKEN`, and the exact secret `CF_WORKERS_AI_FREE_ONLY=YES` after verifying the account is on Workers Free. Free allocation is 10,000 Neurons/day; over that, Free-plan calls fail. Workers Paid overage is chargeable, so do not opt in when billing status is uncertain.
- `BSK_TEXT_PROVIDER` is set to `gemini` in workflow YAML. Do not change this unless you deliberately want a different configured primary. The optional provider secrets are not required for launch.

### F. Lock spending at zero

- Do not link a Cloud Billing account to the Gemini project.
- In GitHub Billing, turn off paid Actions overage / keep paid budget at $0. If free included minutes are exhausted, a run should be blocked rather than billed.
- Do not enable a paid GPU provider, paid model endpoint or other paid service.
- The workflow contains no auto-upgrade branch. Keep GitHub paid Actions overage disabled; scheduled no-op polls now run only a lightweight checkout/state precheck before skipping expensive setup.

## 5. Safe launch order

### Run 1 — offline preflight

GitHub → repository → **Actions** → `BINA SHOR KE — Director and AI Reel Dispatch` → **Run workflow** → `preflight` → Run.

- No Gemini API, no Kaggle GPU and no Telegram delivery are used.
- Tests validate code logic and the local FFmpeg/Devanagari render path.
- Any file named `SMOKE_TEST_ONLY_DO_NOT_PUBLISH.mp4` is a technical smoke test, not a real Reel.

### Run 2 — one real image-first 2.5D test Reel

Run the same workflow with `plan-one`. This uses Gemini Free Tier for script/voice, pushes one private Kaggle GPU job, generates FLUX stills, derives Depth Anything parallax and finalises a 30 FPS master. The ready-for-review package is sent to Telegram only after technical, visual, OCR and motion QA gates pass. This first image-first Reel must record its separate measured GPU benchmark. If quota/hardware/API is unavailable, it alerts and stops—never switches to Wan or paid generation as a silent fallback.

**Do not run the full batch until the test Reel arrives and you have reviewed the audio, motion and subtitles.**

### Run 3 — weekly batch

Select `plan-week` only after `plan-one` succeeds, all technical QA checks pass, all four Telegram delivery items (video, cover, review message, publish kit) arrive, and you send `/approve title=Exact Reel Title`. The workflow processes pending Telegram approval updates before checking the weekly gate. A separate image-first FLUX + depth benchmark (estimated 3-Reel batch <=8h) is mandatory; the old Wan 10.32h benchmark cannot qualify it. The scheduled planning run is Saturday at **07:37 IST**, leaving time to generate next week's planned Sunday/Tuesday/Thursday Reels. A separate poll workflow checks the free GPU job every two hours. GitHub schedules can be delayed; publication time is not guaranteed.

The standard planned slots begin with an alternating lunch/evening experiment: 13:07 IST and 20:37 IST. After at least five metric-bearing posts per window, the planner can favour the better internal score for two of three slots while retaining one exploration slot. This is a small-sample experiment, not a universal “best time”.

## 6. Your only routine work

1. Telegram receives a Reel MP4, cover, caption/hashtags, planned slot and QA report.
2. Watch the entire Reel once on your phone and listen once. Check natural Hindi pronunciation, pace, face/hand/object warping, flicker, changing clothes/props, fake text, bad lighting transitions, subtitle clipping, ending and hook.
3. If it looks obviously synthetic, broken or the story does not pay off, **do not publish**. Sampled-frame visual QA can miss transient motion artifacts; no model can guarantee human-indistinguishable results.
4. If acceptable, upload manually: Facebook Page → Create Reel → select MP4 → choose cover/caption → check public audience and any required AI disclosure → publish.
5. In Telegram send `/published title=Exact Reel Title; url=https://facebook.com/...` after it actually goes live.
6. About 24 hours after publishing, send the actual metrics using `/insights` (see template below). Use real Meta Insights, not estimates.

### Manual insights template

```text
/insights title=Exact Reel Title; pillar=micro_story; views=1200; reach=900; watch=8.2; completion=24; shares=11; saves=6; comments=3; visits=18; follows=5
```

Use actual numbers; `watch` is average watch time in seconds and `completion` is a percent. Available pillars: `micro_story`, `cinematic_moment`, `everyday_insight`. The next manual/scheduled planning run consumes the feedback. It does not automatically read Page Insights from Facebook.

### Telegram command sync

अलग `BINA SHOR KE — Telegram Feedback Sync` workflow हर 6 घंटे में commands sync करता है, भले कोई GPU job pending न हो। Telegram pending updates 24 घंटे से अधिक server पर नहीं रखता, इसलिए यह scheduled sync उपयोगी है; schedule delay या missed workflow की स्थिति में Actions में इस workflow को manually Run workflow करें। यह bot `getUpdates` उपयोग करता है, इसलिए उसी bot पर webhook active नहीं होना चाहिए। नए BotFather bot में webhook न बनाएँ।

### Commands

- `/start` — bind the bot to your private owner chat.
- `/approve title=Exact Reel Title` — approve the delivered Reel for manual publishing only.
- `/reject title=Exact Reel Title; reason=...` — reject it; no Facebook publishing occurs.
- `/published title=Exact Reel Title; url=...` — record that you uploaded it manually.
- `/insights ...` — save actual 24-hour performance.

## 7. Failure / recovery rules

- A current batch remains locked while running so a second weekly plan cannot accidentally duplicate it.
- The free GPU worker validates model nodes, required inputs, GPU, disk and complete scene output. It fails rather than using CPU or a paid model if the required path is missing.
- `poll` runs every two hours. If Telegram/TTS finalization fails transiently, run `retry-finalize`; already-sent Telegram items are checkpointed.
- Each finished FLUX PNG still and parallax MP4 is atomically inventoried with SHA-256, byte size and dimensions/duration. If Kaggle exposes partial output after a failed run, verified PNG stills can be saved to a private Kaggle dataset and hash-checked on restore; missing parallax clips can be regenerated from those stills. Legacy Wan MP4 checkpoint recovery remains backward-compatible. This is best-effort: hard infrastructure loss may expose no files to recover.
- An automatic resume is allowed only when a conservative remaining-time estimate is at most 4 hours. Otherwise, Telegram explains the manual `resume-checkpoint` action (maximum 8 hours, two total attempts). Ambiguous push outcomes are locked until owner confirmation to prevent duplicate GPU jobs.
- If the video fails a hard visual/rhythm QA gate, the status is `qa_rejected`. Do not publish that file and do not use `retry-finalize` (it would reuse the same scenes). After checking the alert, run `plan-one` for a fresh test or `plan-week` for a fresh batch; failed concepts remain in history to reduce repeats.
- If Kaggle quota/session ends or model/node APIs change, inspect the GPU log/manifest. No automatic paid fallback is attempted. If dispatch status becomes ambiguous, inspect Kaggle → Code → your private kernel → version/run history. Only after confirming the new run exists choose `resolve-dispatch-running`; only after confirming it did not start choose `resolve-dispatch-not-started`. Do not guess: these owner-confirmation options exist to avoid duplicate GPU jobs.
- Image-first FLUX source/model/runtime revisions are stored separately in `data/image_toolchain_lock.json`; the legacy Wan lock remains in `data/toolchain_lock.json`. Do not manually edit the lock to bypass a revision/benchmark mismatch. A deliberate requalification must be implemented as a reviewed source change and verified by a new `plan-one` run. Weekly production stays locked until the image-first one-Reel benchmark and owner approval are actually recorded.

## 8. License and model quality notes

- Primary visuals use FLUX.1 Schnell (Apache-2.0), the city96 Q4_K_S GGUF quantization, CLIP-L/T5 text encoders and Depth Anything V2 (Apache-2.0). The AE VAE is downloaded from the public `nick911/flux1-schnell-normal` mirror, which identifies it as an unmodified copy of the BFL Schnell VAE and publishes the original SHA-256; the worker enforces that digest after download. Review each exact model/quantization/encoder licence and NOTICE before commercial use: https://huggingface.co/city96/FLUX.1-schnell-gguf and https://huggingface.co/nick911/flux1-schnell-normal
- Wan2.2 TI2V 5B GGUF is a backward-compatible legacy route only. Review both upstream and derivative `LICENSE`/`NOTICE` before using an old manifest commercially: https://huggingface.co/timfromhcs/Wan2.2-TI2V-5B-GGUF
- Source stills are 704×1280; the final master is upscaled/assembled at 1080×1920, 30 FPS. Upscaling does not create native model detail.
- Model-generated scenes may still contain artifacts. The intended strategy is slow, motivated camera movement; one action per scene; anonymous/object-led shots where possible; custom Hindi subtitles in post; consistent visual bible; restrained colour grade and sound. Do not claim it is equal to Higgsfield or guaranteed not to look AI-generated.
- Meta's current originality guidance can deprioritize low-value/recycled/unoriginal content. Original scripts and custom edits help, but neither our score nor AI disclosure certifies recommendation or monetization eligibility.

## 9. File map

- `.github/workflows/weekly-factory.yml`: Saturday planning schedule + `preflight`, `plan-one`, `plan-week`.
- `.github/workflows/poll-gpu.yml`: 2-hour GPU status check + ASR/visual/motion QA + Telegram send + retry/checkpoint recovery + cross-run caches + toolchain lock persistence.
- `.github/workflows/quality-gates.yml`: Python compile, offline test suite and workflow YAML validation.
- `.github/dependabot.yml`: monthly dependency/action update PRs, manually reviewed.
- `scripts/producer.py`: topic history, multi-provider text routing, independent critique/revision, line-specific Hindi TTS direction, post-production, QA, Telegram commands and performance adaptation.
- `scripts/studio_pipeline.py`: secure plan/dispatch, Kaggle polling, delivery checkpointing and fail-safe state transitions.
- `scripts/kaggle_gpu_runner.py`: private Kaggle ComfyUI worker. Primary mode generates FLUX stills + Depth Anything V2 parallax; legacy mode retains Wan2.2 for older manifests. Both use atomic files and hash manifests.
- `scripts/model_lab.py` + `data/model_lab/`: offline candidate scorecards; no model downloads or live API calls.
- `tests/`: offline logic and orchestration checks.
- `data/history.json`: topic anti-repeat and measured performance state.
- `data/telegram_state.json`: Telegram owner binding और update cursor; feature branch इसे Fernet encryption के साथ save करती है। पुराने public Git commits में legacy plaintext binding अब भी हो सकती है; कोई पहचान/ID public न करें.
- `data/performance_log.csv`: manually shared performance metrics.

## 10. Annual operating cadence

- **Every Reel:** watch the entire MP4 once on a phone; check hook, natural Hindi pronunciation, subtitles, continuity, motion artifacts, ending, and whether the story feels earned. Reject a weak Reel rather than filling the weekly quota.
- **Every week:** publish no more than the planned 3 Reels; submit `/published` and accurate 24-hour `/insights` only after a real upload. Keep one slot as a deliberate exploration slot.
- **Every month:** review the quality-gates workflow and Dependabot PRs; compare the best and worst 5 Replays/retention records; check Gemini/Groq/Mistral account limits and Kaggle quota; inspect storage growth and stale pending states. Do not merge dependency/model updates without a successful `plan-one` qualification.
- **Every quarter:** re-check Meta originality/AI disclosure rules, every model and quantized derivative license, provider free-plan conditions, and the GitHub/Kaggle usage policy. Back up `data/history.json`, `data/performance_log.csv`, `data/telegram_state.json`, `data/toolchain_lock.json` and `data/image_toolchain_lock.json` privately.
- **After any model, ComfyUI node, workflow, or package update:** run CI → `preflight` → `plan-one` → full human review. Only then permit a weekly three-Reel batch.

## 11. Premium quality strategy and known boundaries

The current system is a controlled production pipeline, not a human film crew. The primary image-first path generates one FLUX still per story beat and turns each into a moving Depth Anything parallax clip; the current plan expands six source beats into 12–16 editorial cuts by retiming/cropping those source clips. It does **not yet generate 12–16 independent still images**. Character text descriptions and VLM continuity review reduce drift but are not equivalent to true image-conditioned reference-sheet locking. Final 1080×1920 export is an upscale from 704×1280 source stills/parallax, not native 1080p model detail. VLM samples up to 18 frames; OCR samples the timeline at 1 FPS; FFmpeg scans the full video for black/frozen intervals. These checks do not replace one complete human playback.

Keep the 3-Reel batch locked behind the one-Reel measured runtime and 8-hour estimate. Kaggle notebook sessions have a 12-hour maximum and a 20 GB auto-saved `/kaggle/working` area; GPU availability and weekly allocation can vary. A Kaggle failure does not establish that the model is impossible—it may be quota, queue, runtime, RAM/VRAM, network, or dependency drift. Do not retry blindly.

Text fallback providers reduce one provider's text rate-limit exposure but do not remove rate limits. TTS and image-based QA still use Gemini in this build; a text provider fallback cannot rescue those modalities. Indic-Speak (Bodhan AI/AI4Bharat) and Indic Parler-TTS are research candidates for a local Hindi TTS pilot, not production fallbacks yet: Indic-Speak's own card says style control is preview-quality and requires Transformers 5; compare pronunciation, speaker consistency, pacing, artifact rate and real listening before integration.

HunyuanVideo-1.5 is worth a future isolated comparison because its repository describes a lighter 8.3B video model and 14 GB minimum VRAM with offloading, but it is not a drop-in Wan replacement and has much heavier dependencies/model downloads than the current measured baseline. Test only in a separate branch/kernel, never as a surprise dependency.

## 12. Official/current references

- Meta original-content guidance: https://about.fb.com/news/2026/03/rewarding-original-creators-on-facebook/
- Gemini pricing: https://ai.google.dev/gemini-api/docs/pricing
- Gemini billing/free tier: https://ai.google.dev/gemini-api/docs/billing
- Gemini speech generation: https://ai.google.dev/gemini-api/docs/speech-generation
- Groq model catalogue and rate limits: https://console.groq.com/docs/models and https://console.groq.com/docs/rate-limits
- Mistral Studio Free mode: https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key
- Cloudflare Workers AI pricing and OpenAI-compatible API: https://developers.cloudflare.com/workers-ai/platform/pricing/ and https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/
- Kaggle free GPU usage: https://www.kaggle.com/docs/efficient-gpu-usage
- ComfyUI: https://github.com/Comfy-Org/ComfyUI
- ComfyUI GGUF node: https://github.com/city96/ComfyUI-GGUF
- FLUX.1 Schnell Q4_K_S GGUF: https://huggingface.co/city96/FLUX.1-schnell-gguf
- Public FLUX AE VAE byte mirror (SHA-256 verified in worker): https://huggingface.co/nick911/flux1-schnell-normal
- Wan2.2 TI2V 5B GGUF + NOTICE (legacy only): https://huggingface.co/timfromhcs/Wan2.2-TI2V-5B-GGUF
- GitHub Actions billing: https://docs.github.com/en/billing/concepts/product-billing/github-actions
- GitHub secrets: https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
- Telegram Bot API: https://core.telegram.org/bots/api

## 13. v3.4 multi-AI और emotional-depth safeguards (historical base)

- हर Reel के `quality_report.json` और `publish.txt` में **10K-ambition Director Readiness Index (0–100)** मिलेगा। यह hook, story progression, payoff, originality, creative contribution, share value, human specificity, emotional resonance, visual prompt, continuity, voice rhythm, readability और safety का editorial score है। यह 10,000 views की probability या prediction नहीं है।
- Kaggle worker अब हर scene का generation time और पूरे job का समय रिकॉर्ड करता है। `plan-one` की सफल run के बाद conservative 1.5x safety factor से 3-Reel batch का अनुमान बनेगा। `plan-week` तभी चलेगा जब benchmark मौजूद हो और अनुमान 8 घंटे से कम/बराबर हो। Kaggle की documented notebook session limit 12 घंटे है; यह estimate guarantee नहीं है।
- इसलिए **पहले `preflight`, फिर `plan-one`, फिर पूरा video phone पर जाँचो**। सफल benchmark, चारों Telegram delivery steps और `/approve` दर्ज होने के बाद ही `plan-week` चलाना। अगर अनुमान 8 घंटे से अधिक है, एक Reel प्रति run रखो। Free quota bypass करने के लिए parallel accounts/sessions न चलाओ।
- Static graphic engine अभी Pillow/FFmpeg से custom branded backgrounds, typography, overlays और covers बनाता है। यह FLUX जैसी photoreal image-generation model नहीं है। FLUX.1 schnell (Apache-2.0) को future optional image stage के रूप में qualify किया जा सकता है, लेकिन इससे model download, disk/RAM/VRAM और Kaggle runtime बढ़ेंगे। Base pipeline में इसे अभी अनिवार्य नहीं किया गया है।
- `FINAL_DEEP_REVIEW_v3.4.md` historical review है; current limitations और v3.5 recovery/AutoQA details `FINAL_DEEP_REVIEW_v3.5.md` में हैं।


### 14. v3.4 model-selection decisions (historical base)

- **Added:** Groq `openai/gpt-oss-120b` as the preferred independent critic and optional writer fallback; Mistral `ministral-8b-latest` as another independent fallback; Cloudflare Workers AI `@cf/meta/llama-3.1-8b-instruct` as opt-in fallback only. Groq and Mistral keys are optional; Cloudflare is deliberately disabled by default.
- **Kept:** Gemini for primary text and Hindi TTS, because its current speech-generation API supports Hindi and per-line style metadata. TTS continues to fail closed rather than switching to an unverified language/voice endpoint.
- **Historical v3.5 candidate note — superseded:** FLUX.1 schnell was previously only a candidate scorecard. Current v3.7 feature branch implements it as the primary image-first generator, pending live GPU/model benchmark and full Reel QA.
- **Not added:** Hugging Face Inference Providers as a free API fallback, because current Free users have no included monthly inference credits. Cerebras is not included because its current published pricing flow is not an unambiguous no-payment-method recurring free tier.
- **Not added to production as TTS alternatives:** Indic-Speak is a research-only candidate; style control is preview-quality and it needs a local GPU inference stage. Gemini remains the qualified voice for now.
- Story direction now rotates across twelve narrative devices; every concept must provide a lived-in detail, character contradiction, cost of choice and emotional aftertaste. The critic tests human specificity, earned emotional resonance, natural spoken Hindi and meaningful subtext, and rejects generic moral/quote endings, emotional manipulation and tragedy-as-shortcut.


- GitHub Actions workflow syntax/timezone: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- Indic-Speak model card and license conditions: https://huggingface.co/bodhan-ai/indic-speak
- Indic Parler TTS (legacy comparison candidate): https://huggingface.co/ai4bharat/indic-parler-tts
- HunyuanVideo-1.5 source and hardware notes: https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5


## 15. v3.5 recovery, AutoQA और candidate lab

- **Lightweight polling:** हर दो घंटे का scheduled run पहले केवल न्यूनतम Kaggle CLI से remote kernel status जाँचता है। Kernel अभी queued/running हो तो FFmpeg, Whisper, media dependencies और finalization caches install/restore नहीं होते; terminal/unknown state पर ही पूरा finalizer चलता है। इससे GitHub runner setup और Actions minutes घटते हैं।
- **Scene recovery:** Kaggle worker हर पूर्ण scene के बाद final MP4 atomically लिखता है और SHA-256 + duration + bytes की inventory बनाता है। Kaggle failure के बाद finalizer उपलब्ध output से valid scenes को private dataset में save करने और अगली run में restore करने की कोशिश करता है। Kaggle output उपलब्ध न होने पर recovery संभव नहीं—इसे durable cloud checkpoint की guarantee न समझें।
- **Resume budget:** एक automatic resume केवल conservative estimate <=4h होने पर; manual resume <=8h; अधिकतम दो attempts. Ambiguous kernel push में state lock रहता है और owner को Kaggle history verify करनी होती है।
- **Local audio QA:** `faster-whisper` large-v3-turbo CPU int8 dry voice track का Hindi transcript बनाता है और expected narration से CER compare करता है। यह word omission/mismatch flag करता है; accent, emotion या performance की quality certify नहीं करता।
- **Full-video technical QA:** FFmpeg पूरी video में black intervals और long freeze detect करता है. Visual AI QA beat के 2 frames तक sample करता है (अधिकतम 18); Gemini vision quota unavailable हो तो report manual review required रखती है. ये tests all-frame anatomy/flicker detection नहीं हैं।
- **Final owner review:** Telegram `/approve` और `/reject` status save करते हैं, लेकिन कोई social platform auto-publish नहीं होता। तुम्हें per-scene editing नहीं करनी; हर Reel को final publish से पहले एक बार पूरा देख/सुनकर approve या reject करना है। यही एक शेष नियमित creative review है; इसे समाप्त करना public brand quality के लिए सही नहीं होगा।
- **Model Lab:** HunyuanVideo-1.5, FLUX.1 schnell और Indic-Speak अलग candidate scorecards हैं. 10 paired samples, rights verification, human review, >=4.20/5 candidate score, baseline uplift >=0.25 और runtime budget जरूरी है; pass होने पर भी पहले 3 shadow runs चाहिए।
- **Hunyuan:** official docs 14 GB minimum GPU memory with offloading describe करते हैं; 480p T2V config 50 steps है, जबकि 8/12-step step-distilled track 480p I2V-only है. यह direct Wan replacement नहीं।
- **Indic-Speak:** Hindi production language listed है, लेकिन weights gated हैं और model card upstream components/terms review माँगता है; style control preview-quality है. अभी production TTS fallback नहीं।
- **FLUX.1 schnell:** image/cover/keyframe candidate, video generator नहीं. Hugging Face gate/license approval और current cover pipeline से paired test जरूरी।
- **Whisper:** local ASR model card MIT and 99-language; transcription is independent of Gemini TTS, but Gemini remains the only currently qualified Hindi TTS and vision QA provider.

### v3.5 model and CLI references

- Candidate benchmark guide: `docs/MODEL_LAB_BENCHMARK_HINDI.md`.
- Create candidate scorecards: `python scripts/model_lab.py template --candidate hunyuanvideo-1.5 --output output/model_lab/hunyuan.json` (candidate can also be `flux.1-schnell` or `indic-speak`).
- Score a completed paired benchmark: `python scripts/model_lab.py score --submission output/model_lab/hunyuan.json`.
- Kaggle private dataset default/CLI: https://github.com/Kaggle/kaggle-cli/blob/main/docs/datasets.md
- HunyuanVideo-1.5 official config: https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5
- Indic-Speak model card: https://huggingface.co/bodhan-ai/indic-speak
- Whisper large-v3-turbo model card: https://huggingface.co/openai/whisper-large-v3-turbo


## 16. v3.6 continuous Telegram feedback sync

- An independent scheduled workflow drains the pinned private owner chat every six hours even when no GPU batch is active.
- It persists approval/rejection decisions, manual publication records, actual performance observations, and the Telegram update cursor to the private repository.
- This avoids waiting until the next weekly plan to consume commands; Telegram retains pending updates for no longer than 24 hours. Scheduled workflow delays remain possible, so manual `Run workflow` is available for immediate sync.
- `getUpdates` and webhooks are mutually exclusive. Use a fresh BotFather bot without a webhook for this workflow.


## 17. Current launch baseline

v3.6 ऐतिहासिक release ने Telegram feedback ingestion gap ठीक किया था और 74 offline tests पास किए थे। वर्तमान release v3.7 है; इसके P0 changes और वर्तमान 83-test result नीचे Section 17 में दर्ज हैं. This does not replace the live account/GPU qualification steps in `START_HERE_HINDI.md`.


## 17. v3.7 P0 reliability fixes

1. Kaggle manifest अब single JSON encoding से inject होता है; generated worker startup पर `MANIFEST` का dict type जाँचता है।
2. `plan-week` के लिए केवल GPU benchmark पर्याप्त नहीं है। एक Reel की technical QA पास, Telegram पर video/cover/message/publish kit सफल delivery और owner का `/approve` अनिवार्य है।
3. Telegram sync workflow token न होने पर drain और state-commit दोनों steps छोड़ देता है।
4. `KAGGLE_KERNEL_SLUG` unset, empty या whitespace होने पर safe default लगाया जाता है।
5. `gpu_checkpoint_saved` रहते नया plan नहीं बनेगा; पहले `resume-checkpoint` या owner द्वारा स्पष्ट resolution जरूरी है।

नई integration tests generated Kaggle worker को non-empty manifest के साथ import करती हैं, weekly approval gate को simulate करती हैं और checkpoint overwrite को रोकने की पुष्टि करती हैं। Offline suite: 83 tests expected after release validation. Live Kaggle/API/Telegram run अभी नहीं हुआ है।
