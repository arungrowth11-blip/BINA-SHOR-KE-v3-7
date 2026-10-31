from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import producer  # noqa: E402


def _response(status_code: int = 200, body: dict | None = None, text: str = "") -> Mock:
    response = Mock()
    response.status_code = status_code
    response.text = text or ("OK" if status_code < 400 else "simulated provider error")
    response.headers = {}
    response.json.return_value = body or {}
    return response


def _chat_response(content: str) -> Mock:
    return _response(
        200,
        {"choices": [{"message": {"content": content}}]},
    )


def _gemini_503() -> requests.HTTPError:
    response = _response(503, text="simulated Gemini high demand")
    return requests.HTTPError("Gemini HTTP 503: simulated high demand", response=response)


class ProviderFallbackIntegrationTests(unittest.TestCase):
    """Exercise the production router with deterministic, mocked provider responses.

    No real API keys, network requests, story generation, TTS, Kaggle, or Telegram
    are used. The direct provider connectivity workflow is a separate live test.
    """

    def setUp(self) -> None:
        producer._PROVIDER_COOLDOWN_UNTIL.clear()
        producer._PROVIDER_DISABLED_THIS_RUN.clear()
        producer._LAST_TEXT_PROVIDER_USED = None
        self.env = patch.dict(os.environ, {"BSK_TEXT_PROVIDER": "gemini"}, clear=False)
        self.env.start()
        self.keys = patch.multiple(
            producer,
            GEMINI_API_KEY="test-gemini-key",
            GROQ_API_KEY="test-groq-key",
            MISTRAL_API_KEY="test-mistral-key",
            CF_WORKERS_AI_ENABLED=False,
            CF_ACCOUNT_ID="",
            CF_API_TOKEN="",
        )
        self.keys.start()
        self.sleep = patch.object(producer.time, "sleep")
        self.sleep.start()

    def tearDown(self) -> None:
        self.sleep.stop()
        self.keys.stop()
        self.env.stop()
        producer._PROVIDER_COOLDOWN_UNTIL.clear()
        producer._PROVIDER_DISABLED_THIS_RUN.clear()
        producer._LAST_TEXT_PROVIDER_USED = None

    def _gemini_repeated_failure(self, error: Exception) -> list[Exception]:
        # gemini_json performs three bounded attempts before returning to text_json.
        return [error, error, error]

    def test_gemini_503_routes_to_groq_and_does_not_call_mistral(self) -> None:
        groq_response = _chat_response('{"status":"ok","provider":"groq"}')
        with patch.object(
            producer, "_gemini_json_request", side_effect=self._gemini_repeated_failure(_gemini_503())
        ), patch.object(producer.requests, "post", return_value=groq_response) as http_post:
            result = producer.text_json("system", "integration test", temperature=0.0, timeout=3)

        self.assertEqual(result, {"status": "ok", "provider": "groq"})
        self.assertEqual(http_post.call_count, 1)
        self.assertEqual(http_post.call_args.args[0], "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(producer._LAST_TEXT_PROVIDER_USED, "groq")
        self.assertIn("gemini", producer._PROVIDER_COOLDOWN_UNTIL)

    def test_groq_malformed_json_routes_on_to_mistral(self) -> None:
        groq_bad_json = _chat_response("This is not JSON")
        mistral_ok = _chat_response('{"status":"ok","provider":"mistral"}')
        with patch.object(
            producer, "_gemini_json_request", side_effect=self._gemini_repeated_failure(_gemini_503())
        ), patch.object(producer.requests, "post", side_effect=[groq_bad_json, mistral_ok]) as http_post:
            result = producer.text_json("system", "integration test", temperature=0.0, timeout=3)

        self.assertEqual(result, {"status": "ok", "provider": "mistral"})
        urls = [call.args[0] for call in http_post.call_args_list]
        self.assertEqual(
            urls,
            [
                "https://api.groq.com/openai/v1/chat/completions",
                "https://api.mistral.ai/v1/chat/completions",
            ],
        )
        self.assertEqual(producer._LAST_TEXT_PROVIDER_USED, "mistral")

    def test_gemini_and_groq_timeouts_route_to_mistral(self) -> None:
        timeout = requests.Timeout("simulated upstream timeout")
        mistral_ok = _chat_response('{"status":"ok","provider":"mistral"}')
        with patch.object(
            producer, "_gemini_json_request", side_effect=self._gemini_repeated_failure(timeout)
        ), patch.object(producer.requests, "post", side_effect=[requests.Timeout("Groq timeout"), mistral_ok]) as http_post:
            result = producer.text_json("system", "integration test", temperature=0.0, timeout=3)

        self.assertEqual(result, {"status": "ok", "provider": "mistral"})
        urls = [call.args[0] for call in http_post.call_args_list]
        self.assertEqual(
            urls,
            [
                "https://api.groq.com/openai/v1/chat/completions",
                "https://api.mistral.ai/v1/chat/completions",
            ],
        )
        self.assertIn("gemini", producer._PROVIDER_COOLDOWN_UNTIL)
        self.assertIn("groq", producer._PROVIDER_COOLDOWN_UNTIL)

    def test_independent_editorial_review_uses_an_alternate_provider_then_mistral(self) -> None:
        # The draft writer was Gemini, so the reviewer must try Groq before Mistral.
        producer._LAST_TEXT_PROVIDER_USED = "gemini"
        with patch.object(producer, "groq_json", side_effect=RuntimeError("Groq HTTP 503: simulated outage")) as groq, \
             patch.object(producer, "mistral_json", return_value={"review": "mistral"}) as mistral, \
             patch.object(producer, "gemini_json") as gemini:
            result = producer.independent_review_json("reviewer system", "review this draft", timeout=3)

        self.assertEqual(result, {"review": "mistral"})
        groq.assert_called_once()
        mistral.assert_called_once()
        gemini.assert_not_called()

    def test_all_free_providers_fail_closed_without_cloudflare_or_paid_fallback(self) -> None:
        groq_503 = _response(503, text="simulated Groq 503")
        mistral_429 = _response(429, text="simulated Mistral rate limit")
        with patch.object(
            producer, "_gemini_json_request", side_effect=self._gemini_repeated_failure(_gemini_503())
        ), patch.object(producer.requests, "post", side_effect=[groq_503, mistral_429]) as http_post, patch.object(
            producer, "cloudflare_json", side_effect=AssertionError("Cloudflare must remain disabled")
        ) as cloudflare:
            with self.assertRaisesRegex(RuntimeError, "All configured free text providers failed; no paid fallback was attempted"):
                producer.text_json("system", "integration test", temperature=0.0, timeout=3)

        urls = [call.args[0] for call in http_post.call_args_list]
        self.assertEqual(
            urls,
            [
                "https://api.groq.com/openai/v1/chat/completions",
                "https://api.mistral.ai/v1/chat/completions",
            ],
        )
        cloudflare.assert_not_called()
        self.assertTrue({"gemini", "groq", "mistral"}.issubset(producer._PROVIDER_COOLDOWN_UNTIL))


if __name__ == "__main__":
    unittest.main(verbosity=2)
