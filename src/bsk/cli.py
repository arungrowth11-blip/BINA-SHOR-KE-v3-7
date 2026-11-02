from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bsk.config import settings
from bsk.errors import BSKError
from bsk.pipeline import service
from bsk.pipeline.state import JobStore


def _store() -> JobStore:
    return JobStore(settings.jobs_dir)


def _print(payload: object) -> None:
    if isinstance(payload, (dict, list)):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload)


def cmd_doctor(_: argparse.Namespace) -> int:
    providers = settings.configured_text_providers
    print("BINA SHOR KE v4 — local environment check")
    print(f"Project root: {settings.jobs_dir.parent.parent}")
    print(f"Gemini text model: {settings.gemini_text_model} ({'configured' if settings.gemini_api_key else 'key missing'})")
    print(f"Gemini TTS model: {settings.gemini_tts_model} ({'configured' if settings.gemini_api_key else 'key missing'})")
    print(f"Configured text providers: {', '.join(providers) if providers else 'none'}")
    print(f"Free-only confirmation: {'confirmed by local setting' if settings.confirm_free_only else 'NOT CONFIRMED'}")
    print(f"Mistral route: {'explicitly enabled' if settings.enable_mistral_free_only else 'disabled by default'}")
    print(f"Independent critic: {'ready' if len(providers) >= 2 else 'not ready — configure Groq Free or verified Mistral Free'}")
    print("GPU / Kaggle: not used by v4 foundation")
    print("Network/API calls: none during doctor")
    if "gemini" not in providers:
        return 2
    if len(providers) < 2:
        return 3
    if not settings.confirm_free_only:
        return 4
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bsk",
        description="BINA SHOR KE v4 — audio-first Hindi Reel production stages",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser("doctor", help="Check local configuration; no API calls")
    doctor.set_defaults(func=cmd_doctor)

    new_job = commands.add_parser("new-job", help="Create a clean job from a JSON production brief")
    new_job.add_argument("--brief", required=True, type=Path)
    new_job.add_argument("--job-id")
    new_job.set_defaults(func=lambda args: (print(service.create_job(args.brief, args.job_id)) or 0))

    draft = commands.add_parser("draft-story", help="Write a complete story and obtain an independent critique")
    draft.add_argument("--job-id", required=True)
    draft.set_defaults(func=lambda args: (_print(service.draft_story(args.job_id)) or 0))

    approve_story = commands.add_parser("approve-story", help="Human approval after reading the complete script")
    approve_story.add_argument("--job-id", required=True)
    approve_story.add_argument("--note", required=True)
    approve_story.set_defaults(func=lambda args: (service.approve_story(args.job_id, args.note), print("Story approved."), 0)[-1])

    voice = commands.add_parser("generate-voice", help="Generate one complete Hindi narration WAV")
    voice.add_argument("--job-id", required=True)
    voice.set_defaults(func=lambda args: (_print(service.generate_voice(args.job_id)) or 0))

    approve_voice = commands.add_parser("approve-voice", help="Human approval after listening to the complete WAV")
    approve_voice.add_argument("--job-id", required=True)
    approve_voice.add_argument("--note", required=True)
    approve_voice.set_defaults(func=lambda args: (service.approve_voice(args.job_id, args.note), print("Voice approved."), 0)[-1])

    align = commands.add_parser("align-audio", help="Run optional local CPU Whisper alignment")
    align.add_argument("--job-id", required=True)
    align.set_defaults(func=lambda args: (_print(service.align_audio(args.job_id)) or 0))

    approve_alignment = commands.add_parser("approve-alignment", help="Approve transcript/timing after human inspection")
    approve_alignment.add_argument("--job-id", required=True)
    approve_alignment.add_argument("--note", required=True)
    approve_alignment.set_defaults(func=lambda args: (service.approve_alignment(args.job_id, args.note), print("Alignment approved."), 0)[-1])

    storyboard = commands.add_parser("build-storyboard", help="Create a variable-length storyboard timed to the approved WAV")
    storyboard.add_argument("--job-id", required=True)
    storyboard.set_defaults(func=lambda args: (_print(service.create_storyboard(args.job_id)) or 0))

    status = commands.add_parser("status", help="Show a job's current stage and checksummed artifacts")
    status.add_argument("--job-id", required=True)
    def show_status(args: argparse.Namespace) -> int:
        state = _store().read(args.job_id)
        _print({"job_id": state["job_id"], "stage": state["stage"],
                "approvals": state.get("approvals", {}), "artifacts": state.get("artifacts", {})})
        return 0
    status.set_defaults(func=show_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except BSKError as exc:
        print(f"STOPPED SAFELY: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted. Existing stage artifacts and job state were not intentionally deleted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
