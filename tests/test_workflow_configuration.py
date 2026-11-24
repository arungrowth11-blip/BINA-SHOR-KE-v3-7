from __future__ import annotations
import subprocess
import unittest
import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class WorkflowConfigTests(unittest.TestCase):
    def test_weekly_dispatch_runs_saturday_in_ist(self):
        body = (ROOT / '.github' / 'workflows' / 'weekly-factory.yml').read_text(encoding='utf-8')
        workflow = yaml.load(body, Loader=yaml.BaseLoader)
        push = workflow["on"]["push"]
        self.assertEqual(push["branches"], ["feature/voice-first-3d-foundation"])
        self.assertEqual(
            push["paths"],
            [
                ".github/dispatch/plan-one.once",
                ".github/dispatch/live-tts-smoke.once",
            ],
        )
        self.assertIn('cron: "37 7 * * 6"', body)
        self.assertIn('timezone: "Asia/Kolkata"', body)
        self.assertNotIn('cron: "37 7 * * 0"', body)

    def test_one_shot_plan_one_push_trigger_is_branch_and_path_scoped(self):
        body = (ROOT / '.github' / 'workflows' / 'weekly-factory.yml').read_text(encoding='utf-8')
        self.assertIn('branches:', body)
        self.assertIn('- feature/voice-first-3d-foundation', body)
        self.assertIn('".github/dispatch/plan-one.once"', body)
        self.assertIn("contains(github.event.head_commit.message, 'PLAN_ONE_ONLY')", body)
        self.assertIn("contains(github.event.head_commit.message, 'PLAN_ONE_ONLY')", body)
        self.assertIn('test "$GITHUB_REF" = "refs/heads/feature/voice-first-3d-foundation"', body)
        self.assertIn('git log -1 --format=%B | grep -qx "PLAN_ONE_ONLY_FREE_TIER_CONFIRMED"', body)
        self.assertIn('grep -qx "PLAN_ONE_ONLY" .github/dispatch/plan-one.once', body)
        self.assertIn('grep -qx "FREE_TIER_ONLY_CONFIRMED" .github/dispatch/plan-one.once', body)
        self.assertIn("github.event_name == 'workflow_dispatch' && inputs.mode", body)
        self.assertIn('".github/dispatch/live-tts-smoke.once"', body)
        self.assertIn("contains(github.event.head_commit.message, 'RUN_GEMINI_TTS_SMOKE')", body)
        self.assertIn('git log -1 --format=%B | grep -qx "RUN_GEMINI_TTS_SMOKE"', body)
        self.assertIn("GEMINI_TTS_FREE_TIER_CONFIRMED", body)
        self.assertIn("'live-tts-smoke'", body)
        self.assertIn("contains(github.event.head_commit.message, 'PLAN_ONE_ONLY')", body)
        self.assertIn("'preflight'", body)
        self.assertIn("Consume one-shot live TTS trigger", body)
        self.assertIn("git rm .github/dispatch/live-tts-smoke.once", body)
        self.assertIn("BSK_FREE_TIER_ONLY_ACK:", body)
        self.assertIn("vars.BSK_FREE_TIER_ONLY_CONFIRMED == 'true'", body)
        self.assertIn("PLAN_ONE_ONLY_FREE_TIER_CONFIRMED", body)
        self.assertIn("BSK_FREE_TIER_ONLY_ACK", body)
        self.assertIn("plan-week", body)

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
        self.assertIn('Retry the same Reel after a narrowly classified worker fix', body)
        self.assertIn('refusing to silently skip GPU work', body)
        pipeline = (ROOT / 'scripts' / 'studio_pipeline.py').read_text(encoding='utf-8')
        self.assertIn('def retry_failed_gpu()', pipeline)
        self.assertIn('control_after_generate', pipeline)

    def test_scene5_voiceover_repair_is_guarded_and_does_not_dispatch_gpu(self):
        body = (ROOT / '.github' / 'workflows' / 'poll-gpu.yml').read_text(encoding='utf-8')
        self.assertIn('repair-scene-voiceover', body)
        self.assertIn('scene5_voiceover_repair_ok', body)
        self.assertIn('Replace only Scene 5 Hindi narration and re-finalize the same AI scenes', body)
        self.assertIn('repair-scene-voiceover-finalize', body)
        self.assertIn("[ \"$POLL_ACTION\" = 'repair-scene-voiceover' ]", body)
        pipeline = (ROOT / 'scripts' / 'studio_pipeline.py').read_text(encoding='utf-8')
        self.assertIn('def repair_scene_5_voiceover_finalize()', pipeline)
        self.assertIn('new_kaggle_gpu_dispatch', pipeline)
        self.assertIn('सुमित ने चुपचाप अपनी भीगी कमीज़ निचोड़ दी।', pipeline)

    def test_scene5_voiceover_gate_accepts_actual_generic_qa_message_but_is_strictly_bound(self):
        body = (ROOT / '.github' / 'workflows' / 'poll-gpu.yml').read_text(encoding='utf-8')
        self.assertIn(r'AI scene(?:\s+5)?\s+would require excessive speed change', body)
        self.assertIn('1.66 <= float(scene5_match.group(1)) <= 1.68', body)
        self.assertIn('int(state.get("rhythm_repair_attempts", 0) or 0) == 1', body)
        self.assertIn('scene5_source_matches', body)
        pipeline = (ROOT / 'scripts' / 'studio_pipeline.py').read_text(encoding='utf-8')
        self.assertIn(r"AI scene(?:\s+5)?\s+would require excessive speed change", pipeline)
        self.assertIn("int(pending.get('rhythm_repair_attempts', 0) or 0) != 1", pipeline)
        self.assertIn("'सुमित चुपचाप बालकनी में अपनी भीगी कमीज़ निचोड़ रहा था।'", pipeline)

    def test_kaggle_cli_installs_six_explicitly_for_status_and_repair(self):
        body = (ROOT / '.github' / 'workflows' / 'poll-gpu.yml').read_text(encoding='utf-8')
        expected = '"six>=1.16.0,<2" kaggle'
        self.assertEqual(body.count(expected), 2)
        self.assertIn('Quick remote Kaggle status check (minimal CLI only)', body)
        self.assertIn('Install dependencies and configure private Kaggle CLI', body)
        director = (ROOT / '.github' / 'workflows' / 'weekly-factory.yml').read_text(encoding='utf-8')
        self.assertIn('python -m pip install --disable-pip-version-check --upgrade --no-cache-dir "six>=1.16.0,<2" kaggle', director)
        self.assertIn('Kaggle CLI import preflight passed', director)
        self.assertIn('from kaggle.cli import main', director)

    def test_scene6_voiceover_repair_is_strictly_guarded_and_reuses_existing_scenes(self):
        body = (ROOT / '.github' / 'workflows' / 'poll-gpu.yml').read_text(encoding='utf-8')
        self.assertIn('repair-scene-6-voiceover', body)
        self.assertIn('scene6_voiceover_repair_ok', body)
        self.assertIn('Replace only Scene 6 Hindi narration and re-finalize the same AI scenes', body)
        self.assertIn('repair-scene-6-voiceover-finalize', body)
        self.assertIn('[ "$POLL_ACTION" = \'repair-scene-6-voiceover\' ]', body)
        self.assertIn('1.61 <= float(scene6_match.group(1)) <= 1.63', body)
        self.assertIn('scene6_source_matches', body)
        pipeline = (ROOT / 'scripts' / 'studio_pipeline.py').read_text(encoding='utf-8')
        self.assertIn('def repair_scene_6_voiceover_finalize()', pipeline)
        self.assertIn('उसने सूखी छतरी टाँगी, मगर कमरा चुप रहा।', pipeline)
        self.assertIn("'new_kaggle_gpu_dispatch': False", pipeline)

    def test_scene6_followup_voiceover_repair_is_one_time_and_reuses_existing_scenes(self):
        body = (ROOT / '.github' / 'workflows' / 'poll-gpu.yml').read_text(encoding='utf-8')
        self.assertIn('repair-scene-6-voiceover-followup', body)
        self.assertIn('scene6_followup_ok', body)
        self.assertIn('Shorten only Scene 6 narration once more and re-finalize existing AI scenes', body)
        self.assertIn('repair-scene-6-voiceover-followup-finalize', body)
        self.assertIn("[ \"$POLL_ACTION\" = 'repair-scene-6-voiceover-followup' ]", body)
        self.assertIn('1.53 <= float(scene6_followup_match.group(1)) <= 1.55', body)
        self.assertIn('scene6_voiceover_followup_attempts', body)
        self.assertIn('get("status") in {"qa_rejected_again", "in_progress"}', body)
        pipeline = (ROOT / 'scripts' / 'studio_pipeline.py').read_text(encoding='utf-8')
        self.assertIn('def repair_scene_6_voiceover_followup_finalize()', pipeline)
        self.assertIn('उसने छतरी टाँगी, मगर कमरा चुप रहा।', pipeline)
        self.assertIn("'new_kaggle_gpu_dispatch': False", pipeline)

    def test_finalizer_skips_redundant_apt_installs_and_uses_only_required_fonts(self):
        body = (ROOT / '.github' / 'workflows' / 'poll-gpu.yml').read_text(encoding='utf-8')
        setup = body[body.index('Install only missing FFmpeg and Devanagari prerequisites'):]
        setup = setup[:setup.index('Restore local Hindi narration ASR model cache')]
        self.assertIn('if ! command -v ffmpeg', setup)
        self.assertIn('ffmpeg -filters 2>/dev/null | grep -q subtitles', setup)
        self.assertIn('NotoSansDevanagari-Regular.ttf', setup)
        self.assertIn('NotoSansDevanagari-Bold.ttf', setup)
        self.assertIn('NotoSans-Regular.ttf', setup)
        self.assertIn('NotoSans-Bold.ttf', setup)
        self.assertIn('fonts-noto-core', setup)
        self.assertIn('tesseract-ocr', setup)
        self.assertIn('tesseract-ocr-hin', setup)
        self.assertIn('tesseract --list-langs', setup)
        self.assertIn('grep -qx eng', setup)
        self.assertIn('grep -qx hin', setup)
        self.assertNotIn('fonts-noto-extra', setup)
        self.assertIn('--no-install-recommends', setup)
        self.assertIn('skipping apt update/install', setup)
        self.assertIn('cache: pip', body)
        self.assertIn('cache-dependency-path: |', body)

    def test_offline_quality_gate_installs_hindi_tesseract_for_ocr_checks(self):
        body = (ROOT / '.github' / 'workflows' / 'quality-gates.yml').read_text(encoding='utf-8')
        self.assertIn('ffmpeg tesseract-ocr tesseract-ocr-hin', body)
        self.assertIn('tesseract --list-langs | grep -qx eng', body)
        self.assertIn('tesseract --list-langs | grep -qx hin', body)

    def test_retry_finalize_does_not_reactivate_a_delivered_batch(self):
        body = (ROOT / '.github' / 'workflows' / 'poll-gpu.yml').read_text(encoding='utf-8')
        self.assertIn('retry_states = {"finalize_failed", "finalizing", "gpu_failed"}', body)
        self.assertIn('active = state.get("status") in allowed', body)
        self.assertNotIn('"delivered"', body[body.index('retry_states ='):body.index('qa_reason =')])

    def test_telegram_feedback_sync_runs_independently_of_gpu_batches(self):
        body = (ROOT / '.github' / 'workflows' / 'telegram-feedback-sync.yml').read_text(encoding='utf-8')
        self.assertIn('cron: "17 */6 * * *"', body)
        self.assertIn('timezone: "Asia/Kolkata"', body)
        self.assertIn('TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}', body)
        self.assertIn('scripts/telegram_feedback_sync.py', body)
        self.assertIn('data/telegram_state.json data/history.json data/performance_log.csv', body)
        self.assertIn('group: bina-shor-ke-studio', body)

    def test_kaggle_status_timestamp_is_expanded_by_shell(self):
        body = (ROOT / '.github' / 'workflows' / 'poll-gpu.yml').read_text(encoding='utf-8')
        self.assertIn('echo "status_checked_at_utc=${status_checked_at_utc}" >> "$GITHUB_OUTPUT"', body)
        self.assertIn('echo "KAGGLE_STATUS_CHECKED_AT_UTC=${status_checked_at_utc}"', body)
        self.assertNotIn(r'\${status_checked_at_utc}', body)

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

    def test_queued_feature_dispatch_refreshes_latest_state_before_pending_guard(self):
        body = (ROOT / '.github' / 'workflows' / 'poll-gpu.yml').read_text(encoding='utf-8')
        refresh_name = '      - name: Refresh queued feature-branch dispatch to latest state'
        pending_name = '      - name: Check whether a GPU batch actually needs polling (stdlib only)'
        self.assertIn(refresh_name, body)
        self.assertLess(body.index(refresh_name), body.index(pending_name))
        refresh = body[body.index(refresh_name):body.index(pending_name)]
        self.assertIn("if: github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/feature/voice-first-3d-foundation'", refresh)
        self.assertIn('git fetch --no-tags origin "$GITHUB_REF"', refresh)
        self.assertIn('git reset --hard FETCH_HEAD', refresh)
        self.assertIn('group: bina-shor-ke-studio', body)
        self.assertIn('cancel-in-progress: false', body)
        self.assertIn('retry_states = {"finalize_failed", "finalizing", "gpu_failed"}', body)


    def test_director_installs_only_required_ffmpeg_and_devanagari_fonts(self):
        body = (ROOT / '.github' / 'workflows' / 'weekly-factory.yml').read_text(encoding='utf-8')
        setup = body[body.index('      - name: Install FFmpeg and Devanagari fonts'):body.index('      - name: Install free workflow dependencies')]
        self.assertIn('sudo apt-get install --no-install-recommends -y ffmpeg fonts-noto-core', setup)
        self.assertNotIn('fonts-noto-extra', setup)
        self.assertIn('fc-match "Noto Sans Devanagari"', setup)


    def test_human_review_store_is_encrypted_and_only_ciphertext_is_persisted(self):
        poll = (ROOT / ".github" / "workflows" / "poll-gpu.yml").read_text(encoding="utf-8")
        sync = (ROOT / ".github" / "workflows" / "telegram-feedback-sync.yml").read_text(encoding="utf-8")
        producer = (ROOT / "scripts" / "producer.py").read_text(encoding="utf-8")
        self.assertIn("BSK_HUMAN_REVIEW_ENCRYPTION_KEY: ${{ secrets.BSK_HUMAN_REVIEW_ENCRYPTION_KEY }}", poll)
        self.assertIn("BSK_HUMAN_REVIEW_ENCRYPTION_KEY: ${{ secrets.BSK_HUMAN_REVIEW_ENCRYPTION_KEY }}", sync)
        self.assertIn("cryptography>=42.0.0,<47.0.0", sync)
        self.assertIn("git add data/human_reviews.enc", sync)
        self.assertNotIn("git add data/human_reviews.json", sync)
        self.assertIn('HUMAN_REVIEW_PATH = ROOT / "data" / "human_reviews.enc"', producer)
        self.assertIn("Fernet(human_review_encryption_key()).encrypt", producer)
        self.assertIn("Fernet(human_review_encryption_key()).decrypt", producer)

    def test_gpu_finalizer_prerequisite_shell_block_is_valid_bash(self):
        body = (ROOT / ".github" / "workflows" / "poll-gpu.yml").read_text(encoding="utf-8")
        workflow = yaml.load(body, Loader=yaml.BaseLoader)
        step = next(
            item for item in workflow["jobs"]["finalize"]["steps"]
            if item.get("name") == "Install only missing FFmpeg and Devanagari prerequisites"
        )
        script = step["run"]
        self.assertIn("grep -qx eng", script)
        self.assertIn("grep -qx hin", script)
        result = subprocess.run(
            ["bash", "-n"], input=script, text=True, capture_output=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
