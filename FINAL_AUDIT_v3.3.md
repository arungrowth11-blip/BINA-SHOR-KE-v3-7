# BINA SHOR KE — v3.3 Final Offline Audit

**Result:** offline code validation passed; production remains **not live-certified**.

## What changed

1. **Provider routing.** Gemini remains the default text writer and the only qualified Hindi TTS engine. Optional writer failover is sequential: Gemini → Groq → Mistral → Cloudflare (only when the Cloudflare free-only opt-in is set). Editorial critique prefers a provider different from the current writer where possible, then tries the configured free providers (Groq → Mistral → enabled Cloudflare → Gemini). If only one provider is configured, that provider is the unavoidable final fallback. The application does not parallel-broadcast prompts and does not contain a paid provider fallback.
2. **Provider choices.** Groq documents OpenAI-compatible Chat Completions and exposes a Free plan with model-specific limits; exact org limits must be checked in the account. Mistral Studio Free mode documents API access without a credit card but with low evaluation/prototyping limits; the selected Ministral model must be confirmed in the owner account. Cloudflare Workers AI documents OpenAI-compatible chat completions and a free allocation of 10,000 Neurons/day; Workers Paid overage is chargeable, so integration is OFF unless explicitly enabled.
3. **Story quality.** Twelve rotating narrative devices; mandatory human detail, character contradiction, cost of choice, emotional aftertaste; second-opinion reviewer with strict natural-Hindi and emotional-resonance dimensions; one targeted revision and fail-closed approval gate.
4. **Voice acting.** Per-beat directions feed Gemini 3.8 `speech_metadata`; cache keys include the exact transcript and delivery direction. Hindi support and the relevant speech metadata format are present in current Gemini TTS documentation.
5. **Scoring.** The 10K-ambition index now contains `human_specificity` and `emotional_resonance`; it remains an editorial index only, never a view probability.

## Validation evidence

- Python syntax compilation: passed.
- Both GitHub Actions workflow YAML files parsed successfully after quoting the Cloudflare model identifier.
- 44 offline unit/orchestration tests: passed.
- Provider tests: Groq Chat Completions route; Mistral Chat Completions route; Gemini→Groq fallback; Gemini/Groq failures→Mistral fallback; independent reviewer chooses Groq first and avoids the writer provider when alternatives exist; Cloudflare opt-in disabled by default and enabled-route endpoint/options mocked; workflow YAML parsed successfully.
- TTS tests: line-specific speech metadata, raw PCM wrapping/24kHz mono WAV validation, text+direction cache key.
- Offline studio preflight: passed; this uses mocked ComfyUI graph metadata and does not call a real API or GPU.

## Deliberately not integrated

- **FLUX.1 schnell / still-image generation:** open weights are available, but an additional model download/inference in the same Kaggle session increases disk, RAM/VRAM and runtime risk before the Wan2.2 one-Reel benchmark has passed. Keep it as a separately qualified future visual stage, not a fragile dependency of the base pipeline.
- **Hugging Face Inference Providers:** current documentation says Free users have no included monthly inference credits; usage requires purchased credits or a paid subscription. Not suitable for the zero-spend fallback.
- **Cerebras paid/promotional credit path:** the currently surfaced pricing page offers a promotional credit conditioned on a valid payment method and does not present a clean recurring no-payment-method free tier suitable for this project. Excluded.
- **Mistral/Groq/Cloudflare TTS:** no alternative Hindi voice route was added without live acoustic qualification; Gemini TTS currently documents Hindi support, style metadata and raw PCM output formats.

## Remaining risks / required human actions

- Offline mocks cannot prove provider account key validity, current account quota, free-plan status, model availability, network behavior, or remote response schemas.
- Cloudflare is not automatically bill-safe on a Workers Paid account. It must remain disabled unless the owner explicitly verifies Workers Free and deliberately sets the opt-in secret. Free allocation is 10,000 Neurons/day; if a Workers Free account exceeds the allocation, further operations fail.
- Keep Google AI Studio on Free Tier and do not link billing; Gemini free prompts/responses may be used to improve Google products. Keep Mistral in Free mode, and never add a payment method / enable Pay-as-you-go. Check Groq account plan/limits. Disable GitHub Actions paid overage.
- No live Kaggle GPU generation has been run here. The one-Reel benchmark gate still must be completed in the owner's account before `plan-week`. Kaggle hardware availability and quotas may vary.
- The full generated Reel must be watched on a phone for motion warping, flicker, character/prop continuity, voice pronunciation, subtitle legibility, pacing and story payoff. A handful of sampled frames cannot certify temporal quality.
- No guarantee of 10,000 views, viral reach, Meta recommendation, or monetization eligibility.

## Official provider references checked (2026-10-30)

- Groq Chat API/rate limits: https://console.groq.com/docs/api-reference and https://console.groq.com/docs/rate-limits
- Mistral Free mode and model API example: https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key
- Cloudflare Workers AI pricing and OpenAI-compatible endpoint: https://developers.cloudflare.com/workers-ai/platform/pricing/ and https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/
- Gemini pricing and TTS: https://ai.google.dev/gemini-api/docs/pricing and https://ai.google.dev/gemini-api/docs/speech-generation
- Hugging Face Inference Providers pricing: https://huggingface.co/docs/inference-providers/pricing
