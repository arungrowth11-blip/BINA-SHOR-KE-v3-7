from __future__ import annotations
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class WorkflowConfigTests(unittest.TestCase):
    def test_weekly_dispatch_runs_saturday_in_ist(self):
        body = (ROOT / '.github' / 'workflows' / 'weekly-factory.yml').read_text(encoding='utf-8')
        self.assertIn('cron: "37 7 * * 6"', body)
        self.assertIn('timezone: "Asia/Kolkata"', body)
        self.assertNotIn('cron: "37 7 * * 0"', body)

    def test_optional_provider_secrets_and_cloudflare_model_are_yaml_safe(self):
        for name in ("weekly-factory.yml", "poll-gpu.yml"):
            body = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
            self.assertIn("GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}", body)
            self.assertIn("MISTRAL_API_KEY: ${{ secrets.MISTRAL_API_KEY }}", body)
            self.assertIn('CF_TEXT_MODEL: "@cf/meta/llama-3.1-8b-instruct"', body)


    def test_gpu_workflow_has_guarded_same_reel_retry_action(self):
        body = (ROOT / '.github' / 'workflows' / 'poll-gpu.yml').read_text(encoding='utf-8')
        self.assertIn('retry-gpu', body)
        self.assertIn('repair-rhythm', body)
        self.assertIn('Repair borderline narration rhythm using the same AI scenes', body)
        self.assertIn("[ \"$POLL_ACTION\" = 'repair-rhythm' ]", body)
        self.assertIn('repair-rhythm-finalize', body)
        self.assertIn('Retry the same Reel after the KSampler schema fix', body)
        self.assertIn('refusing to silently skip GPU work', body)
        pipeline = (ROOT / 'scripts' / 'studio_pipeline.py').read_text(encoding='utf-8')
        self.assertIn('def retry_failed_gpu()', pipeline)
        self.assertIn('control_after_generate', pipeline)

    def test_kaggle_cli_installs_six_explicitly_for_status_and_repair(self):
        body = (ROOT / '.github' / 'workflows' / 'poll-gpu.yml').read_text(encoding='utf-8')
        expected = '"six>=1.16.0,<2" kaggle'
        self.assertEqual(body.count(expected), 2)
        self.assertIn('Quick remote Kaggle status check (minimal CLI only)', body)
        self.assertIn('Install dependencies and configure private Kaggle CLI', body)

    def test_telegram_feedback_sync_runs_independently_of_gpu_batches(self):
        body = (ROOT / '.github' / 'workflows' / 'telegram-feedback-sync.yml').read_text(encoding='utf-8')
        self.assertIn('cron: "17 */6 * * *"', body)
        self.assertIn('timezone: "Asia/Kolkata"', body)
        self.assertIn('TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}', body)
        self.assertIn('scripts/telegram_feedback_sync.py', body)
        self.assertIn('data/telegram_state.json data/history.json data/performance_log.csv', body)
        self.assertIn('group: bina-shor-ke-studio', body)

    def test_gpu_poller_is_bounded_and_has_zero_paid_fallback(self):
        body = (ROOT / '.github' / 'workflows' / 'poll-gpu.yml').read_text(encoding='utf-8')
        self.assertIn('timeout-minutes: 180', body)
        self.assertIn('Check whether a GPU batch actually needs polling', body)
        self.assertIn("steps.pending.outputs.active == 'true'", body)
        self.assertIn("dispatch_unknown", (ROOT / 'scripts' / 'studio_pipeline.py').read_text(encoding='utf-8'))
        self.assertIn('resolve-dispatch-running', body)
        self.assertIn('resolve-dispatch-not-started', body)
        self.assertIn('REQUIRE_AI_VIDEO: "1"', body)
        self.assertIn('actions/cache/restore@v4', body)
        self.assertIn('actions/cache/save@v4', body)
        self.assertIn('Quick remote Kaggle status check (minimal CLI only)', body)
        self.assertIn("if: steps.work.outputs.finalize == 'true' && env.POLL_ACTION == 'poll'", body)
        self.assertIn("if: steps.work.outputs.finalize == 'true'", body)
        self.assertIn("if: steps.work.outputs.required == 'true'", body)
        self.assertIn("steps.work.outputs.finalize == 'true'", body)
        self.assertIn('resume-checkpoint', body)
        self.assertIn('requirements-asr.txt', body)
        self.assertIn("steps.tts_cache_changed.outputs.changed == 'true'", body)
        runner = (ROOT / 'scripts' / 'studio_pipeline.py').read_text(encoding='utf-8')
        self.assertIn("'paid_fallback': False", runner)
        self.assertIn("'auto_facebook_publish': False", runner)

if __name__ == '__main__':
    unittest.main(verbosity=2)
