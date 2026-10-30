# BINA SHOR KE — v3.7: सबसे पहले यह करें

यह latest corrected release है। v3.5 या उससे पुराने ZIP की बजाय v3.7 इस्तेमाल करें।

# BINA SHOR KE v3.7 — सबसे पहले यह करें

## 1. ZIP को GitHub पर डालें

1. ZIP extract करें।
2. GitHub पर `bina-shor-ke-studio` नाम की **Private** repository बनाएं।
3. GitHub Desktop से repository clone करें और extracted folder की सभी files, hidden `.github` folder सहित, उसमें copy करें।
4. Commit और Push करें।

पूरी Windows walkthrough `README_HINDI.md` में है।

## 2. पहले केवल ये 4 GitHub Secrets डालें

Repository → Settings → Secrets and variables → Actions → New repository secret:

- `GEMINI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `KAGGLE_USERNAME`
- `KAGGLE_KEY`

Gemini को Free Tier पर रखें; Google Cloud Billing link न करें।

## 3. अतिरिक्त free AI keys (recommended, पर launch के लिए optional)

- `GROQ_API_KEY` — Groq Free. यह independent critic को अलग provider देता है और Gemini text quota fail होने पर fallback करता है।
- `MISTRAL_API_KEY` — Mistral Studio **Free mode**. `ministral-8b-latest` model का access अपने account में जाँचें; Free mode की limits कम हैं। Pay-as-you-go/billing enable न करें।
- Cloudflare अभी **बंद रखें**। इसे तभी चालू करें जब account को Workers Free verify कर लें; तब `CF_ACCOUNT_ID`, `CF_API_TOKEN` और `CF_WORKERS_AI_FREE_ONLY=YES` secrets जोड़ें। Workers Paid account पर opt-in न करें।

## 4. सही launch order

1. GitHub Actions → `BINA SHOR KE — Director and AI Reel Dispatch` → Run workflow → `preflight`.
2. Preflight पास हो तो उसी workflow में `plan-one` चलाएँ। यह पहला GPU qualification Reel है।
3. Telegram पर MP4 video, cover, review message और publish kit चारों आने की पुष्टि करें। पूरा video फोन पर देखें: हिंदी उच्चारण, कहानी, pacing, motion/flicker, character/prop continuity और subtitle readability जाँचें।
4. Reel सही हो तो `/approve title=Exact Reel Title` भेजें; समस्या हो तो `/reject title=Exact Reel Title` भेजें। `plan-week` केवल owner approval, QA, सभी Telegram delivery steps और qualified GPU benchmark के बाद ही चलेगा। अनुमानित runtime 8 घंटे से अधिक हो तो एक Reel प्रति run रखें।
5. Approved Reel को Facebook/Instagram पर manually publish करें; फिर `/published` और लगभग 24 घंटे बाद `/insights` दर्ज करें। `Telegram Feedback Sync` workflow हर 6 घंटे में commands save करेगा; जरूरत पर इसे manually भी Run workflow कर सकते हैं।

## 5. खर्च सुरक्षा

GitHub Actions billing में paid overage बंद रखें। Gemini को billing से link न करें। Groq/Mistral को Free mode/Free plan पर ही रखें। Cloudflare opt-in default से OFF है। किसी provider का free quota खत्म हो तो workflow fail होगा—paid provider पर switch नहीं करेगा।

**ध्यान दें:** 84 offline tests और workflow YAML validation पास हैं। आपकी API keys, Kaggle GPU, Telegram delivery और real video generation इस मशीन से live test नहीं किए गए हैं। 3 Reels/week लक्ष्य है, guarantee नहीं।


## अगर Kaggle dispatch status ambiguous हो
GitHub → Actions → `GPU Poll, Final Edit, QA and Telegram` → Run workflow. पहले Kaggle के private kernel की run/version history खोलकर जाँचें। नया run दिखे तो `resolve-dispatch-running` चुनें। नया run बिल्कुल नहीं दिखे तो ही `resolve-dispatch-not-started` चुनें। अनुमान से कोई विकल्प न चुनें।


## 6. Crash हुआ तो क्या होगा?

- Worker हर scene को complete/validate करके atomically MP4 लिखता है और SHA-256 checkpoint manifest बनाता है।
- Kaggle failure के बाद यदि Kaggle output files उपलब्ध कराता है, finalizer valid scenes को private Kaggle Dataset में save करके next run में hash-verify restore करने की कोशिश करेगा। यह best-effort recovery है; अचानक infrastructure loss में Kaggle output उपलब्ध न हो तो scenes recover नहीं हो पाएँगे।
- Estimated remaining render 4 घंटे के भीतर हो तो एक bounded automatic resume संभव है। अन्यथा Telegram alert आएगा; `GPU Poll, Final Edit, QA and Telegram` workflow में `resume-checkpoint` चुनें—केवल तब जब estimate 8 घंटे के भीतर हो। अधिकतम दो resume attempts हैं।
- Push response ambiguous हो तो कोई auto-resume नहीं: पहले Kaggle kernel history देखकर `resolve-dispatch-running` या `resolve-dispatch-not-started` चुनें।

## 7. Telegram command sync

`Telegram Feedback Sync` workflow हर 6 घंटे में `/approve`, `/reject`, `/published` और `/insights` commands पढ़कर private GitHub history तथा update cursor save करता है। First `plan-one` से पहले bot को private chat में `/start` भेजें; उसी run में owner chat pin होगा। Scheduled runs में delay हो सकता है, इसलिए command भेजने के बाद Actions → `BINA SHOR KE — Telegram Feedback Sync` → Run workflow से तत्काल sync भी कर सकते हैं। Bot पर webhook पहले से configured हो तो `getUpdates` काम नहीं करेगा; नए BotFather bot का उपयोग करें या पुराने webhook को हटाएँ।

## 8. नए models का controlled test

`docs/MODEL_LAB_BENCHMARK_HINDI.md` देखें। Model Lab isolated है—यह weekly run में Hunyuan/FLUX/Indic-Speak install या download नहीं करता। Scorecard commands:

```powershell
python scripts/model_lab.py template --candidate hunyuanvideo-1.5 --output output/model_lab/hunyuan.json
python scripts/model_lab.py template --candidate flux.1-schnell --output output/model_lab/flux.json
python scripts/model_lab.py template --candidate indic-speak --output output/model_lab/indic.json
```

पहले weights/terms और upstream licenses verify करें। Candidate को baseline से paired comparison किए बिना production में promote न करें।


## v3.7 का अनिवार्य weekly gate

`plan-week` GPU benchmark से अकेले unlock नहीं होगा। पहले `plan-one` पूरा हो, technical QA पास हो, Telegram पर video + cover + review message + publish kit चारों सफलतापूर्वक आएँ, और आप exact title के साथ `/approve title=Exact Reel Title` भेजें। Approval आने के बाद Telegram Feedback Sync workflow चलाएँ; चाहें तो `plan-week` स्वयं भी pending Telegram updates process करके gate जाँचता है।

अगर पिछला GPU job `gpu_checkpoint_saved` पर है, नया plan न चलाएँ। पहले workflow में `resume-checkpoint` चलाएँ या Kaggle स्थिति की जाँच करके स्पष्ट owner resolution करें।
