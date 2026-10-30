#!/usr/bin/env python3
"""Lightweight scheduled sync for the pinned private Telegram owner chat.

Telegram only retains pending updates for a limited time. This entry point drains
owner commands frequently even when no GPU batch is running, then persists the
updated owner cursor, publication log, approvals and performance metrics.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import producer  # noqa: E402


def main() -> int:
    if not producer.TELEGRAM_BOT_TOKEN:
        print("Telegram feedback sync skipped: TELEGRAM_BOT_TOKEN is not configured.")
        return 0

    state = producer.load_telegram_state()
    if not state.get("owner_chat_id"):
        print("Telegram feedback sync skipped: owner chat is not enrolled yet. Run plan-one after sending /start to your bot.")
        return 0

    history = producer.load_history()
    previous_cursor = int(state.get("last_update_id", 0))
    accepted = producer.process_telegram_feedback(history)
    updated_state = producer.load_telegram_state()
    new_cursor = int(updated_state.get("last_update_id", previous_cursor))
    print(
        "Telegram feedback sync complete: "
        f"cursor {previous_cursor} -> {new_cursor}; "
        f"new insights saved={accepted}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
