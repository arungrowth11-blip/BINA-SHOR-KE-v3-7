from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bsk.errors import StateError

STAGES = [
    "created",
    "story_drafted",
    "story_approved",
    "voice_generated",
    "voice_approved",
    "audio_aligned",
    "alignment_approved",
    "storyboard_created",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise


class JobStore:
    def __init__(self, jobs_dir: Path):
        self.jobs_dir = Path(jobs_dir)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def job_dir(self, job_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,79}", job_id):
            raise StateError("Invalid job ID; use 2–80 letters, numbers, dots, underscores or hyphens.")
        return self.jobs_dir / job_id

    def create(self, job_id: str, brief: dict[str, Any]) -> Path:
        directory = self.job_dir(job_id)
        if directory.exists():
            raise StateError(f"Job already exists: {job_id}")
        directory.mkdir(parents=True)
        atomic_json(directory / "brief.json", brief)
        state = {
            "schema_version": 1,
            "job_id": job_id,
            "stage": "created",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "artifacts": {},
            "approvals": {},
            "events": [{"stage": "created", "at_utc": datetime.now(timezone.utc).isoformat()}],
        }
        atomic_json(directory / "state.json", state)
        return directory

    def read(self, job_id: str) -> dict[str, Any]:
        path = self.job_dir(job_id) / "state.json"
        if not path.exists():
            raise StateError(f"Unknown job: {job_id}")
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("schema_version") != 1:
            raise StateError("Unsupported job-state schema; refusing unsafe migration.")
        return state

    def save(self, job_id: str, state: dict[str, Any]) -> None:
        state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        atomic_json(self.job_dir(job_id) / "state.json", state)

    def require_stage(self, job_id: str, expected: str) -> dict[str, Any]:
        state = self.read(job_id)
        if state.get("stage") != expected:
            raise StateError(f"Job is at '{state.get('stage')}', but this command requires '{expected}'.")
        return state

    def transition(self, job_id: str, expected: str, new_stage: str, note: str | None = None) -> dict[str, Any]:
        if expected not in STAGES or new_stage not in STAGES or STAGES.index(new_stage) != STAGES.index(expected) + 1:
            raise StateError(f"Invalid stage transition: {expected} -> {new_stage}")
        state = self.require_stage(job_id, expected)
        state["stage"] = new_stage
        event = {"stage": new_stage, "at_utc": datetime.now(timezone.utc).isoformat()}
        if note:
            event["note"] = note[:1000]
        state.setdefault("events", []).append(event)
        self.save(job_id, state)
        return state

    def add_artifact(self, job_id: str, key: str, artifact_path: Path) -> dict[str, Any]:
        directory = self.job_dir(job_id)
        path = Path(artifact_path).resolve()
        if directory.resolve() not in path.parents:
            raise StateError("Artifact must be stored inside its own job directory.")
        if not path.is_file():
            raise StateError(f"Artifact does not exist: {path}")
        state = self.read(job_id)
        relative = path.relative_to(directory.resolve()).as_posix()
        state.setdefault("artifacts", {})[key] = {
            "path": relative,
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        self.save(job_id, state)
        return state

    def artifact_path(self, job_id: str, key: str, verify: bool = True) -> Path:
        state = self.read(job_id)
        item = state.get("artifacts", {}).get(key)
        if not isinstance(item, dict):
            raise StateError(f"Job artifact not found: {key}")
        path = (self.job_dir(job_id) / item["path"]).resolve()
        if self.job_dir(job_id).resolve() not in path.parents or not path.is_file():
            raise StateError(f"Artifact is missing or has an unsafe path: {key}")
        if verify and sha256_file(path) != item.get("sha256"):
            raise StateError(f"Artifact checksum mismatch: {key}")
        return path
