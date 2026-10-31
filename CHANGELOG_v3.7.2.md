# BINA SHOR KE v3.7.2 — Bounded Director Structural Repair

## Why this patch exists

The first live `plan-one` run demonstrated that a text model can still return a structurally invalid draft after the v3.7.1 correction-feedback retry. The factory correctly stopped before delivery, but the Director had no final, narrowly scoped repair step for common formatting mistakes.

## Changes

- Unknown or unsupported `overlay_type` values are normalized to the neutral `keyword` style. Known aliases are mapped to their nearest supported style. This changes presentation metadata only; it does not rewrite story content.
- Narration lines outside the 7–12 whitespace-separated word range receive one targeted repair request containing only the affected lines and minimal story context. Only those lines may be replaced.
- The returned narration repair is checked locally. Missing, duplicate, unexpected, or still-invalid replacements are rejected; the factory fails closed rather than truncating spoken Hindi or silently accepting an overlong line.
- The same repair helper is used after the editorial revision path.
- Prompt and validator are aligned to exactly six beats and 45–72 total spoken Hindi words, with 48–60 as the target.
- Added regression tests for enum normalization, targeted narration repair, invalid repair rejection, and the six-beat requirement.

## Safety and cost boundary

- No paid provider or paid fallback was added.
- The narration repair request uses the existing configured free text-provider router and runs only when a line fails the structural word-count check.
- Overlay normalization is local and does not make an API request.
- Invalid repair output still stops the run. No malformed Reel is delivered to Kaggle or Telegram.
- This is an offline-tested code correction, not live certification of Gemini, Groq, Mistral, Kaggle GPU, Telegram or video quality.

## Verification

- Python tests: 91 passed (plus 5 subtests)
- Python compilation: passed
- GitHub workflow YAML: 4/4 parsed
