# BINA SHOR KE — Provider Fallback Integration Test

## इसका उद्देश्य

यह manual GitHub Actions workflow मौजूदा `scripts/producer.py` के वास्तविक provider router (`text_json`) को deterministic mocked responses के साथ जाँचता है। यह production code को modify नहीं करता।

## क्या जाँचा जाता है

1. Gemini HTTP 503 के बाद Groq को request जाती है और Groq सफल होने पर Mistral call नहीं होता।
2. Gemini विफल हो और Groq malformed JSON लौटाए, तो Mistral fallback लिया जाता है।
3. Gemini और Groq timeout पर Mistral fallback लिया जाता है।
4. तीनों free providers विफल हों तो workflow fail-closed रहता है; Cloudflare disabled रहता है और paid fallback नहीं होता।

## सुरक्षा सीमा

- कोई वास्तविक API key या GitHub Secret पढ़ा/उपयोग नहीं किया जाता।
- कोई बाहरी network/API request नहीं भेजी जाती; provider HTTP responses mock हैं।
- कोई story planning, TTS, visual QA, Kaggle GPU, Telegram या Facebook operation नहीं होता।
- यह test routing/control-flow प्रमाणित करता है, live provider availability नहीं। Live authentication के लिए अलग `AI Provider Smoke Test` workflow इस्तेमाल होता है।

## चलाने का तरीका

GitHub Repository → Actions → `BINA SHOR KE — Provider Fallback Integration Test` → Run workflow.

सफल परिणाम में चारों tests `OK` होंगे। यह workflow manual-only है; कोई code push, Reel generation या publishing स्वतः शुरू नहीं करता।
