# BINA SHOR KE — Provider Fallback Integration Test Patch

यह patch मौजूदा v3.7.2 repository पर लागू होगा। यह production logic को नहीं बदलता; केवल अलग, manual workflow और regression tests जोड़ता है।

## केवल 3 project files जोड़ें

1. `tests/test_provider_fallback_integration.py` → repository के `tests/` folder में रखें।
2. `.github/workflows/provider-fallback-integration-test.yml` → repository के `.github/workflows/` folder में रखें।
3. `docs/PROVIDER_FALLBACK_INTEGRATION_TEST_HINDI.md` → repository के `docs/` folder में रखें।

**इन files को overwrite नहीं करना है।** ये नई files हैं। `scripts/producer.py`, existing workflows, `data/`, Telegram state, Kaggle files और GitHub Secrets में कोई बदलाव नहीं करना है।

## GitHub Desktop

1. Repository `BINA-SHOR-KE-v3-7` और branch `main` खोलें।
2. ऊपर दी गई तीनों files सही folders में copy करें।
3. GitHub Desktop में ठीक 3 नई files दिखनी चाहिए।
4. Commit summary:
   `Add simulated AI provider fallback integration test`
5. Commit करें और `Push origin` करें।

## Test चलाएँ

GitHub → Actions → `BINA SHOR KE — Provider Fallback Integration Test` → Run workflow.

सफल run में 5 tests `OK` होने चाहिए।

## सुरक्षा और सीमा

यह mocked/offline test है। इसमें कोई API secret इस्तेमाल नहीं होता, कोई network request नहीं जाती, कोई खर्च/GPU job नहीं होती और कोई Reel generate/publish नहीं होती। यह मौजूदा router के control-flow को verify करता है। Live API authentication अलग `AI Provider Smoke Test` से जाँची जाती है।
