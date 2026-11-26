from __future__ import annotations
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import factory_supervisor  # noqa: E402


class FactorySupervisorTests(unittest.TestCase):
    def test_transient_provider_errors_are_bounded_retry_candidates(self):
        for error in ("Gemini HTTP 503 Service Unavailable", "provider HTTP 429", "HTTP 502 Bad Gateway", "read timed out"):
            with self.subTest(error=error):
                self.assertEqual(factory_supervisor.classify_finalization_failure(error), "transient_provider")

    def test_voice_integrity_failures_are_never_auto_retried(self):
        for error in ("Voice cache mismatch: planned 3.280s, received 3.560s",
                      "Locked voice asset SHA-256 mismatch",
                      "Exact Director-run voice cache is missing or invalid"):
            with self.subTest(error=error):
                self.assertEqual(factory_supervisor.classify_finalization_failure(error), "non_retryable_integrity_or_qa")

    def test_hard_qa_and_audio_errors_are_never_auto_retried(self):
        for error in ("critical visual defect in frame 4", "metadata OCR is failed",
                      "Full-video motion diagnostics are incomplete",
                      "Final audio QA true peak +0.3 dBTP exceeds the limit"):
            with self.subTest(error=error):
                self.assertEqual(factory_supervisor.classify_finalization_failure(error), "non_retryable_integrity_or_qa")

    def test_finalization_retry_backoff_is_bounded(self):
        self.assertEqual(factory_supervisor.finalization_retry_delay_seconds(1), 30)
        self.assertEqual(factory_supervisor.finalization_retry_delay_seconds(2), 90)
        self.assertIsNone(factory_supervisor.finalization_retry_delay_seconds(3))

    def test_active_job_keeps_polling_before_chunk_limit(self):
        self.assertIsNone(factory_supervisor.next_watch_action(
            "KernelWorkerStatus.QUEUED", chunk_elapsed_seconds=600, total_elapsed_seconds=600,
            chunk_limit_seconds=10800, total_limit_seconds=43200))

    def test_active_job_chains_after_watch_chunk(self):
        self.assertEqual(factory_supervisor.next_watch_action(
            "RUNNING", chunk_elapsed_seconds=10800, total_elapsed_seconds=10800,
            chunk_limit_seconds=10800, total_limit_seconds=43200), "watch")

    def test_terminal_job_moves_to_finalizer(self):
        for status in ("COMPLETE", "FAILED", "KernelWorkerStatus.CANCELLED"):
            with self.subTest(status=status):
                self.assertEqual(factory_supervisor.next_watch_action(
                    status, chunk_elapsed_seconds=20, total_elapsed_seconds=20,
                    chunk_limit_seconds=10800, total_limit_seconds=43200), "poll")

    def test_unknown_status_stops_without_dispatch(self):
        self.assertEqual(factory_supervisor.next_watch_action(
            "UNKNOWN", chunk_elapsed_seconds=20, total_elapsed_seconds=20,
            chunk_limit_seconds=10800, total_limit_seconds=43200), "stop")

    def test_exact_tts_cache_key_is_director_run_and_attempt_scoped(self):
        self.assertEqual(factory_supervisor.exact_tts_cache_key("Linux", "45166930219", 1),
                         "bsk-tts-Linux-45166930219-1")
        with self.assertRaises(ValueError):
            factory_supervisor.exact_tts_cache_key("Linux", "", 1)
        with self.assertRaises(ValueError):
            factory_supervisor.exact_tts_cache_key("Linux", "45166930219", 0)


if __name__ == "__main__":
    unittest.main()
