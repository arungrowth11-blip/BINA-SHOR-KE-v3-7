# AI Provider Smoke Test — हिंदी निर्देश

यह छोटा manual GitHub Actions workflow Gemini, Groq और Mistral के वास्तविक text API credentials/model/response path की जाँच करता है। यह story planning, TTS, Telegram delivery या Kaggle GPU job शुरू नहीं करता।

## सुरक्षा और billing gate

Run करने से पहले Mistral Admin/Subscriptions में जाँचें कि Organization Free mode पर है और Pay-as-you-go / paid billing enabled नहीं है। यह workflow उस setting को बदलता नहीं है; confirmation checkbox केवल operator acknowledgement है। यदि Free mode या billing स्थिति स्पष्ट नहीं है, checkbox न चुनें और test न चलाएँ।

## GitHub में चलाने का तरीका

1. `Actions` खोलें।
2. `BINA SHOR KE — AI Provider Smoke Test` workflow चुनें।
3. `Run workflow` दबाएँ।
4. `confirm_free_mode` checkbox केवल Free mode और Pay-as-you-go OFF ہونے کی تصدیق کے بعد tick करें।
5. `Run workflow` करें।

## Expected result

Log में Gemini, Groq और Mistral के लिए अलग-अलग `PASS` दिखना चाहिए और अंत में `RESULT: 3/3 providers passed` आना चाहिए। कोई provider fail हो तो पूरा error देखें; API keys/values किसी screenshot या message में साझा न करें।

यह test प्रत्येक configured provider को एक छोटा JSON request भेजता है। Gemini अपने मौजूदा bounded retry logic के कारण transient 503/429 पर दोबारा प्रयास कर सकता है। Workflow कोई paid fallback enable नहीं करता।
