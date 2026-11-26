from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import producer  # noqa: E402


class FactoryLogicTests(unittest.TestCase):
    def setUp(self):
        producer._PROVIDER_COOLDOWN_UNTIL.clear()
        producer._PROVIDER_DISABLED_THIS_RUN.clear()
        producer._LAST_TEXT_PROVIDER_USED = None

    def sample_concept(self):
        voice = [
            "पहले वह बिना सोचे सबकी मदद कर देता था।",
            "धीरे धीरे लोग इसे उसकी अपनी जिम्मेदारी समझने लगे।",
            "एक दिन उसके अपने जरूरी काम भी रुक गए।",
            "उसने पहली बार अपनी सीमा साफ शब्दों में बताई।",
            "कुछ लोग नाराज हुए, लेकिन कुछ ने उसकी बात समझी।",
            "अपनी सीमा तय करना हमेशा स्वार्थ नहीं होता।",
        ]
        overlays = ["अनुरोधों की शुरुआत", "बढ़ती अपेक्षाएँ", "छूटा हुआ काम", "नई सीमा", "दो अलग प्रतिक्रियाएँ", "सीख का निष्कर्ष"]
        queries = ["hands writing notebook desk", "phone notification desk", "unfinished notebook coffee", "hand turning phone down", "quiet empty office chair", "closed notebook warm lamp"]
        beats = []
        narrative_roles = ("hook", "context", "conflict", "escalation", "turn", "payoff")
        state_changes = (
            "A habitual request creates the opening pressure",
            "Repeated help becomes an assumed responsibility",
            "The protagonist loses time for a necessary personal task",
            "The protagonist states a boundary for the first time",
            "Two people react differently to the new boundary",
            "The final choice reframes what being dependable means",
        )
        causal_links = (
            "The opening establishes the pressure that needs explanation",
            "The earlier request is treated as a routine expectation",
            "That expectation now creates a visible personal cost",
            "The missed task forces a clear decision",
            "The boundary causes different reactions from friends",
            "Those reactions reveal the cost and meaning of the choice",
        )
        for i in range(6):
            beats.append({
                "narrative_role": narrative_roles[i],
                "state_change": state_changes[i],
                "causal_link": causal_links[i],
                "voiceover": voice[i],
                "screen_text": f"दृश्य {i+1} की बात",
                "visual_query": queries[i],
                "visual_direction": f"This shot adds narrative context number {i+1}.",
                "video_prompt": f"Semi-painterly Indian graphic-novel motion-comic frame {i+1}, layered foreground notebook, midground hand and background desk, tactile ink-and-gouache surfaces, warm tungsten practical light, slow cinematic camera drift, soft charcoal shadows and amber highlights, subtle paper grain, one physically plausible action, mature illustrated visual design, a consistent visual bible, stable wardrobe anchors, clean negative space, controlled perspective and a balanced mobile composition, no readable text, subtitles, logos or watermark.",
                "overlay_type": "note" if i != 3 else "contrast",
                "overlay_text": overlays[i],
            })
        return {
            "title": "सीमा तय करना",
            "story_type": "insight",
            "share_recipient": "अपने छोटे भाई को",
            "theme": "एक मददगार व्यक्ति को देर से पता चलता है कि दूसरों की अपेक्षाएँ उसकी जिम्मेदारी नहीं हैं।",
            "visual_bible": "Restrained naturalistic cinematic visuals, charcoal and warm amber practical light, anonymous everyday environments.",
            "share_reason": "The story gives a friend a simple way to think about boundaries without telling them what to do.",
            "narrative_engine": "A small choice has a quiet but visible cost",
            "emotional_aftertaste": "A little relief mixed with the sadness of a changed friendship",
            "human_detail": "A half-filled notebook left open beside a cooling cup of tea",
            "character_contradiction": "He wants to be dependable but resents being assumed available",
            "cost_of_choice": "One friend reacts coldly after he finally declines a request",
            "hook": "जब उसने पहली बार ना कहा",
            "beats": beats,
            "caption": "हर अनुरोध आपका कर्तव्य नहीं होता।",
            "hashtags": ["#BinaShorKe", "#HindiStories", "#SelfRespect"],
            "cover_text": "एक साफ सीमा",
        }

    def test_groq_openai_compatible_json_request(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"choices": [{"message": {"content": '{"ok": true}'}}]}
        with patch.object(producer, "GROQ_API_KEY", "test-key"), patch.object(producer.requests, "post", return_value=response) as mocked:
            result = producer.groq_json("system", "make json")
        self.assertTrue(result["ok"])
        self.assertEqual(mocked.call_args.args[0], "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(mocked.call_args.kwargs["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(mocked.call_args.kwargs["json"]["model"], producer.GROQ_TEXT_MODEL)
        payload = mocked.call_args.kwargs["json"]
        self.assertEqual(payload["max_completion_tokens"], 12000)
        self.assertEqual(payload["reasoning_effort"], "low")
        self.assertEqual(payload["include_reasoning"], False)
        self.assertNotIn("reasoning_format", payload)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["include_reasoning"], False)
        self.assertNotIn("reasoning_format", payload)

    def test_mistral_free_mode_uses_chat_completions_endpoint(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"choices": [{"message": {"content": '{"ok": true}'}}]}
        with patch.object(producer, "MISTRAL_API_KEY", "test-mistral-key"), patch.object(producer.requests, "post", return_value=response) as mocked:
            result = producer.mistral_json("system", "make json")
        self.assertTrue(result["ok"])
        self.assertEqual(mocked.call_args.args[0], "https://api.mistral.ai/v1/chat/completions")
        self.assertEqual(mocked.call_args.kwargs["headers"]["Authorization"], "Bearer test-mistral-key")
        payload = mocked.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "ministral-8b-latest")
        self.assertEqual(payload["max_tokens"], 8000)
        self.assertEqual(payload["response_format"], {"type": "json_object"})

    def test_openai_json_completion_rejects_truncated_output(self):
        body = {
            "choices": [{
                "finish_reason": "length",
                "message": {"content": '{"title":"incomplete'},
            }]
        }
        with self.assertRaisesRegex(RuntimeError, "refusing to parse truncated JSON"):
            producer._openai_json_completion(body, "Groq", 5000)

    def test_openai_json_completion_accepts_mistral_text_content_blocks(self):
        body = {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": [{"type": "text", "text": '{"ok": true}'}]},
            }]
        }
        self.assertEqual(producer._openai_json_completion(body, "Mistral", 5000), {"ok": True})

    def test_invalid_provider_json_does_not_open_permanent_provider_circuit(self):
        error = json.JSONDecodeError("Unterminated string", '{"title":"broken', 9)
        producer._provider_failure_cooldown("groq", error)
        self.assertTrue(producer._provider_available("groq"))
        self.assertTrue(producer._provider_available("mistral"))

    def test_cloudflare_is_disabled_without_explicit_free_only_flag(self):
        with patch.object(producer, "CF_WORKERS_AI_ENABLED", False), patch.object(producer, "CF_ACCOUNT_ID", "account"), patch.object(producer, "CF_API_TOKEN", "token"), patch.object(producer.requests, "post") as mocked:
            with self.assertRaisesRegex(RuntimeError, "disabled"):
                producer.cloudflare_json("system", "prompt")
        mocked.assert_not_called()

    def test_cloudflare_opt_in_route_uses_workers_ai_openai_compat_endpoint(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"choices": [{"message": {"content": '{"ok": true}'}}]}
        with patch.object(producer, "CF_WORKERS_AI_ENABLED", True), patch.object(producer, "CF_ACCOUNT_ID", "account-id"), patch.object(producer, "CF_API_TOKEN", "cf-token"), patch.object(producer.requests, "post", return_value=response) as mocked:
            result = producer.cloudflare_json("system", "make json")
        self.assertTrue(result["ok"])
        self.assertEqual(mocked.call_args.args[0], "https://api.cloudflare.com/client/v4/accounts/account-id/ai/v1/chat/completions")
        payload = mocked.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "@cf/meta/llama-3.1-8b-instruct")
        self.assertTrue(payload["options"]["rejectIfBusy"])


    def test_gemini_retry_honours_retry_after_header(self):
        response = Mock()
        response.headers = {"Retry-After": "12"}
        error = producer.requests.HTTPError("Gemini HTTP 503: high demand", response=response)
        with patch.object(producer, "_gemini_json_request", side_effect=[error, {"ok": True}]), \
             patch.object(producer.time, "sleep") as sleep:
            result = producer.gemini_json("system", "prompt")
        self.assertTrue(result["ok"])
        sleep.assert_called_once_with(12)

    def test_gemini_text_request_uses_header_for_api_key(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]
        }
        with patch.object(producer, "GEMINI_API_KEY", "test-gemini-key"), patch.object(
            producer.requests, "post", return_value=response
        ) as mocked:
            result = producer._gemini_json_request("system", "prompt")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(mocked.call_args.kwargs["headers"]["x-goog-api-key"], "test-gemini-key")
        self.assertNotIn("params", mocked.call_args.kwargs)
        self.assertNotIn("test-gemini-key", mocked.call_args.args[0])

    def test_gemini_visual_qa_request_uses_header_for_api_key(self):
        response = Mock()
        response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": '{"scores": {}}'}]}}]
        }
        with tempfile.TemporaryDirectory() as folder:
            frame = Path(folder) / "frame.jpg"
            frame.write_bytes(b"frame-bytes")
            with patch.object(producer, "GEMINI_API_KEY", "test-gemini-key"), patch.object(
                producer.requests, "post", return_value=response
            ) as mocked:
                result = producer.gemini_json_with_images("system", "prompt", [frame])
        self.assertEqual(result, {"scores": {}})
        self.assertEqual(mocked.call_args.kwargs["headers"]["x-goog-api-key"], "test-gemini-key")
        self.assertNotIn("params", mocked.call_args.kwargs)
        self.assertNotIn("test-gemini-key", mocked.call_args.args[0])

    def test_gemini_visual_qa_retries_transient_503(self):
        busy = Mock()
        busy.status_code = 503
        busy.headers = {"Retry-After": "2"}
        error = producer.requests.HTTPError("Gemini HTTP 503: unavailable", response=busy)
        success = Mock()
        success.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": '{"scores": {"visual_quality": 4}}'}]}}]
        }
        with tempfile.TemporaryDirectory() as folder:
            frame = Path(folder) / "frame.jpg"
            frame.write_bytes(b"frame-bytes")
            with patch.object(producer, "GEMINI_API_KEY", "test-gemini-key"), \
                 patch.object(producer.requests, "post", side_effect=[error, success]) as mocked, \
                 patch.object(producer.time, "sleep") as sleep:
                result = producer.gemini_json_with_images("system", "prompt", [frame])
        self.assertEqual(result["scores"]["visual_quality"], 4)
        self.assertEqual(mocked.call_count, 2)
        sleep.assert_called_once_with(2)

    def test_local_visual_qa_passes_valid_portrait_and_flags_black_frames(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            valid = Path(folder) / "valid.jpg"
            black = Path(folder) / "black.jpg"
            Image.new("RGB", (540, 960), (80, 90, 100)).save(valid, quality=90)
            Image.new("RGB", (540, 960), (0, 0, 0)).save(black, quality=90)
            passed = producer.deterministic_local_visual_qa([valid, valid])
            failed = producer.deterministic_local_visual_qa([valid, black])
        self.assertEqual(passed["status"], "passed")
        self.assertEqual(passed["engine"], "bsk_local_frame_qa_v1")
        self.assertEqual(failed["status"], "warning")
        self.assertTrue(any(item["check"] == "near_black_frame" for item in failed["hard_failures"]))

    def test_gemini_outage_falls_back_to_local_human_review_without_fake_ai_pass(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            reel_dir = Path(folder)
            def fake_extract(command, timeout=60):
                output = Path(command[-1])
                output.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (540, 960), (65, 75, 90)).save(output, format="JPEG", quality=90)
            with patch.object(producer, "run_cmd", side_effect=fake_extract), \
                 patch.object(producer, "gemini_json_with_images", side_effect=RuntimeError("Gemini HTTP 503: unavailable")), \
                 patch.object(producer, "metadata_ocr_qa", return_value={"status": "passed", "forbidden_terms_detected": []}):
                result = producer.visual_qa(
                    reel_dir / "reel.mp4", reel_dir, 4.0,
                    segment_durations=[2.0, 2.0],
                )
        self.assertEqual(result["status"], "local_pass_human_review")
        self.assertEqual(result["review_mode"], "deterministic_local_fallback")
        self.assertEqual(result["visual_ai_review"]["status"], "not_completed")
        self.assertEqual(result["local_visual_diagnostics"]["status"], "passed")
        self.assertTrue(result["human_review_required"])
        result["full_video_motion_diagnostics"] = {"status": "passed", "full_video_scanned": True}
        producer.enforce_visual_qa(result)

    def test_second_draft_prompt_includes_previous_structural_feedback(self):
        concept = self.sample_concept()
        feedback = "Beat 1 narration has 18 words; use 7-12 words."
        with patch.object(producer, "text_json", return_value=concept) as mocked:
            result = producer.generate_concept(
                {"topics": [], "generated_count": 0, "performance": []},
                "micro_story", producer.datetime.now(producer.TZ), 0,
                correction_feedback=feedback,
            )
        self.assertEqual(len(result["beats"]), 6)
        self.assertIn("exactly 6 narrative beats", mocked.call_args.args[1])
        self.assertIn("narrative_role", mocked.call_args.args[1])
        self.assertIn("causal_link", mocked.call_args.args[1])
        prompt = mocked.call_args.args[1]
        self.assertIn(feedback, prompt)
        self.assertIn("the production pipeline derives the canonical age/gender-matched profile", prompt)
        self.assertIn("If you choose a young-adult woman, the pipeline assigns Leda", prompt)
        self.assertIn("if you choose an adult woman (30–54), it assigns Aoede", prompt)
        self.assertIn('"video_prompt":"55–80 concrete English words', prompt)
        schema_cast = prompt.split('"characters": [', 1)[1].split('"pillar":', 1)[0]
        self.assertNotIn('"voice_profile_id"', schema_cast)
        self.assertIn("OMIT voice_profile_id entirely", prompt)
        self.assertIn("Return a beats array containing EXACTLY SIX objects", prompt)
        self.assertIn("no prologue object, no epilogue object, no seventh beat, and no merged beats", prompt)

    def test_transient_provider_outage_stops_redundant_second_candidate(self):
        failure = RuntimeError(
            "All configured free text providers failed; no paid fallback was attempted. "
            "gemini: Gemini HTTP 503: This model is currently experiencing high demand"
        )
        with patch.object(producer, "generate_concept", side_effect=failure) as generate:
            with self.assertRaisesRegex(RuntimeError, "temporarily unavailable"):
                producer.acquire_approved_concept(
                    {"topics": [], "generated_count": 0, "performance": []},
                    "micro_story", producer.datetime.now(producer.TZ), 0,
                )
        generate.assert_called_once()

    def test_all_free_provider_cooldowns_stop_candidate_retries(self):
        cooldown_until = producer.time.monotonic() + 3600
        cooldowns = {
            "gemini": cooldown_until,
            "groq": cooldown_until,
            "mistral": cooldown_until,
        }

        def generate_without_available_provider(*args, **kwargs):
            return producer.text_json("system", "prompt")

        with patch.object(producer, "GEMINI_API_KEY", "gemini-key"), \
             patch.object(producer, "GROQ_API_KEY", "groq-key"), \
             patch.object(producer, "MISTRAL_API_KEY", "mistral-key"), \
             patch.object(producer, "CF_WORKERS_AI_ENABLED", False), \
             patch.dict(producer._PROVIDER_COOLDOWN_UNTIL, cooldowns), \
             patch.object(producer, "generate_concept", side_effect=generate_without_available_provider) as generate, \
             patch.object(producer.requests, "post") as request:
            with self.assertRaisesRegex(RuntimeError, "temporarily unavailable"):
                producer.acquire_approved_concept(
                    {"topics": [], "generated_count": 0, "performance": []},
                    "micro_story", producer.datetime.now(producer.TZ), 0,
                )
        generate.assert_called_once()
        request.assert_not_called()

    def test_text_router_falls_back_from_gemini_to_groq(self):
        with patch.object(producer, "GEMINI_API_KEY", "gemini-key"), patch.object(producer, "GROQ_API_KEY", "groq-key"), patch.object(producer, "CF_WORKERS_AI_ENABLED", False), patch.object(producer, "gemini_json", side_effect=RuntimeError("429 quota")), patch.object(producer, "groq_json", return_value={"writer": "groq"}) as groq:
            result = producer.text_json("system", "prompt")
        self.assertEqual(result["writer"], "groq")
        groq.assert_called_once()

    def test_text_router_falls_back_to_mistral_after_groq_failure(self):
        with patch.object(producer, "GEMINI_API_KEY", "gemini-key"), patch.object(producer, "GROQ_API_KEY", "groq-key"), patch.object(producer, "MISTRAL_API_KEY", "mistral-key"), patch.object(producer, "CF_WORKERS_AI_ENABLED", False), patch.object(producer, "gemini_json", side_effect=RuntimeError("429 quota")), patch.object(producer, "groq_json", side_effect=RuntimeError("429 rate limit")), patch.object(producer, "mistral_json", return_value={"writer": "mistral"}) as mistral:
            result = producer.text_json("system", "prompt")
        self.assertEqual(result["writer"], "mistral")
        mistral.assert_called_once()

    def test_independent_review_prefers_groq_before_gemini(self):
        with patch.object(producer, "GEMINI_API_KEY", "gemini-key"), patch.object(producer, "GROQ_API_KEY", "groq-key"), patch.object(producer, "CF_WORKERS_AI_ENABLED", False), patch.object(producer, "groq_json", return_value={"critic": "groq"}) as groq, patch.object(producer, "gemini_json") as gemini:
            result = producer.independent_review_json("system", "prompt")
        self.assertEqual(result["critic"], "groq")
        groq.assert_called_once()
        gemini.assert_not_called()

    def test_independent_review_avoids_the_provider_that_wrote_the_draft(self):
        with patch.object(producer, "_LAST_TEXT_PROVIDER_USED", "groq"), patch.object(producer, "GROQ_API_KEY", "groq-key"), patch.object(producer, "MISTRAL_API_KEY", "mistral-key"), patch.object(producer, "GEMINI_API_KEY", "gemini-key"), patch.object(producer, "CF_WORKERS_AI_ENABLED", False), patch.object(producer, "mistral_json", return_value={"critic": "mistral"}) as mistral, patch.object(producer, "groq_json") as groq:
            result = producer.independent_review_json("system", "prompt")
        self.assertEqual(result["critic"], "mistral")
        mistral.assert_called_once()
        groq.assert_not_called()

    def test_concept_validation_passes_sample_with_distinct_overlays(self):
        concept = self.sample_concept()
        producer.validate_concept_shape(concept)

    def test_structural_repair_normalizes_unknown_overlay_without_extra_ai_call(self):
        concept = self.sample_concept()
        concept["beats"][0]["overlay_type"] = "headline_overlay"
        with patch.object(producer, "text_json") as mocked:
            repaired = producer.repair_concept_structure(concept)
        self.assertEqual(repaired["beats"][0]["overlay_type"], "keyword")
        mocked.assert_not_called()

    def test_structural_repair_shortens_only_invalid_narration_lines(self):
        concept = self.sample_concept()
        concept["beats"][1]["voiceover"] = "आज सुबह उसने अपने पुराने दोस्त को बिना बताए बहुत देर तक स्टेशन के बाहर अकेले इंतजार करते देखा था।"
        replacement = "आज उसने दोस्त को स्टेशन पर चुपचाप इंतजार करते देखा।"
        with patch.object(producer, "text_json", return_value={"replacements": [{"beat": 2, "voiceover": replacement}]}) as mocked:
            repaired = producer.repair_concept_structure(concept)
        self.assertEqual(repaired["beats"][1]["voiceover"], replacement)
        self.assertEqual(repaired["beats"][0]["voiceover"], self.sample_concept()["beats"][0]["voiceover"])
        self.assertTrue(7 <= len(replacement.split()) <= 18)
        mocked.assert_called_once()

    def test_structural_repair_rejects_a_still_overlong_ai_rewrite(self):
        concept = self.sample_concept()
        concept["beats"][1]["voiceover"] = "आज सुबह उसने अपने पुराने दोस्त को बिना बताए बहुत देर तक स्टेशन के बाहर अकेले इंतजार करते देखा था।"
        too_long = "आज सुबह उसने अपने पुराने दोस्त को स्टेशन के बाहर बहुत देर तक अकेले इंतजार करते हुए देखा था।"
        with patch.object(producer, "text_json", return_value={"replacements": [{"beat": 2, "voiceover": too_long}]}):
            with self.assertRaisesRegex(ValueError, "left Beat 2 at"):
                producer.repair_concept_structure(concept)

    def test_share_recipient_gate_rejects_missing_or_generic_recipient(self):
        missing = self.sample_concept()
        missing.pop("share_recipient", None)
        with self.assertRaisesRegex(ValueError, "share_recipient"):
            producer.validate_concept_shape(missing)
        generic = self.sample_concept()
        generic["share_recipient"] = "everyone"
        with self.assertRaisesRegex(ValueError, "too generic"):
            producer.validate_concept_shape(generic)
        audience = self.sample_concept()
        audience["share_recipient"] = "Hindi audience"
        with self.assertRaisesRegex(ValueError, "too generic"):
            producer.validate_concept_shape(audience)

    def test_structural_repair_completes_near_threshold_video_prompt_without_extra_ai_call(self):
        concept = self.sample_concept()
        original = concept["beats"][2]["video_prompt"]
        concept["beats"][2]["video_prompt"] = " ".join(original.split()[:53])
        self.assertEqual(len(concept["beats"][2]["video_prompt"].split()), 53)
        with patch.object(producer, "text_json") as mocked:
            repaired = producer.repair_concept_structure(concept)
        prompt = repaired["beats"][2]["video_prompt"]
        self.assertGreaterEqual(len(prompt.split()), 55)
        self.assertLessEqual(len(prompt.split()), 180)
        self.assertIn("layered foreground", prompt)
        mocked.assert_not_called()
        producer.validate_concept_shape(repaired)

    def test_structural_repair_replaces_generic_recipient_without_an_ai_call(self):
        concept = self.sample_concept()
        concept["share_recipient"] = "Hindi audience"
        concept["theme"] += " यह बात उसके छोटे भाई के काम आएगी।"
        with patch.object(producer, "text_json") as mocked:
            repaired = producer.repair_concept_structure(concept)
        self.assertEqual(repaired["share_recipient"], "अपने भाई को")
        mocked.assert_not_called()
        producer.validate_concept_shape(repaired)

    def test_structural_repair_infers_story_specific_recipient_from_mother_context(self):
        concept = self.sample_concept()
        concept["share_recipient"] = "everyone"
        concept["share_reason"] = "A daughter wants her mother to understand the small sacrifice."
        with patch.object(producer, "text_json") as mocked:
            repaired = producer.repair_concept_structure(concept)
        self.assertEqual(repaired["share_recipient"], "अपनी माँ को")
        mocked.assert_not_called()
        producer.validate_concept_shape(repaired)

    def test_structural_repair_uses_singular_relationship_fallback_without_provider(self):
        concept = self.sample_concept()
        concept["share_recipient"] = "Hindi audience"
        concept["share_reason"] = "A small everyday observation that has no explicit family relationship."
        with patch.object(producer, "text_json") as mocked:
            repaired = producer.repair_concept_structure(concept)
        self.assertEqual(repaired["share_recipient"], "उस दोस्त को")
        mocked.assert_not_called()
        producer.validate_concept_shape(repaired)

    def test_concept_validation_requires_exactly_six_beats(self):
        concept = self.sample_concept()
        concept["beats"] = concept["beats"][:5]
        with self.assertRaisesRegex(ValueError, "exactly 6 narrative beats"):
            producer.validate_concept_shape(concept)

    def test_repeated_lived_in_detail_is_rejected(self):
        history = [{"human_detail": "A half-filled notebook left open beside a cooling cup of tea"}]
        self.assertTrue(producer.human_detail_is_too_similar("A half filled notebook left open beside a cooling cup of tea", history))
        self.assertFalse(producer.human_detail_is_too_similar("A bus conductor folds the same torn ticket twice", history))

    def test_concept_validation_rejects_repeated_overlay(self):
        concept = self.sample_concept()
        for beat in concept["beats"]:
            beat["overlay_text"] = "एक ही बात"
        with self.assertRaises(ValueError):
            producer.validate_concept_shape(concept)

    def test_duplicate_topic_detection(self):
        history = [{"title": "एक सीमा की कीमत", "theme": "एक व्यक्ति हमेशा मदद करता है और लोग इसे अपना हक समझ लेते हैं"}]
        self.assertTrue(producer.topic_is_too_similar("एक सीमा की कीमत", "एक अलग शुरुआत", history))
        self.assertFalse(producer.topic_is_too_similar("बारिश में एक पुरानी आदत", "चाय और खिड़की के पास अकेलापन", history))

    def test_caption_discloses_fiction_only_for_story_pillars(self):
        story = {"pillar": "micro_story", "caption": "एक छोटी कहानी।", "hashtags": ["#BinaShorKe"]}
        lifestyle = {"pillar": "useful_lifestyle", "caption": "कपड़ों का सही fit चुनें।", "hashtags": ["#BinaShorKe"]}
        self.assertIn("कहानी काल्पनिक है।", producer.safe_caption(story))
        self.assertNotIn("कहानी काल्पनिक है।", producer.safe_caption(lifestyle))

    def test_telegram_state_save_is_atomic_encrypted_and_round_trips(self):
        old_path = producer.TELEGRAM_STATE_PATH
        with tempfile.TemporaryDirectory() as folder, patch.object(producer, "TELEGRAM_BOT_TOKEN", "test-telegram-bot-token"):
            producer.TELEGRAM_STATE_PATH = Path(folder) / 'telegram_state.json'
            try:
                producer.save_telegram_state({'owner_chat_id': '123', 'last_update_id': 55})
                raw = producer.TELEGRAM_STATE_PATH.read_text(encoding="utf-8")
                stored = json.loads(raw)
                self.assertNotIn("owner_chat_id", stored)
                self.assertIn("owner_chat_id_encrypted", stored)
                self.assertNotIn('"123"', raw)
                loaded = producer.load_telegram_state()
                self.assertEqual(loaded['owner_chat_id'], '123')
                self.assertEqual(loaded['last_update_id'], 55)
                self.assertFalse(producer.TELEGRAM_STATE_PATH.with_suffix('.json.tmp').exists())
            finally:
                producer.TELEGRAM_STATE_PATH = old_path

    def test_legacy_plaintext_telegram_owner_state_migrates_without_cursor_loss(self):
        old_path = producer.TELEGRAM_STATE_PATH
        with tempfile.TemporaryDirectory() as folder, patch.object(producer, "TELEGRAM_BOT_TOKEN", "test-telegram-bot-token"):
            producer.TELEGRAM_STATE_PATH = Path(folder) / "telegram_state.json"
            try:
                producer.TELEGRAM_STATE_PATH.write_text(
                    json.dumps({"owner_chat_id": "legacy-owner-id", "last_update_id": 674097690}),
                    encoding="utf-8",
                )
                state = producer.load_telegram_state()
                self.assertEqual(state["owner_chat_id"], "legacy-owner-id")
                self.assertEqual(state["last_update_id"], 674097690)
                producer.save_telegram_state(state)
                persisted = json.loads(producer.TELEGRAM_STATE_PATH.read_text(encoding="utf-8"))
                self.assertNotIn("owner_chat_id", persisted)
                self.assertNotIn("legacy-owner-id", json.dumps(persisted))
                self.assertEqual(persisted["last_update_id"], 674097690)
                reloaded = producer.load_telegram_state()
                self.assertEqual(reloaded["owner_chat_id"], "legacy-owner-id")
                self.assertEqual(reloaded["last_update_id"], 674097690)
                encrypted_snapshot = producer.TELEGRAM_STATE_PATH.read_bytes()
                producer.save_telegram_state(reloaded)
                self.assertEqual(producer.TELEGRAM_STATE_PATH.read_bytes(), encrypted_snapshot)
            finally:
                producer.TELEGRAM_STATE_PATH = old_path

    def test_wrong_telegram_bot_token_fails_closed_without_overwriting_state(self):
        old_path = producer.TELEGRAM_STATE_PATH
        with tempfile.TemporaryDirectory() as folder:
            producer.TELEGRAM_STATE_PATH = Path(folder) / "telegram_state.json"
            try:
                with patch.object(producer, "TELEGRAM_BOT_TOKEN", "original-bot-token"):
                    producer.save_telegram_state({"owner_chat_id": "owner-id", "last_update_id": 91})
                original_bytes = producer.TELEGRAM_STATE_PATH.read_bytes()
                with patch.object(producer, "TELEGRAM_BOT_TOKEN", "rotated-bot-token"):
                    with self.assertRaisesRegex(RuntimeError, "could not be decrypted"):
                        producer.load_telegram_state()
                self.assertEqual(producer.TELEGRAM_STATE_PATH.read_bytes(), original_bytes)
            finally:
                producer.TELEGRAM_STATE_PATH = old_path

    def test_manual_insights_parser(self):
        history = {"topics": [], "performance": []}
        result = producer._parse_insights_message(
            "/insights title=पहली कहानी; pillar=micro_story; views=1200; reach=900; watch=8.2; completion=24%; shares=11; saves=6; comments=3; visits=18; follows=5",
            history,
        )
        self.assertEqual(result["views_24h"], 1200)
        self.assertEqual(result["pillar"], "micro_story")
        self.assertAlmostEqual(result["new_follows_per_1000_views"], 4.167, places=2)

    def test_manual_insights_records_planned_post_window(self):
        history = {
            "topics": [{"title": "पहली कहानी", "pillar": "micro_story", "planned_publish_at": "2026-10-27T20:37:00+05:30"}],
            "performance": [],
        }
        record = producer._parse_insights_message(
            "/insights title=पहली कहानी; pillar=micro_story; views=500; watch=7.1; completion=20",
            history,
        )
        self.assertEqual(record["post_window"], "evening")
        self.assertEqual(record["planned_post_hour"], 20)
        self.assertIsNone(record["shares"])
        self.assertIsNone(record["new_follows"])
        self.assertIsNone(record["new_follows_per_1000_views"])

    def test_time_adaptation_needs_five_posts_per_window_and_keeps_exploration(self):
        history = {"performance": []}
        for i in range(5):
            history["performance"].append({"post_window": "evening", "views_24h": 1000, "new_follows": 5, "shares": 15, "completion_rate_percent": 45, "average_watch_time_seconds": 10})
            history["performance"].append({"post_window": "midday", "views_24h": 1000, "new_follows": 1, "shares": 1, "completion_rate_percent": 10, "average_watch_time_seconds": 3})
        # rotation=1 activates adaptation; one of the three slots remains an exploration slot.
        slots = producer.next_post_slots(3, rotation=1, history=history)
        self.assertEqual(len(slots), 3)
        self.assertEqual([slot.strftime("%H:%M") for slot in slots], ["20:37", "13:07", "20:37"])

    def test_sparse_insights_do_not_train_factory_as_zero_performance(self):
        row = {"views_24h": 500, "new_follows": None, "shares": None, "saves": None,
               "completion_rate_percent": 22, "average_watch_time_seconds": None}
        self.assertIsNone(producer._metric_score(row))
        full_row = {"views_24h": 500, "new_follows": None, "shares": 5, "saves": 3,
                    "completion_rate_percent": 22, "average_watch_time_seconds": 6}
        self.assertIsNotNone(producer._metric_score(full_row))

    def test_performance_context_uses_median_and_minimum_sample(self):
        rows = []
        for score in (10, 20, 30, 40, 100):
            rows.append({"pillar": "micro_story", "views_24h": 1000, "shares": score,
                         "saves": 5, "completion_rate_percent": 30, "average_watch_time_seconds": 8})
        context = producer.performance_context({"performance": rows})
        self.assertEqual(context["minimum_sample_for_pillar_adaptation"], 5)
        self.assertEqual(context["by_pillar"]["micro_story"]["posts_with_metrics"], 5)
        self.assertEqual(context["by_pillar"]["micro_story"]["median_internal_score"],
                         context["by_pillar"]["micro_story"]["mean_internal_score"])

    def test_manual_insights_reject_zero_views(self):
        with self.assertRaises(ValueError):
            producer._parse_insights_message("/insights title=Test; pillar=micro_story; views=0", {"topics": []})

    def test_performance_context_returns_scores_and_counts(self):
        history = {"performance": [
            {"pillar": "micro_story", "views_24h": 1000, "new_follows": 5, "shares": 10, "saves": 4, "completion_rate_percent": 30, "average_watch_time_seconds": 8},
            {"pillar": "micro_story", "views_24h": 800, "new_follows": 4, "shares": 9, "saves": 3, "completion_rate_percent": 35, "average_watch_time_seconds": 7},
        ]}
        context = producer.performance_context(history)
        self.assertEqual(context["posts_with_metrics"], 2)
        self.assertEqual(context["by_pillar"]["micro_story"]["posts_with_metrics"], 2)
        self.assertGreater(context["by_pillar"]["micro_story"]["mean_internal_score"], 0)

    def test_ass_includes_story_overlay_and_scene_counter(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.ass"
            producer.write_ass(path, "यह एक कहानी है", 3.2, overlay_text="नया संदर्भ", overlay_type="contrast", scene_index=2, scene_count=6)
            content = path.read_text(encoding="utf-8")
            self.assertIn("BINA SHOR KE", content)
            self.assertIn("नया संदर्भ", content)
            self.assertNotIn("CONTRAST", content)
            self.assertNotIn("  |  ", content)
            self.assertIn("02 / 06", content)


    def test_final_storyboard_is_generated_from_locked_speaker_audio_timeline(self):
        prompt = "A vertical cinematic animated shot with two friends in a modest Indian kitchen. " + " ".join(
            ["Show the correct speaker's natural mouth movement, the listener's reaction, expressive eyes, a measured camera move, realistic cloth, warm practical window light and consistent character appearance."] * 4
        )
        concept = {
            "title": "दो दोस्तों की बात",
            "visual_bible": "Consistent two-person character design, warm muted cinematic lighting.",
            "characters": [
                {"character_id": "story_12345678_arjun", "display_name": "अर्जुन", "appearance": "Young man in blue shirt.", "personality": "Impatient", "voice_profile_id": "hi_male_young_puck", "voice_direction": "Young masculine Hindi."},
                {"character_id": "story_12345678_meera", "display_name": "मीरा", "appearance": "Older woman in green shawl.", "personality": "Patient", "voice_profile_id": "hi_female_older_gacrux", "voice_direction": "Mature feminine Hindi."},
            ],
            "voice_first_plan": {"status": "voice_measured_before_video"},
            "beats": [],
        }
        for i in range(6):
            sid = f"beat_{i+1:02d}_line_01"
            speaker_id = concept["characters"][i % 2]["character_id"]
            concept["beats"].append({
                "narrative_role": ("hook", "context", "conflict", "escalation", "turn", "payoff")[i],
                "state_change": f"A distinct story development number {i+1} changes the situation",
                "causal_link": f"The previous beat leads into story development number {i+1}",
                "visual_query": "two friends kitchen conversation",
                "visual_direction": "A small misunderstanding becomes clear through a quiet response.",
                "video_prompt": "Initial prompt, replaced after voice lock.",
                "speech_segments": [{
                    "segment_id": sid,
                    "speaker_id": speaker_id,
                    "text": "मैंने तुम्हारी बात सुनी थी।",
                    "duration_seconds": 4.6,
                }],
                "voice_timing": {
                    "timing_source": "measured_tts_wav_before_gpu",
                    "target_duration_seconds": 5.0,
                    "target_frames": 120,
                    "fps": 24,
                    "segments": [{
                        "segment_id": sid,
                        "speaker_id": speaker_id,
                        "start_seconds": 0.08,
                        "end_seconds": 4.68,
                    }],
                },
            })
        response = {"shots": [{"beat_index": i, "video_prompt": prompt} for i in range(1, 7)]}
        with patch.object(producer, "text_json", return_value=response) as mocked:
            result = producer.generate_voice_aware_storyboard(concept)
        self.assertEqual(result["voice_aware_storyboard"]["status"], "generated_after_voice_lock")
        self.assertEqual(result["beats"][0]["video_prompt"], prompt)
        self.assertEqual(result["beats"][0]["speech_segments"][0]["text"], "मैंने तुम्हारी बात सुनी थी।")
        self.assertEqual(result["beats"][0]["voice_timing"]["target_frames"], 120)
        self.assertIn("actual_audio_duration_seconds", mocked.call_args.args[1])
        self.assertIn("target_duration_seconds", mocked.call_args.args[1])
        self.assertIn("narrative_role", mocked.call_args.args[1])
        self.assertIn("state_change", mocked.call_args.args[1])
        self.assertIn("causal_link", mocked.call_args.args[1])

    def test_final_storyboard_refuses_to_run_before_voice_lock(self):
        with self.assertRaisesRegex(RuntimeError, "requires measured TTS audio"):
            producer.generate_voice_aware_storyboard({"beats": [], "characters": []})

    def test_tts_payload_keeps_spoken_text_separate_and_wraps_pcm(self):
        raw_pcm = (b"\x01\x00" * 24000)  # 1 sec, 24 kHz, mono, signed 16-bit samples
        encoded = base64.b64encode(raw_pcm).decode("ascii")
        response = Mock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = {"steps": [{"type": "model_output", "content": [{"type": "audio", "data": encoded}]}]}
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "voice.wav"
            with patch.object(producer.requests, "post", return_value=response) as mocked:
                producer.tts_wav("यह केवल बोली जाने वाली पंक्ति है।", out, voice_direction="धीमे बोलें; आखिरी शब्द में हल्की नरमी रखें।", voice_name="Puck")
            payload = mocked.call_args.kwargs["json"]
            self.assertEqual(payload["input"][0]["content"][0]["text"], "यह केवल बोली जाने वाली पंक्ति है।")
            self.assertEqual(payload["response_format"]["mime_type"], "audio/l16")
            self.assertEqual(payload["generation_config"]["speech_config"][0]["voice"], "Puck")
            style = payload["input"][0]["content"][0]["annotations"][0]["style"]
            self.assertIn("धीमे बोलें", style)
            self.assertTrue(style.startswith("Natural Hindi; warm, grounded, restrained, clear diction."))
            self.assertLessEqual(len(style), 190)
            with wave.open(str(out), "rb") as wav_file:
                self.assertEqual(wav_file.getnchannels(), 1)
                self.assertEqual(wav_file.getsampwidth(), 2)
                self.assertEqual(wav_file.getframerate(), 24000)
                self.assertEqual(wav_file.getnframes(), 24000)

    def test_tts_client_error_is_not_retried(self):
        response = Mock()
        response.status_code = 400
        response.text = '{"error":{"message":"invalid voice"}}'
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(producer, "TTS_MIN_INTERVAL_SECONDS", 0), \
             patch.object(producer, "_LAST_TTS_REQUEST_AT", 0), \
             patch.object(producer.requests, "post", return_value=response) as mocked_post, \
             patch.object(producer.time, "sleep") as mocked_sleep:
            with self.assertRaisesRegex(RuntimeError, "non-retryable HTTP 400"):
                producer.tts_wav("यह परीक्षण पंक्ति है।", Path(folder) / "voice.wav", voice_name="Puck")
        mocked_post.assert_called_once()
        mocked_sleep.assert_not_called()

    def test_tts_success_response_without_audio_is_not_retried(self):
        response = Mock()
        response.status_code = 200
        response.text = ""
        response.json.return_value = {"status": "completed", "steps": []}
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(producer, "TTS_MIN_INTERVAL_SECONDS", 0), \
             patch.object(producer, "_LAST_TTS_REQUEST_AT", 0), \
             patch.object(producer.requests, "post", return_value=response) as mocked_post, \
             patch.object(producer.time, "sleep") as mocked_sleep:
            with self.assertRaisesRegex(ValueError, "No audio block"):
                producer.tts_wav("यह परीक्षण पंक्ति है।", Path(folder) / "voice.wav", voice_name="Puck")
        mocked_post.assert_called_once()
        mocked_sleep.assert_not_called()

    def test_tts_cache_reuses_exact_text_and_valid_wav_across_reruns(self):
        text = "एक छोटी कहानी की परीक्षण पंक्ति।"
        digest = producer.tts_cache_fingerprint(text)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old_cache = producer.TTS_CACHE_DIR
            cache_dir = root / "cache"
            producer.TTS_CACHE_DIR = cache_dir
            try:
                cache_dir.mkdir()
                cached = cache_dir / f"{digest}.wav"
                with wave.open(str(cached), "wb") as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(24000)
                    wav_file.writeframes(b"\x00\x00" * 24000)
                (cache_dir / f"{digest}.wav.sha256").write_text(digest, encoding="ascii")
                out = root / "new-run-output" / "voice.wav"
                with patch.object(producer, "tts_wav") as mocked_tts:
                    self.assertEqual(producer.ensure_tts_wav(text, out), "cached")
                    mocked_tts.assert_not_called()
                self.assertTrue(out.exists())
                self.assertTrue(out.with_suffix(out.suffix + ".sha256").exists())
            finally:
                producer.TTS_CACHE_DIR = old_cache


    def test_tts_cache_identity_includes_voice_and_performance_direction(self):
        text = "यह एक छोटी सी परीक्षण पंक्ति है।"
        first = producer.tts_cache_fingerprint(text, "calm", "Puck")
        second = producer.tts_cache_fingerprint(text, "calm", "Gacrux")
        third = producer.tts_cache_fingerprint(text, "angry", "Puck")
        self.assertNotEqual(first, second)
        self.assertNotEqual(first, third)

    def test_tts_cache_accepts_valid_nine_second_audio_then_scene_planner_enforces_shot_limit(self):
        text = "यह नौ सेकंड की सीमा जाँचने वाली परीक्षण पंक्ति है।"
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old_cache = producer.TTS_CACHE_DIR
            old_interval = producer.TTS_MIN_INTERVAL_SECONDS
            old_last = producer._LAST_TTS_REQUEST_AT
            producer.TTS_CACHE_DIR = root / "cache"
            producer.TTS_MIN_INTERVAL_SECONDS = 0
            producer._LAST_TTS_REQUEST_AT = 0
            try:
                out = root / "render" / "long-line.wav"

                def fake_tts(line, destination, voice_direction=None, voice_name=None):
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with wave.open(str(destination), "wb") as wav_file:
                        wav_file.setnchannels(1)
                        wav_file.setsampwidth(2)
                        wav_file.setframerate(24000)
                        wav_file.writeframes(b"\x00\x00" * (24000 * 9))

                with patch.object(producer, "tts_wav", side_effect=fake_tts):
                    self.assertEqual(producer.ensure_tts_wav(text, out), "generated")
                self.assertTrue(producer._valid_tts_wav(out))
                self.assertAlmostEqual(producer.voice_first.wav_duration(out), 9.0, places=3)
                with self.assertRaisesRegex(ValueError, "Beat voice track requires"):
                    producer.voice_first.build_scene_timing_plan(
                        [{"segment_id": "long_line", "speaker_id": "narrator"}],
                        {"long_line": 9.0},
                    )
            finally:
                producer.TTS_CACHE_DIR = old_cache
                producer.TTS_MIN_INTERVAL_SECONDS = old_interval
                producer._LAST_TTS_REQUEST_AT = old_last

    def test_tts_wav_validation_reports_measured_duration_outside_transport_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "too-long.wav"
            with wave.open(str(path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(24000)
                wav_file.writeframes(b"\x00\x00" * (24000 * 13))
            reason = producer._tts_wav_validation_error(path)
            self.assertIn("measured duration 13.000s", reason)
            self.assertIn("12.00s TTS transport/cache range", reason)
            self.assertFalse(producer._valid_tts_wav(path))

    def test_tts_cache_marks_new_audio_for_cross_run_persistence(self):
        text = "नया ऑडियो कैश परीक्षण।"
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old_cache = producer.TTS_CACHE_DIR
            old_interval = producer.TTS_MIN_INTERVAL_SECONDS
            old_last = producer._LAST_TTS_REQUEST_AT
            producer.TTS_CACHE_DIR = root / "cache"
            producer.TTS_MIN_INTERVAL_SECONDS = 0
            producer._LAST_TTS_REQUEST_AT = 0
            try:
                out = root / "render" / "voice.wav"
                def fake_tts(line, destination, voice_direction=None, voice_name=None):
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with wave.open(str(destination), "wb") as wav_file:
                        wav_file.setnchannels(1)
                        wav_file.setsampwidth(2)
                        wav_file.setframerate(24000)
                        wav_file.writeframes(b"\x00\x00" * 24000)
                with patch.object(producer, "tts_wav", side_effect=fake_tts):
                    self.assertEqual(producer.ensure_tts_wav(text, out), "generated")
                digest = producer.tts_cache_fingerprint(text)
                self.assertTrue((producer.TTS_CACHE_DIR / f"{digest}.wav").exists())
                self.assertTrue((producer.TTS_CACHE_DIR / f"{digest}.wav.sha256").exists())
                self.assertTrue((producer.TTS_CACHE_DIR / ".dirty").exists())
            finally:
                producer.TTS_CACHE_DIR = old_cache
                producer.TTS_MIN_INTERVAL_SECONDS = old_interval
                producer._LAST_TTS_REQUEST_AT = old_last

    def test_original_graphic_scene_renders_full_vertical_canvas(self):
        from PIL import Image
        beat = {
            "visual_query": "phone message notebook desk",
            "voiceover": "कभी-कभी सीमा बताना जरूरी होता है।",
            "screen_text": "एक स्पष्ट सीमा",
            "overlay_text": "अपनी प्राथमिकता",
            "overlay_type": "note",
        }
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "scene.png"
            producer.create_original_scene_image(beat, 1, 6, target)
            self.assertTrue(target.exists())
            self.assertGreater(target.stat().st_size, 10_000)
            with Image.open(target) as image:
                self.assertEqual(image.size, (1080, 1920))
                self.assertEqual(image.format, "PNG")

    def test_cover_background_is_full_vertical_brand_canvas(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "cover_bg.png"
            producer.create_cover_background(target, "एक अलग शीर्षक")
            self.assertTrue(target.exists())
            with Image.open(target) as image:
                self.assertEqual(image.size, (1080, 1920))
                self.assertEqual(image.format, "PNG")

    def test_visual_qa_fails_closed_for_critical_rendered_defects(self):
        with self.assertRaisesRegex(RuntimeError, "critical visual defect"):
            producer.enforce_visual_qa({"status": "warning", "critical_issue": True})

    def test_visual_qa_outage_never_fabricates_an_ai_review(self):
        with self.assertRaisesRegex(RuntimeError, "did not complete successfully"):
            producer.enforce_visual_qa({"status": "not_completed", "human_review_required": True})

        local_fallback = {
            "status": "local_pass_human_review",
            "critical_issue": False,
            "review_mode": "deterministic_local_fallback",
            "human_review_required": True,
            "local_visual_diagnostics": {
                "status": "passed",
                "engine": "bsk_local_frame_qa_v1",
                "frames_scanned": 4,
                "hard_failures": [],
            },
            "metadata_ocr_qa": {"status": "passed", "forbidden_terms_detected": []},
            "full_video_motion_diagnostics": {"status": "passed", "full_video_scanned": True},
        }
        producer.enforce_visual_qa(local_fallback)

        local_fallback["local_visual_diagnostics"]["status"] = "warning"
        with self.assertRaisesRegex(RuntimeError, "Local visual QA did not pass"):
            producer.enforce_visual_qa(local_fallback)

    def test_visual_qa_requires_ocr_and_full_video_motion_to_pass(self):
        base = {
            "status": "reviewed",
            "critical_issue": False,
            "metadata_ocr_qa": {"status": "passed", "forbidden_terms_detected": []},
        }
        with self.assertRaisesRegex(RuntimeError, "Full-video black/freeze diagnostics"):
            producer.enforce_visual_qa(base)
        with self.assertRaisesRegex(RuntimeError, "Metadata OCR"):
            producer.enforce_visual_qa({
                **base,
                "full_video_motion_diagnostics": {"status": "passed", "full_video_scanned": True},
                "metadata_ocr_qa": {"status": "not_completed"},
            })
        producer.enforce_visual_qa({
            **base,
            "full_video_motion_diagnostics": {"status": "passed", "full_video_scanned": True},
        })

    def test_metadata_ocr_rejects_internal_prompt_labels(self):
        from subprocess import CompletedProcess
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            video = root / "reel.mp4"
            video.write_bytes(b"video")
            def fake_extract(command, timeout=240):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                (Path(command[-1]).parent / "ocr_0001.jpg").write_bytes(b"frame-a")
                (Path(command[-1]).parent / "ocr_0002.jpg").write_bytes(b"frame-b")
            outputs = [
                CompletedProcess([], 0, stdout="normal subtitle text", stderr=""),
                CompletedProcess([], 0, stdout="KEYWORD STEP appeared on screen", stderr=""),
            ]
            with patch.object(producer.shutil, "which", return_value="/usr/bin/tesseract"), \
                 patch.object(producer, "run_cmd", side_effect=fake_extract), \
                 patch.object(producer.subprocess, "run", side_effect=outputs):
                report = producer.metadata_ocr_qa(video, root, 2.0)
            self.assertEqual(report["status"], "warning")
            self.assertEqual(report["frames_scanned"], 2)
            self.assertEqual({x["term"] for x in report["forbidden_terms_detected"]}, {"KEYWORD", "STEP"})

    def test_metadata_ocr_fails_closed_when_tesseract_is_unavailable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(producer.shutil, "which", return_value=None):
                report = producer.metadata_ocr_qa(root / "reel.mp4", root, 2.0)
        self.assertEqual(report["status"], "not_completed")

    def test_visual_qa_requires_character_continuity_and_metadata_dimensions(self):
        with tempfile.TemporaryDirectory() as folder:
            reel_dir = Path(folder)
            def fake_extract(command, timeout=240):
                from PIL import Image
                Image.new("RGB", (540, 960), (65, 75, 90)).save(Path(command[-1]), format="JPEG", quality=90)
            response = {
                "scores": {
                    "text_legibility": 5, "devanagari_rendering": 5,
                    "anatomy_integrity": 5, "story_visual_match": 5,
                    "safe_composition": 5, "visual_quality": 4,
                    "character_continuity": 2, "metadata_text_cleanliness": 1,
                },
                "critical_issue": True, "notes": ["Wardrobe drift and internal overlay label visible."],
                "confidence": "high",
            }
            with patch.object(producer, "run_cmd", side_effect=fake_extract), patch.object(
                producer, "gemini_json_with_images", return_value=response
            ) as audit, patch.object(
                producer, "metadata_ocr_qa", return_value={"status": "passed", "forbidden_terms_detected": []}
            ):
                result = producer.visual_qa(
                    reel_dir / "reel.mp4", reel_dir, 35.0,
                    segment_durations=[5.8] * 6,
                )
            prompt = audit.call_args.args[1]
            self.assertIn("Compare recurring characters across all frames", prompt)
            self.assertIn("KEYWORD, STEP, CONTRAST", prompt)
            self.assertEqual(result["scores"]["character_continuity"], 2)
            self.assertEqual(result["scores"]["metadata_text_cleanliness"], 1)
            self.assertEqual(result["status"], "warning")

    def test_visual_qa_does_not_mark_reviewed_when_required_dimensions_are_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            reel_dir = Path(folder)
            def fake_extract(command, timeout=240):
                from PIL import Image
                Image.new("RGB", (540, 960), (65, 75, 90)).save(Path(command[-1]), format="JPEG", quality=90)
            incomplete = {
                "scores": {"text_legibility": 5, "visual_quality": 5},
                "critical_issue": False, "notes": [], "confidence": "low",
            }
            with patch.object(producer, "run_cmd", side_effect=fake_extract), patch.object(
                producer, "gemini_json_with_images", return_value=incomplete
            ), patch.object(
                producer, "metadata_ocr_qa", return_value={"status": "passed", "forbidden_terms_detected": []}
            ):
                result = producer.visual_qa(
                    reel_dir / "reel.mp4", reel_dir, 35.0,
                    segment_durations=[5.8] * 6,
                )
            self.assertEqual(result["status"], "local_pass_human_review")
            self.assertEqual(result["visual_ai_review"]["status"], "not_completed")
            self.assertTrue(result["human_review_required"])

    def test_visual_qa_rejects_boolean_out_of_range_and_non_finite_scores(self):
        required = (
            "text_legibility", "devanagari_rendering", "anatomy_integrity",
            "story_visual_match", "safe_composition", "visual_quality",
            "character_continuity", "metadata_text_cleanliness",
        )
        bad_values = (True, 0, 5.1, float("nan"), float("inf"))
        with tempfile.TemporaryDirectory() as folder:
            reel_dir = Path(folder)

            def fake_extract(command, timeout=240):
                from PIL import Image
                Image.new("RGB", (540, 960), (65, 75, 90)).save(Path(command[-1]), format="JPEG", quality=90)

            for bad_value in bad_values:
                response = {
                    "scores": {key: 5 for key in required},
                    "critical_issue": False,
                    "notes": [],
                    "confidence": "high",
                }
                response["scores"]["character_continuity"] = bad_value
                with self.subTest(bad_value=repr(bad_value)), patch.object(
                    producer, "run_cmd", side_effect=fake_extract
                ), patch.object(producer, "gemini_json_with_images", return_value=response), patch.object(
                    producer, "metadata_ocr_qa", return_value={"status": "passed", "forbidden_terms_detected": []}
                ):
                    result = producer.visual_qa(
                        reel_dir / "reel.mp4", reel_dir, 35.0,
                        segment_durations=[5.8] * 6,
                    )
                self.assertEqual(result["status"], "local_pass_human_review")
                self.assertEqual(result["visual_ai_review"]["status"], "not_completed")
                self.assertTrue(result["human_review_required"])

    def test_visual_qa_requires_boolean_critical_issue_field(self):
        required = (
            "text_legibility", "devanagari_rendering", "anatomy_integrity",
            "story_visual_match", "safe_composition", "visual_quality",
            "character_continuity", "metadata_text_cleanliness",
        )
        response = {
            "scores": {key: 5 for key in required},
            "critical_issue": "false",
            "notes": [],
            "confidence": "high",
        }
        with tempfile.TemporaryDirectory() as folder:
            reel_dir = Path(folder)

            def fake_extract(command, timeout=240):
                from PIL import Image
                Image.new("RGB", (540, 960), (65, 75, 90)).save(Path(command[-1]), format="JPEG", quality=90)

            with patch.object(producer, "run_cmd", side_effect=fake_extract), patch.object(
                producer, "gemini_json_with_images", return_value=response
            ), patch.object(
                producer, "metadata_ocr_qa", return_value={"status": "passed", "forbidden_terms_detected": []}
            ):
                result = producer.visual_qa(
                    reel_dir / "reel.mp4", reel_dir, 35.0,
                    segment_durations=[5.8] * 6,
                )
        self.assertEqual(result["status"], "local_pass_human_review")
        self.assertEqual(result["visual_ai_review"]["status"], "not_completed")
        self.assertTrue(result["human_review_required"])

    def test_pexels_is_optional_when_free_local_graphics_are_available(self):
        with patch.object(producer, "GEMINI_API_KEY", "test-key"), \
             patch.object(producer, "TELEGRAM_BOT_TOKEN", "test-token"), \
             patch.object(producer, "PEXELS_API_KEY", ""):
            producer.require_env()  # Pexels key intentionally omitted.

    def test_published_command_marks_exact_title_as_confirmed(self):
        history = {"topics": [{"title": "एक अलग कहानी", "pillar": "micro_story", "status": "ready_for_manual_publish_not_confirmed_published"}]}
        record = producer._parse_published_message("/published title=एक अलग कहानी; url=https://facebook.com/reel/123", history)
        self.assertFalse(record["already_published"])
        self.assertEqual(history["topics"][0]["status"], "published_manual_confirmed")
        self.assertEqual(history["topics"][0]["facebook_post_url"], "https://facebook.com/reel/123")
        record_again = producer._parse_published_message("/published title=एक अलग कहानी", history)
        self.assertTrue(record_again["already_published"])

    def test_final_audio_mix_applies_true_peak_headroom_without_limiter_makeup_gain(self):
        filter_graph = producer.final_audio_mix_filter()
        self.assertIn("amix=inputs=2:duration=first", filter_graph)
        self.assertIn("volume=0.22[bed]", filter_graph)
        self.assertIn("loudnorm=I=-16:TP=-2.5:LRA=11", filter_graph)
        self.assertIn("alimiter=limit=0.84:level=false[a]", filter_graph)

    def test_final_audio_loudness_measurement_parses_ffmpeg_json(self):
        payload = (
            'video stream metadata\\n'
            + '{"input_i" : "-16.31", "input_tp" : "-2.42", '
            + '"input_lra" : "3.80", "input_thresh" : "-26.50"}'
        )
        with tempfile.TemporaryDirectory() as folder:
            media = Path(folder) / "reel.mp4"
            media.write_bytes(b"valid media placeholder")
            with patch.object(producer.subprocess, "run", return_value=Mock(returncode=0, stderr=payload, stdout="")) as mocked:
                result = producer.measure_audio_loudness(media)
        self.assertEqual(result["integrated_loudness_lufs"], -16.31)
        self.assertEqual(result["true_peak_dbtp"], -2.42)
        self.assertIn("loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", mocked.call_args.args[0])

    def test_final_audio_qa_accepts_encoded_audio_inside_limits_without_remaster(self):
        measured = {"integrated_loudness_lufs": -16.2, "true_peak_dbtp": -2.1}
        with (
            patch.object(producer, "measure_audio_loudness", return_value=measured),
            patch.object(producer, "run_cmd") as remaster,
        ):
            result = producer.enforce_final_audio_qa(Path("reel.mp4"))
        self.assertEqual(result["status"], "passed")
        self.assertFalse(result["remastered"])
        self.assertEqual(result["measured"], measured)
        remaster.assert_not_called()

    def test_final_audio_qa_remasters_hot_aac_once_and_rechecks_before_replace(self):
        before = {"integrated_loudness_lufs": -15.15, "true_peak_dbtp": 0.31}
        after = {"integrated_loudness_lufs": -16.67, "true_peak_dbtp": -2.46}
        command_seen = []

        def fake_remaster(command, timeout=240):
            command_seen.append(command)
            Path(command[-1]).write_bytes(b"remastered-aac" * 10000)

        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "reel.mp4"
            video.write_bytes(b"original-video" * 1000)
            original = video.read_bytes()
            with (
                patch.object(producer, "measure_audio_loudness", side_effect=[before, after]),
                patch.object(producer, "run_cmd", side_effect=fake_remaster),
            ):
                result = producer.enforce_final_audio_qa(video)
            self.assertEqual(video.read_bytes(), b"remastered-aac" * 10000)
            self.assertNotEqual(video.read_bytes(), original)
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["remastered"])
        self.assertEqual(result["before"], before)
        self.assertEqual(result["measured"], after)
        self.assertIn("level=false", " ".join(command_seen[0]))
        self.assertIn("48000", command_seen[0])

    def test_final_audio_qa_fails_closed_and_preserves_original_when_remaster_stays_hot(self):
        before = {"integrated_loudness_lufs": -15.15, "true_peak_dbtp": 0.31}
        still_hot = {"integrated_loudness_lufs": -16.0, "true_peak_dbtp": -0.4}

        def fake_remaster(command, timeout=240):
            Path(command[-1]).write_bytes(b"unsafe-remaster" * 10000)

        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "reel.mp4"
            original = b"original-video" * 1000
            video.write_bytes(original)
            with (
                patch.object(producer, "measure_audio_loudness", side_effect=[before, still_hot]),
                patch.object(producer, "run_cmd", side_effect=fake_remaster),
            ):
                with self.assertRaisesRegex(RuntimeError, "remaster"):
                    producer.enforce_final_audio_qa(video)
            self.assertEqual(video.read_bytes(), original)

    def test_sound_bed_has_valid_stereo_wave(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "bed.wav"
            producer.create_original_sound_bed(target, 2.0, "micro_story")
            with wave.open(str(target), "rb") as f:
                self.assertEqual(f.getnchannels(), 2)
                self.assertEqual(f.getsampwidth(), 2)
                self.assertEqual(f.getframerate(), 24000)
                self.assertEqual(f.getnframes(), 48000)

    def test_strict_ai_video_fails_before_spending_tts_if_clip_missing(self):
        concept = self.sample_concept()
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"REQUIRE_AI_VIDEO": "1"}), patch.object(producer, "tts_wav") as mocked_tts:
            with self.assertRaisesRegex(RuntimeError, "missing required clips before TTS starts"):
                producer.render_reel(concept, Path(folder), set(), set())
            mocked_tts.assert_not_called()

    def test_borderline_ai_scene_uses_tiny_pitch_preserving_audio_fit_only_when_enabled(self):
        clip_duration = 3.375
        audio_duration = clip_duration * 1.39 - 0.08

        unassisted = producer.fit_ai_scene_timing(audio_duration, clip_duration)
        self.assertEqual(unassisted["audio_tempo"], 1.0)
        self.assertLessEqual(unassisted["video_speed_ratio"], 1.38)
        self.assertGreater(unassisted["video_hold_duration"], 0.0)
        self.assertLessEqual(unassisted["video_hold_duration"], 1.20)

        assisted = producer.fit_ai_scene_timing(
            audio_duration, clip_duration, allow_tiny_audio_tempo_fit=True
        )
        self.assertGreater(assisted["audio_tempo"], 1.0)
        self.assertLessEqual(assisted["audio_tempo"], 1.03)
        self.assertLessEqual(assisted["video_speed_ratio"], 1.38)
        self.assertAlmostEqual(assisted["video_hold_duration"], 0.0, places=3)

    def test_longer_voiceover_uses_bounded_end_hold_instead_of_rejecting_the_reel(self):
        clip_duration = 3.375
        audio_duration = clip_duration * 1.50 - 0.08
        timing = producer.fit_ai_scene_timing(
            audio_duration, clip_duration, allow_tiny_audio_tempo_fit=True
        )
        self.assertEqual(timing["audio_tempo"], 1.0)
        self.assertLessEqual(timing["video_speed_ratio"], 1.38)
        self.assertGreater(timing["video_hold_duration"], 0.0)
        self.assertLessEqual(timing["video_hold_duration"], 1.20)
        self.assertAlmostEqual(
            timing["target_duration"],
            timing["rendered_audio_duration"] + timing["audio_pad_duration"],
            places=3,
        )

    def test_short_voiceover_keeps_ai_scene_at_natural_speed_and_pads_audio(self):
        clip_duration = 3.375
        audio_duration = 2.0
        timing = producer.fit_ai_scene_timing(audio_duration, clip_duration)
        self.assertEqual(timing["video_speed_ratio"], 1.0)
        self.assertEqual(timing["target_duration"], clip_duration)
        self.assertEqual(timing["video_hold_duration"], 0.0)
        self.assertGreater(timing["audio_pad_duration"], 1.0)

    def test_extreme_voiceover_mismatch_still_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "above the 1.20s quality limit"):
            producer.fit_ai_scene_timing(8.0, 3.375, allow_tiny_audio_tempo_fit=True)

    def test_probe_media_accepts_native_24_fps_for_ai_and_30_fps_for_smoke(self):
        body = {"streams": [
            {"codec_type": "video", "width": 1080, "height": 1920, "avg_frame_rate": "24/1", "r_frame_rate": "24/1", "codec_name": "h264"},
            {"codec_type": "audio", "codec_name": "aac"}], "format": {"format_name": "mov,mp4"}}
        response = Mock(returncode=0, stdout=json.dumps(body), stderr="")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "video.mp4"
            path.touch()
            with patch.object(producer.subprocess, "run", return_value=response):
                self.assertEqual(producer.probe_media(path, expected_fps=24)["frame_rate"], "24/1")
            with patch.object(producer.subprocess, "run", return_value=response):
                with self.assertRaisesRegex(RuntimeError, "expected about 30 fps"):
                    producer.probe_media(path, expected_fps=30)

    def test_telegram_state_does_not_select_chat_without_private_start(self):
        with tempfile.TemporaryDirectory() as folder:
            state_path = Path(folder) / "telegram_state.json"
            original = producer.TELEGRAM_STATE_PATH
            producer.TELEGRAM_STATE_PATH = state_path
            original_token = producer.TELEGRAM_BOT_TOKEN
            producer.TELEGRAM_BOT_TOKEN = "dummy-token"
            try:
                response = Mock()
                response.raise_for_status.return_value = None
                response.json.return_value = {"ok": True, "result": [{"update_id": 10, "message": {"text": "hi", "chat": {"id": 999, "type": "private"}}}]}
                with patch.object(producer.requests, "get", return_value=response):
                    with self.assertRaises(RuntimeError):
                        producer.telegram_chat_id()
            finally:
                producer.TELEGRAM_STATE_PATH = original
                producer.TELEGRAM_BOT_TOKEN = original_token

    def test_10k_readiness_is_not_a_view_probability(self):
        concept = self.sample_concept()
        concept["editorial_review"] = {"scores": {
            "hook_clarity": 5, "human_specificity": 5, "emotional_resonance": 5,
            "story_progression": 5, "payoff": 5,
            "originality": 5, "creative_contribution_beyond_stock": 5,
            "share_value": 5, "illustrated_visual_quality": 5,
            "continuity_coherence": 5, "voiceover_rhythm": 5,
            "readability": 5, "platform_safety": 5,
        }}
        result = producer.director_10k_readiness(concept, {
            "technical": {"technical_checks_passed": True, "rendered_frame_visual_qa": {"status": "reviewed"}}
        })
        self.assertEqual(result["score"], 100.0)
        self.assertEqual(result["band"], "STRONG_EDITORIAL_CANDIDATE")
        self.assertIsNone(result["10k_view_probability"])

    def test_readiness_rubric_weights_total_100_and_requires_emotional_dimensions(self):
        concept = self.sample_concept()
        concept["editorial_review"] = {"scores": {"hook_clarity": 5}}
        result = producer.director_10k_readiness(concept, {"technical": {"technical_checks_passed": True}})
        self.assertIn("human_specificity", result["missing_dimensions"])
        self.assertIn("emotional_resonance", result["missing_dimensions"])
        weights = {
            "hook_clarity": 12, "story_progression": 10, "payoff": 10,
            "originality": 10, "creative_contribution_beyond_stock": 8,
            "share_value": 8, "human_specificity": 9, "emotional_resonance": 9,
            "illustrated_visual_quality": 7, "continuity_coherence": 5,
            "voiceover_rhythm": 4, "readability": 3, "platform_safety": 5,
        }
        self.assertEqual(sum(weights.values()), 100)

    def test_10k_readiness_fails_closed_when_scores_missing(self):
        result = producer.director_10k_readiness(self.sample_concept(), {"technical": {"technical_checks_passed": True}})
        self.assertIsNone(result["score"])
        self.assertEqual(result["band"], "NOT_RATED")




    def test_transcript_normalization_ignores_whitespace_and_punctuation(self):
        self.assertEqual(producer.normalize_transcript_for_comparison("नमस्ते, दुनिया!"), producer.normalize_transcript_for_comparison("नमस्ते दुनिया"))

    def test_character_error_rate_detects_changed_words(self):
        self.assertEqual(producer.character_error_rate("नमस्ते दुनिया", "नमस्ते दुनिया"), 0.0)
        self.assertGreater(producer.character_error_rate("नमस्ते दुनिया", "नमस्ते दोस्त"), 0.0)

    def test_review_command_marks_ready_for_manual_publish_only(self):
        history = {"topics": [{"title": "सीमा तय करना", "status": "ready_for_manual_publish_not_confirmed_published", "qa_passed": True}]}
        result = producer._parse_review_message("/approve title=सीमा तय करना", history, approved=True)
        self.assertTrue(result["approved"])
        self.assertEqual(history["topics"][0]["status"], "owner_approved_for_manual_publish")
        self.assertIsNone(history.get("one_reel_qualification"))

    def test_weekly_qualification_requires_full_visual_qa_evidence(self):
        history = {"topics": [{
            "title": "पिता की घड़ी", "status": "ready_for_manual_publish_not_confirmed_published",
            "qa_passed": True, "telegram_delivered": True, "reel_id": "reel_qa_complete",
            "visual_qa_status": "reviewed", "motion_diagnostics_status": "passed",
            "metadata_ocr_status": "passed",
        }]}
        result = producer._parse_review_message("/approve title=पिता की घड़ी", history, approved=True)
        self.assertTrue(result["weekly_qualification_created"])
        qualification = history["one_reel_qualification"]
        self.assertEqual(qualification["status"], "qualified")
        self.assertTrue(qualification["visual_qa_status"] == "reviewed")
        self.assertEqual(qualification["metadata_ocr_status"], "passed")

    def test_weekly_qualification_rejects_missing_ocr_evidence(self):
        history = {"topics": [{
            "title": "पिता की घड़ी", "status": "ready_for_manual_publish_not_confirmed_published",
            "qa_passed": True, "telegram_delivered": True, "reel_id": "reel_qa_missing_ocr",
            "visual_qa_status": "reviewed", "motion_diagnostics_status": "passed",
        }]}
        result = producer._parse_review_message("/approve title=पिता की घड़ी", history, approved=True)
        self.assertFalse(result["weekly_qualification_created"])
        self.assertIsNone(history.get("one_reel_qualification"))

    def test_review_rejection_does_not_mark_as_published(self):
        history = {"topics": [{"title": "सीमा तय करना", "status": "ready_for_manual_publish_not_confirmed_published"}]}
        producer._parse_review_message("/reject title=सीमा तय करना; reason=broken hand", history, approved=False)
        self.assertEqual(history["topics"][0]["status"], "owner_rejected_not_published")
        self.assertNotIn("published_at_ist", history["topics"][0])


class LocalMediaQATests(unittest.TestCase):
    def test_local_asr_matches_known_hindi_text_without_remote_api(self):
        import sys
        import types
        import os
        import producer
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import Mock, patch
        with TemporaryDirectory() as folder:
            reel_dir = Path(folder)
            wav = reel_dir / "voice_01.wav"; wav.write_bytes(b"fake source")
            fake_model = Mock()
            fake_model.transcribe.return_value = ([types.SimpleNamespace(text=" कभी-कभी मदद करना अच्छा होता है। ")], types.SimpleNamespace(language="hi", language_probability=0.96))
            fake_module = types.SimpleNamespace(WhisperModel=Mock(return_value=fake_model))
            def fake_ffmpeg(command, timeout=180):
                Path(command[-1]).write_bytes(b"v" * 8000)
            old_model = producer._ASR_MODEL
            producer._ASR_MODEL = None
            try:
                with patch.dict(sys.modules, {"faster_whisper": fake_module}), patch.object(producer, "run_cmd", side_effect=fake_ffmpeg), patch.dict(os.environ, {"BSK_ASR_QA": "1", "BSK_ASR_MODEL": "large-v3-turbo"}):
                    report = producer.audio_transcript_qa([wav], ["कभी-कभी मदद करना अच्छा होता है।"], reel_dir)
                self.assertEqual(report["status"], "likely_match")
                self.assertEqual(report["character_error_rate"], 0.0)
                self.assertTrue(report["human_review_required"])
            finally:
                producer._ASR_MODEL = old_model

    def test_full_video_motion_diagnostics_flags_black_interval(self):
        import producer
        from pathlib import Path
        from unittest.mock import Mock, patch
        mocked = Mock(returncode=0, stdout="", stderr="black_start:1.0 black_end:1.5 black_duration:0.500")
        with patch.object(producer.subprocess, "run", return_value=mocked) as run:
            report = producer.motion_diagnostics(Path("fake.mp4"))
        self.assertEqual(report["status"], "warning")
        self.assertTrue(report["full_video_scanned"])
        self.assertIn("freezedetect", run.call_args.args[0][run.call_args.args[0].index("-vf") + 1])

class SceneAudioFilterTests(unittest.TestCase):
    def test_silent_scene_bypasses_loudnorm(self):
        audio_filter = producer._scene_audio_filter(1.0, 0.08, has_speech=False)
        self.assertEqual(audio_filter, "apad=pad_dur=0.080,anull")
        self.assertNotIn("loudnorm", audio_filter)

    def test_spoken_scene_keeps_bounded_tempo_and_loudnorm(self):
        audio_filter = producer._scene_audio_filter(1.02, 0.08, has_speech=True)
        self.assertEqual(
            audio_filter,
            "atempo=1.020000,apad=pad_dur=0.080,loudnorm=I=-16:TP=-1.5:LRA=11",
        )

    def test_scene_audio_filter_rejects_nonfinite_timing(self):
        with self.assertRaisesRegex(ValueError, "tempo must be finite"):
            producer._scene_audio_filter(float("nan"), 0.08, has_speech=False)
        with self.assertRaisesRegex(ValueError, "padding must be finite"):
            producer._scene_audio_filter(1.0, float("inf"), has_speech=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
