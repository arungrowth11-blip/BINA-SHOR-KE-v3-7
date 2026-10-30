# BINA SHOR KE — Final Creative & Reliability Review v3.1

## The brand decision

**Keep BINA SHOR KE. Keep the niche broad in audience, focused in promise.** The page should not try to cover every subject under the sun. It should cover universally relatable human decisions and experiences—trust, boundaries, friendship, family, work, misunderstanding, digital life, small kindnesses and practical everyday behaviour—through the same short Hindi cinematic storytelling grammar.

Brand promise: **कम शब्द। साफ़ कहानी। ऐसा अर्थ जो याद रहे।**

This is a stronger long-term position than a page that alternates unrelated motivational quotes, AI portraits, fashion, comedy and news. Useful-life tips are allowed only when they feel like part of the same human-experience brand. Do not turn the page into a generic “everything viral” feed.

## Weekly mix (measured across a long horizon)

- 60% `micro_story` — one relatable choice, pressure or misunderstanding; a clear change in meaning.
- 25% `cinematic_moment` — an observed detail or reveal changes how the viewer interprets the scene.
- 15% `everyday_insight` — one useful behavioural/digital-life insight, shown rather than simply listed.

Three posts per week cannot hit 60/25/15 exactly every week; enforce the mix across the 20-item pillar cycle, then adjust only when actual Page data gives a defensible signal.

## A quality bar that matters more than volume

Every Reel should pass all of these before it enters the Telegram publish kit:

1. **Hook:** a concrete unanswered question, decision or visual contradiction begins immediately; no logo intro.
2. **Causal story:** each shot changes what we know, raises a consequence, or turns the interpretation. Remove any scene that is merely pretty filler.
3. **Earned payoff:** the ending resolves the setup or changes the viewer's understanding. It must not be a random proverb pasted at the end.
4. **Share reason:** the story gives a viewer a useful way to explain a feeling or situation to someone else. Never demand shares or manufacture controversy.
5. **Visual plan:** one physically plausible action per shot; restrained camera movement; practical light; consistent visual bible; no in-model text/logos; avoid difficult hands, fast crowds, rapid mouth movements and complicated interactions unless essential.
6. **Audio:** coherent Hindi pronunciation, pauses, moderate pace, speech clearly above original quiet sound bed; no copyrighted music needed.
7. **Typography:** correct Devanagari, short screen lines, safe margins, readable contrast, text added in post rather than generated into the scene.
8. **Technical quality:** real MP4 with valid audio/video streams, 9:16, 1080x1920 export, 24 fps output in AI mode, sensible duration and a Telegram-safe file size.
9. **Visual QA + person review:** sampled frames can catch many layout problems but cannot detect all flicker/morphing. Watch the entire Reel once on a phone before upload. If a shot is visibly broken, do not publish it.
10. **Originality and compliance:** original script and edit, no downloaded/reposted creator clips, disclose synthetic media when Meta's current flow requires it, and do not imply a fictional story is a verified real event.

## Photorealistic generation strategy

Wan2.2 TI2V-5B Q4_K_M is the no-paid-generation trial model. The pipeline renders six-ish short scenes per Reel at 704x1280 / 24 fps and upscales to 1080x1920. The original pixel detail remains 704x1280; the export size is not native 1080 detail. Use slow, simple, motivated action and anonymous/object-led compositions to reduce visible AI flaws. More render time cannot guarantee artifact-free faces, hands, physics or temporal consistency.

The system should prefer a smaller number of strong, coherent shots over fast, overcomplicated shots. If the model produces an obvious defect, reject the entire Reel and re-brief/re-generate fresh scenes rather than disguising it with filters. Do not try to evade required AI labels; realism and disclosure are separate issues.

## Editorial room and automation boundaries

The “director” and role-based review are structured prompts to the same AI model, not ten thousand independent human experts. They are useful repeatable checklists, not a guarantee of taste or truth. It automatically plans the week, writes/revises scripts, generates prompts, queues video, adds narration/subtitles/sound/cover, checks the file, writes caption/hashtags, sends the kit, records delivery and learns from owner-entered insights.

Human-controlled steps intentionally left in place:

- **One-time:** create private GitHub repo; set up Gemini Free Tier key, Kaggle API credentials and Telegram bot; confirm GitHub Actions paid overage is disabled.
- **After initial deployment:** run `preflight`, then `plan-one`; approve one real output before any `plan-week` run.
- **Every post:** watch the whole Reel, listen to Hindi, inspect subtitle and motion artifacts, then manually upload to Facebook and choose correct audience/disclosure.
- **After publishing:** send `/published`, then submit real 24-hour/7-day metrics with `/insights` when available.
- **Periodic maintenance:** check official model/Meta/quota guidance. A deliberately pinned stack is upgraded only by resetting `data/toolchain_lock.json`, running one qualification Reel, and approving it before weekly use.

## Zero-spend controls

- No paid video or audio APIs and no automatic switch to paid services.
- No Google Cloud billing link on the Gemini key; no paid Actions overage (set budget/spending to zero or turn overage off); no paid GPU provider.
- Kaggle's GPU availability, weekly quota and session limit are controlled by Kaggle and may prevent a run. The system should stop/alert rather than bill or deliver an incomplete batch.
- TTS narration is rate-paced and exact-text WAVs are cached across workflow retries where the GitHub cache is available, lowering repeated free-tier requests.
- Keep the GitHub repo private. Never send confidential police, case, personal or other sensitive data to Gemini Free Tier; only use fictional, public-safe content.

## Learning loop and performance honesty

Use same-window metrics, ideally 24h and 7d, and compare multiple Reels. A short Reel's average watch time must be interpreted alongside its runtime; completion, shares/saves, profile visits and follows per 1,000 views provide different signals. The planner's composite score is an internal prioritization heuristic, not an algorithm prediction. A weekly winner is a hypothesis until multiple posts repeat it. Keep an exploration slot and change one major variable at a time.

## What this system cannot promise

It cannot guarantee that a Reel will be shared, watched to the end, go viral, avoid all AI-looking artifacts, qualify for Meta recommendations/monetization, or run for a year with every free third-party service available. Wan2.2 is a serious open-weight option for free trials, not a contractual equivalence to Higgsfield. The honest standard is: only publish work that looks good on a phone, has a meaningful story, passes technical validation, and adds real creative value.
