from __future__ import annotations
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("telegram_feedback_sync", ROOT / "scripts" / "telegram_feedback_sync.py")
sync = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sync
spec.loader.exec_module(sync)


class TelegramFeedbackSyncTests(unittest.TestCase):
    def test_skips_cleanly_without_bot_token(self):
        with patch.object(sync.producer, "TELEGRAM_BOT_TOKEN", ""), patch.object(sync.producer, "process_telegram_feedback") as process:
            self.assertEqual(sync.main(), 0)
            process.assert_not_called()

    def test_skips_until_private_owner_chat_is_enrolled(self):
        with patch.object(sync.producer, "TELEGRAM_BOT_TOKEN", "token"), patch.object(sync.producer, "load_telegram_state", return_value={"owner_chat_id": None}), patch.object(sync.producer, "process_telegram_feedback") as process:
            self.assertEqual(sync.main(), 0)
            process.assert_not_called()

    def test_drains_feedback_after_owner_is_enrolled(self):
        states = iter([{"owner_chat_id": "private-owner", "last_update_id": 10}, {"owner_chat_id": "private-owner", "last_update_id": 12}])
        with patch.object(sync.producer, "TELEGRAM_BOT_TOKEN", "token"), patch.object(sync.producer, "load_telegram_state", side_effect=lambda: next(states)), patch.object(sync.producer, "load_history", return_value={"topics": [], "performance": []}), patch.object(sync.producer, "process_telegram_feedback", return_value=1) as process:
            self.assertEqual(sync.main(), 0)
            process.assert_called_once()


if __name__ == "__main__":
    unittest.main()
