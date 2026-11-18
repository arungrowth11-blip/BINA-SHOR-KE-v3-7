from __future__ import annotations

import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import tts_smoke_test  # noqa: E402


class LiveTtsSmokeValidationTests(unittest.TestCase):
    def make_wav(
        self,
        path: Path,
        *,
        sample_rate: int = 24000,
        channels: int = 1,
        sample_width: int = 2,
        sample_value: int = 8192,
        duration_seconds: float = 1.0,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        frame_count = round(sample_rate * duration_seconds)
        if sample_width != 2:
            frame = bytes(sample_width * channels)
        else:
            frame = int(sample_value).to_bytes(2, "little", signed=True) * channels
        with wave.open(str(path), "wb") as output:
            output.setnchannels(channels)
            output.setsampwidth(sample_width)
            output.setframerate(sample_rate)
            output.writeframes(frame * frame_count)

    def test_accepts_audible_24khz_mono_pcm_and_reports_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "speech.wav"
            self.make_wav(path)
            report = tts_smoke_test.inspect_wav(path)
        self.assertEqual(report["sample_rate_hz"], 24000)
        self.assertEqual(report["channels"], 1)
        self.assertEqual(report["sample_width_bits"], 16)
        self.assertEqual(report["duration_seconds"], 1.0)
        self.assertEqual(report["machine_audio_checks"], "passed")
        self.assertEqual(len(report["sha256"]), 64)
        self.assertGreater(report["rms_amplitude"], 32)

    def test_rejects_wrong_sample_rate(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "wrong-rate.wav"
            self.make_wav(path, sample_rate=16000)
            with self.assertRaisesRegex(ValueError, "24 kHz"):
                tts_smoke_test.inspect_wav(path)

    def test_rejects_silent_audio_even_when_wav_container_is_valid(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "silence.wav"
            self.make_wav(path, sample_value=0)
            with self.assertRaisesRegex(ValueError, "effectively silent"):
                tts_smoke_test.inspect_wav(path)

    def test_report_is_written_atomically_as_valid_utf8_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "nested" / "report.json"
            tts_smoke_test.write_report(path, {"status": "failed", "note": "हिंदी"})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["note"], "हिंदी")
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_error_output_redacts_configured_api_key(self):
        key = "AIza0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        previous = tts_smoke_test.producer.GEMINI_API_KEY
        try:
            tts_smoke_test.producer.GEMINI_API_KEY = key
            message = tts_smoke_test.safe_error(RuntimeError("request failed with " + key))
        finally:
            tts_smoke_test.producer.GEMINI_API_KEY = previous
        self.assertNotIn(key, message)
        self.assertIn("[REDACTED]", message)


if __name__ == "__main__":
    unittest.main()
