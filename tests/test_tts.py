import base64
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bsk.audio.tts import GeminiTTS


def make_wav_bytes():
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "stub.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(b"\x00\x00" * 24000)
        return path.read_bytes()


class FakeResponse:
    status_code = 200
    headers = {}
    text = ""

    def __init__(self, data):
        self.data = data

    def json(self):
        return {"output_audio": {"data": self.data}}


class TtsTests(unittest.TestCase):
    def test_whole_narration_wav_and_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            wav_bytes = make_wav_bytes()
            config = SimpleNamespace(
                gemini_api_key="test-key",
                gemini_tts_model="gemini-3.8-flash-tts",
                tts_voice="Kore",
                tts_style="natural Hindi",
                tts_cache_dir=Path(temp) / "cache",
                request_timeout_seconds=5,
                confirm_free_only=True,
            )
            tts = GeminiTTS(config)
            destination = Path(temp) / "job" / "narration.wav"
            with patch("bsk.audio.tts.requests.post", return_value=FakeResponse(base64.b64encode(wav_bytes).decode())) as post:
                status, info = tts.generate("यह पूरी कहानी की आवाज़ है।", destination)
                self.assertEqual(status, "generated")
                self.assertEqual(info["duration_seconds"], 1.0)
                second = Path(temp) / "job" / "narration_copy.wav"
                status2, info2 = tts.generate("यह पूरी कहानी की आवाज़ है।", second)
                self.assertEqual(status2, "cached")
                self.assertEqual(info2["duration_seconds"], 1.0)
                self.assertEqual(post.call_count, 1)
                self.assertTrue(second.exists())


if __name__ == "__main__":
    unittest.main()
