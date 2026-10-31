# BINA SHOR KE v3.7.1 — Director Recovery Patch

## Corrections based on the first live `plan-one` logs

- Gemini HTTP errors now retain the original `requests.Response`, allowing bounded retry logic to read the provider's `Retry-After` header. Backoff waits 8s/16s by default and respects a supplied retry delay up to a 90s cap.
- The story prompt now explicitly requires exactly six beats, 7–12 whitespace-separated Hindi words per spoken line (target 8–10), and 48–60 words overall. It instructs the model to count each line before returning JSON.
- If the first candidate fails a structural validation, the second candidate receives the specific validation message as correction feedback.
- If all configured free providers fail with HTTP 429/5xx, quota, timeout or connection errors, the run stops rather than making an unproductive second draft attempt. There is still no paid fallback.

## Safety boundary

This patch does not change Kaggle GPU dispatch, video generation, TTS, QA, Telegram delivery, or Facebook publishing. It does not guarantee Gemini availability or model compliance. Optional free text-provider backups (Groq/Mistral) remain opt-in; do not add billing or paid fallback.
