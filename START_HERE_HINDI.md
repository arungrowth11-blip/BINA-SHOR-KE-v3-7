# BINA SHOR KE — Current Operator Guide (Primary 2.5D)

> यह मौजूदा GitHub repository और feature branch के लिए है। नया ZIP, नई repository या manual code copy बनाने की जरूरत नहीं। Current PR #10 open/draft है; production में merge नहीं हुआ।

## 1. Current architecture

- **Primary:** FLUX.1 Schnell Q4_K_S से एक 704×1280 illustrated still प्रति source story beat।
- **Motion:** Depth Anything V2 + OpenCV/FFmpeg से वास्तविक 2.5D depth-parallax MP4।
- **Final edit:** 1080×1920, 30 FPS; primary editorial shots सभी depth-parallax से।
- **Legacy only:** Wan2.2 केवल पुराने pending manifests/recovery के लिए। नई primary job में Wan fallback नहीं।
- **Voice-first:** script/dialogue पहले, हर voice segment का वास्तविक WAV duration मापना, फिर final timed shot plan।
- **Human sign-off:** पूरा Reel सुनना/देखना, owner approval; कोई social platform auto-publish नहीं।

## 2. Required secrets

GitHub Actions secrets: GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, KAGGLE_USERNAME, KAGGLE_KEY. Optional text fallback secrets: GROQ_API_KEY and MISTRAL_API_KEY. FLUX AE VAE public mirror से आता है और fixed SHA-256 check होता है; Hugging Face token को requirement नहीं बनाया गया। Gemini/provider accounts को paid billing पर switch न करें; no paid fallback है।

## 3. Qualification sequence

1. Offline preflight and current-head CI must pass.
2. Run exactly one image-first `plan-one` after code/CI review. Do not run a weekly batch.
3. The worker must load pinned FLUX + CLIP-L/T5 + VAE + Depth Anything models on Kaggle, create all source PNG stills, make every depth-parallax MP4, persist manifest hashes and finish without errors.
4. Finalizer must verify PNG/MP4 hashes, render 30 FPS 9:16 master, and pass technical checks, complete VLM review, full-video black/freeze scan and Hindi+English OCR.
5. Telegram must confirm all four delivery items: video, cover, review message and publish kit.
6. Watch/listen to the full Reel. Only after explicit owner `/approve title=Exact Reel Title` is the one-Reel qualification recorded.
7. The image-first toolchain must save a complete immutable model/runtime lock and measured benchmark; only if the measured conservative 3-Reel estimate is <=8 hours can `plan-week` unlock.

The prior Wan benchmark (10.32h estimate) is not evidence for the FLUX image-first path.

## 4. Recovery / retry

- Image-first checkpoints save FLUX PNG stills with dimensions and SHA-256; private Kaggle restore verifies those hashes. Missing parallax MP4s can be regenerated from restored stills.
- Legacy Wan recovery accepts only the old video assets/lock. Never combine primary FLUX and legacy Wan assets in one job.
- Do not clear pending job state or fake benchmark/QA/Telegram flags. Ambiguous Kaggle dispatch must be resolved against the exact private kernel history before any retry.
- A technical rerun is not proof of a passed visual review. Failed/incomplete OCR/VLM/motion checks must stay blocked.

## 5. Known qualification gaps

- Live FLUX/Kaggle image-first Reel and measured runtime have not yet been verified.
- Six source story beats currently produce six FLUX stills; these are expanded into 12–16 editorial cuts using camera movement/crops. Independent still generation per each editorial shot is not yet implemented.
- Character descriptions and wardrobe are repeated in prompts and reviewed by VLM, but true image-conditioned multi-angle character-sheet locking is not yet implemented or qualified.
- 18–28 minutes per Reel is an unverified target.
- First six-Reel experiment and platform analytics are pending.
- Immutable container/dependency caching to remove the older cold-start bottleneck is still pending.

## 6. Publishing

The factory sends a private review package to Telegram. Publishing to Facebook, Instagram or YouTube remains a manual, owner-controlled action. Use accurate synthetic-content disclosures where the platform requires them. Never treat a successful render or Telegram delivery as publication confirmation.
