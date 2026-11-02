import tempfile
import unittest
import wave
from pathlib import Path

from bsk.audio.asr import character_error_rate
from bsk.audio.wav import inspect_wav
from bsk.errors import GateError


class AudioTests(unittest.TestCase):
    def test_wav_duration_and_format(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "voice.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(24000)
                wav.writeframes(b"\x00\x00" * 24000)
            info = inspect_wav(path)
            self.assertEqual(info["duration_seconds"], 1.0)
            self.assertEqual(info["sample_rate_hz"], 24000)

    def test_wrong_sample_rate_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b"\x00\x00" * 16000)
            with self.assertRaises(GateError):
                inspect_wav(path)

    def test_character_error_rate(self):
        self.assertEqual(character_error_rate("नमस्ते दुनिया", "नमस्ते दुनिया"), 0.0)
        self.assertGreater(character_error_rate("नमस्ते दुनिया", "नमस्ते दुनिया!"), -0.01)
        self.assertGreater(character_error_rate("नमस्ते", "दुनिया"), 0.5)


if __name__ == "__main__":
    unittest.main()
