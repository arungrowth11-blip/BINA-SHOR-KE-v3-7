# BINA SHOR KE — साल भर चलाने का Operations Playbook

## हर सप्ताह
1. शनिवार की Director workflow से पहले देखें कि कोई पुराना GPU batch pending नहीं है।
2. शुरुआत में `plan-one` ही चलाएँ। पहला live one-Reel benchmark और फोन पर पूरी समीक्षा पास होने के बाद ही `plan-week` की अनुमति दें।
3. Telegram में आया हर Reel पूरा देखें और सुनें। खराब motion, चेहरा/हाथ/सामान बदलना, टूटे subtitles, गलत उच्चारण, कमजोर hook/payoff या बनावटी भावुकता हो तो publish न करें।
4. Telegram में `/approve title=Exact Title` भेजें; खराब हो तो `/reject title=Exact Title`। Approved Reel को Facebook पर manually upload करें, फिर `/published` और करीब 24 घंटे बाद वास्तविक `/insights` भरें।

## हर महीने
- Scheduled poll पहले lightweight Kaggle status check करता है; GPU active होने पर full media/ASR dependencies install नहीं होतीं। Terminal status पर ही finalizer चलता है।
- GitHub → Actions → quality-gates में latest result देखें।
- Dependabot PR को merge करने से पहले tests और release notes पढ़ें। किसी model/runtime update के बाद पहले plan-one ही चलाएँ।
- Gemini, Groq, Mistral और Kaggle के वास्तविक account limits देखें। Quota खत्म हो तो रुकें; paid plan न चालू करें।
- `data/history.json`, `data/performance_log.csv`, `data/telegram_state.json` और `data/toolchain_lock.json` की private backup रखें।
- कम से कम 5 measured Reels वाले groups के बिना audience strategy न बदलें। एक experimentation slot हमेशा रखें।

## हर तीन महीने
- Meta की current original-content और AI disclosure policy देखें।
- Video, TTS, quantized model, ComfyUI nodes और font/source licenses दोबारा जाँचें।
- GitHub repository collaborators, Actions permissions, secrets और data backup की जाँच करें।
- अगर current Wan quality/runtime गिरा हो, अलग branch पर 10 fixed prompts के साथ HunyuanVideo-1.5 का controlled test करें। Base workflow को उसी दिन न बदलें।
- Indic-Speak/Indic Parler जैसे TTS विकल्पों को कम से कम 20 real Hindi scripts पर सुनकर compare करें; सिर्फ़ benchmark score के आधार पर voice न बदलें।

## Failure पर
- `dispatch_unknown`: Kaggle की private kernel run/version history जाँचें। Run मौजूद है तो poll workflow में `resolve-dispatch-running`; कोई नया run शुरू नहीं हुआ है तभी `resolve-dispatch-not-started`। अंदाज़ से न चुनें।
- `finalize_failed`: transient issue ठीक करके `retry-finalize` चलाएँ।
- `qa_rejected`: पुराना output publish न करें और retry-finalize न चलाएँ; नया `plan-one` बनाएँ।
- GPU/quota failure: duplicate push नहीं; logs देखें और free quota reset/availability का इंतज़ार/manual requalification करें। कोई paid fallback नहीं।

## v3.6 Telegram command reliability
- अलग lightweight workflow हर 6 घंटे में pinned owner के Telegram commands process करता है, चाहे GPU batch active हो या न हो. इससे `/published` और `/insights` को अगले weekly plan तक रोके रखने की v3.5 कमी दूर होती है.
- Telegram pending updates 24 घंटे से अधिक नहीं रखता; scheduled runs delay हो सकते हैं, इसलिए आवश्यक command के बाद manual sync भी उपलब्ध है.
- Bot पर webhook active न रखें; Telegram `getUpdates` और webhook साथ नहीं चल सकते.

## v3.5 AutoQA और scene recovery
- हर Reel पर local Whisper ASR narration को script से compare करता है; FFmpeg पूरी video में black/freeze intervals scan करता है; Gemini vision QA हर beat से दो frame sample करता है. इनके outputs advisory signals हैं, human approval का विकल्प नहीं.
- Kaggle worker per-scene atomic MP4 + SHA-256 manifest रखता है. Failure पर partial output अगर Kaggle से download हो सके तभी private dataset checkpoint बनता है. Hard infrastructure loss में recovery file न मिले तो नया render आवश्यक होगा.
- Automatic resume का conservative estimate <=4h, manual <=8h और कुल दो resume attempts तक सीमित है.

## Premium filter
**Quality > cadence. Original human insight > twist. Natural Hindi > heavy vocabulary. Consistent brand > random trends.** हर कहानी में अलग lived detail, अलग human contradiction और believable cost होना चाहिए। Ending में दर्शक को अर्थ खुद महसूस हो; कहानी भाषण न बने।
