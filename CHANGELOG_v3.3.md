# Changelog — BINA SHOR KE v3.3 Free Multi-AI Story Factory

## AI provider resilience
- Kept Gemini 3.8 Flash as the default writer and Gemini 3.8 Flash-Lite TTS for Hindi narration.
- Added optional Groq `openai/gpt-oss-120b` chat-completions provider, using Groq's OpenAI-compatible API.
- Added optional Mistral Studio Free-mode `ministral-8b-latest` provider.
- Added Cloudflare Workers AI `@cf/meta/llama-3.1-8b-instruct` as a tertiary fallback behind explicit Free-plan opt-in. It is OFF by default.
- Added bounded sequential provider routing: Gemini → Groq → Mistral → Cloudflare for normal text generation; the critic avoids the writer provider where another configured provider exists. No parallel fan-out and no paid fallback.
- Added offline tests for API endpoint routing, authorization headers, provider cascade and Cloudflare opt-in fail-closed behavior.

## Story and voice direction
- Added 12 rotating narrative devices to reduce same-hook/same-twist/same-moral repetition.
- Required a lived-in human detail, character contradiction, cost of choice and emotional aftertaste for each concept.
- Expanded critic requirements and hard approval gates for `human_specificity` and `emotional_resonance`.
- More direct critique of unnatural Hindi, essay-like narration, forced sentiment, over-poetic lines, generic morality and tragedy-as-shortcut.
- Added per-beat vocal acting direction, passed separately into Gemini 3.8 TTS `speech_metadata`; WAV cache identity now includes narration + voice direction.
- Added story anchors and emotional aftertaste to topic history so future concepts can avoid repeating the same everyday detail.
- Expanded the 0–100 readiness index to include human specificity and emotional resonance. It remains non-predictive.

## Reliability and safety
- Cloudflare Workers AI uses `rejectIfBusy` to fail promptly under capacity pressure rather than queueing.
- Free provider limits are treated as account-specific and subject to change.
- Kept manual Facebook publishing and mandatory full-phone review.
- FLUX.1 schnell, other image generators and unverified Hindi TTS replacements were not added to the constrained Kaggle/GitHub base path.

## Validation
- `python -m py_compile scripts/producer.py tests/test_producer.py`: passed.
- `python -m unittest discover -s tests -q`: 44 tests passed.
- `studio_pipeline.py preflight`: passed with mocked ComfyUI metadata; no external API, GPU or account credentials used.
- Both workflow YAML files parsed; packaged ZIP integrity check passed.
- No live Gemini/Groq/Mistral/Cloudflare/Kaggle/Telegram execution was performed.
