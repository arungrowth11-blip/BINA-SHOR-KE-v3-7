# BINA SHOR KE v3.7 — P0 Reliability Review

## Scope

Only the five agreed P0 corrections were implemented. No TTS provider, video model, Kaggle model dataset, carousel, or broad runtime optimization was added in this release.

## P0 items

1. **Kaggle manifest:** `build_kaggle_kernel()` now inserts `json.loads(<single-encoded JSON string>)`. The generated worker rejects a non-dictionary manifest at import/startup. Integration test generates the actual worker file, compiles it, imports it, and verifies nested non-empty manifest values.
2. **Weekly qualification:** `plan-week` now requires `history.one_reel_qualification` with `qa_passed`, `telegram_delivered`, `owner_approved`, Reel ID and approval timestamp, plus the pre-existing qualified GPU benchmark and <=8-hour estimate. The qualification is written only when `/approve` is applied to a topic carrying QA and delivery flags. The plan command processes Telegram feedback and reloads persisted history before evaluating the gate.
3. **Telegram workflow:** both drain and persistence steps are conditional on a non-empty `TELEGRAM_BOT_TOKEN`.
4. **Kaggle slug:** unset, empty and whitespace-only values fall back to `bina-shor-ke-studio-video`.
5. **Recovery protection:** `gpu_checkpoint_saved` joins active pending states and blocks new plans from overwriting its resume metadata. The measured GPU benchmark now accepts five scene timings, matching the story validator's minimum of five beats.

## Test results

- `python -m unittest discover -s tests -v`: **84 tests passed**.
- `python -m compileall -q scripts tests`: passed.
- `python scripts/producer.py --self-test`: passed (offline, no API/network).
- `python scripts/studio_pipeline.py preflight`: passed (offline graph/render preflight, no API/network/GPU).
- All four GitHub Actions workflow YAML files parsed successfully.
- ZIP integrity: verified after packaging.

## Not tested live

- Kaggle API credentials, kernel push/status/output download.
- ComfyUI node schema compatibility and Wan2.2 model download/render.
- Gemini/Groq/Mistral API calls and TTS.
- Telegram sendVideo/sendPhoto/sendMessage/sendDocument and real `/approve` polling.
- Actual phone playback and manual owner approval.

## Go/no-go

Offline tests can establish these source-level protections, not live production readiness. The next allowed run is `preflight`, followed by one real `plan-one` pilot. Do not run `plan-week` until the delivered Reel has been watched and approved in Telegram, and the GPU benchmark qualifies.
