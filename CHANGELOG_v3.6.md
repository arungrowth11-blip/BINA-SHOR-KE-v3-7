# BINA SHOR KE v3.6 — Release notes

## Critical integration correction
- Added `.github/workflows/telegram-feedback-sync.yml`, running every six hours and manually on demand.
- Added `scripts/telegram_feedback_sync.py` to drain the pinned private owner chat independently of GPU generation/finalization.
- Sync persists `data/telegram_state.json`, `data/history.json` and `data/performance_log.csv` to the private repository.
- Shared concurrency group prevents overlapping commits with planning and GPU finalization workflows.
- Skips safely before the Telegram token or owner enrollment exists.
- Added regression tests for missing token, unenrolled owner, successful cursor advancement and workflow configuration.

## Why this is required
In v3.5, Telegram commands were read during planning only. Telegram retains pending updates for no longer than 24 hours, so approvals, publication records and insights might not reach the factory before a later weekly plan. v3.6 fixes this with independent six-hour sync.

## Validation
- `python -m unittest discover -s tests -q`: 74 passed.
- `python -m compileall -q scripts tests`: passed.
- `python scripts/producer.py --self-test`: passed.
- `python scripts/studio_pipeline.py preflight`: passed.
- All workflow YAML files parsed successfully.
- No live Gemini/Kaggle/Telegram account or GPU render test was performed.
