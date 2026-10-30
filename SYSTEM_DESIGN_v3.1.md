# BINA SHOR KE — System Design v3.1

## Brand thesis

The brand is not “AI motivational videos”. It is **short, original Hindi cinema about everyday human choices**. The recurring promise is “कम शब्द। गहरी बातें।” Stories should provide one earned shift in perspective or one practical takeaway. The audience is broad across gender and life stage, but the topic selection remains within human decisions, work/family/friendship, trust, boundaries, digital life and daily habits.

## Weekly production line

1. **Schedule & state:** a Saturday 07:37 IST GitHub Actions run checks tests, reads history/metrics, selects three upcoming slots, drafts three non-duplicate briefs and pushes one private Kaggle GPU kernel with a per-Reel visual bible and beat prompts.
2. **Showrunner:** Gemini drafts a 5–6 beat mini-film with a one-second hook, a causal progression, a turning point and an earned ending. Each beat has voiceover, short on-screen Hindi text, unique overlay label, unique shot purpose and a 55–180-word concrete cinematic prompt.
3. **Role-based editorial review:** a second call scores 15 axes spanning hook, specificity, arc, payoff, readability, originality, creative contribution, visual match, photoreal prompt quality, motion feasibility, continuity, voiceover rhythm, caption, share value and safety. One targeted revision is permitted; weak ideas are rejected. This is a structured reviewer prompt to one model, not a literal multi-model committee.
4. **AI cinematography:** Wan2.2 TI2V-5B GGUF Q4_K_M runs as a text-to-video worker in ComfyUI on a free Kaggle GPU. Each beat is a separate 704×1280, 81-frame (~3.375s), 24fps scene. No paid video-generation API is called. The worker refuses CPU mode, checks VRAM/disk, validates ComfyUI's real node schemas and only declares success when every scene in the batch exists.
5. **Post-production:** GitHub FFmpeg renders the scene/voiceover timing, subtitles and creative overlays after generation (not rendered by the model), restrained colour grade, original low-level synthesized ambience, cover, credits and publish kit. Final output is 1080×1920, 24fps to preserve the model's native cadence.
6. **QA:** technical media validation (1080×1920, 24fps, audio/video streams, duration, size); six sampled rendered frames are sent to the free-tier vision model where available to check text legibility/clipping and composition; failures that look critical stop delivery. Vision QA is not full motion forensics and can miss morphing/flicker. A human must watch/listen once.
7. **Deliver:** Telegram gets MP4, cover, caption, hashtags, scheduled-slot hypothesis, storyboard prompts, credits and QA report. Per-message checkpoints prevent accidental duplicate sends. There is no Facebook password/cookie automation and no auto-publishing.
8. **Learn:** `/published` logs manual publish confirmation and optional post URL. `/insights` captures real owner-entered 24h data. A conservative internal score summarizes follows/1000 views, shares/1000, saves/1000, completion and watch time. After 2 measured posts per pillar, one out of every five pieces can be a pillar experiment. Posting-time adaptation is gated until 4 measured posts exist in both lunch and evening windows; thereafter it gives the better window two of three slots while preserving one exploration slot, with a baseline exploration week every fourth week.

## Fail-safe policy

- Never choose a paid model when a free-tier quota is exhausted.
- Never downgrade missing AI video to still images in strict production mode.
- Never post to Facebook automatically.
- Block a second plan if a batch is still active.
- Do not redeliver completed Telegram steps during transient finalization retry.
- Hard visual/rhythm rejection is marked `qa_rejected`; retry-finalize is blocked in the instructions because it would reuse the same bad frames. Start a fresh concept/batch instead.
- Missing GPU, low VRAM/disk, changed ComfyUI node schema, incomplete output manifest, missing clips, malformed audio, failed frame QA or invalid MP4 must alert/stop.

## Free-tier / longevity constraints

- Gemini Free Tier quotas and availability are account-specific and may change; no Google Cloud Billing should be linked. Google indicates Free Tier prompts/responses can be used to improve products, so scripts must not contain private/confidential information.
- Kaggle offers a limited and demand-dependent GPU quota (official guidance currently describes around 30 GPU hours/week; sessions can be time-limited). Queue, disk, Internet, model download, session limits and GPU type are operational dependencies, not guaranteed capacity.
- Wan2.2 upstream is Apache-2.0; the selected quantization is a derivative with its own `LICENSE`/`NOTICE`. Review both before monetized commercial use.
- The generated model scene is 704×1280, then upscaled. The result may look photorealistic but can also contain model artifacts. “Equal to Higgsfield”, “never looks AI-generated”, “viral” and “monetization eligible” are not promises the factory can make.
- Service endpoints, model names, ComfyUI nodes, free quotas and Meta disclosure rules can change. After the first successful GPU batch, exact ComfyUI/GGUF commits and Hugging Face model revisions are locked and reused; upgrades require a deliberate unlock plus one-Reel requalification. Runtime node-schema checks still fail closed if the locked stack is no longer compatible.
