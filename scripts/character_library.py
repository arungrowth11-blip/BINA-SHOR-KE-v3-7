#!/usr/bin/env python3
"""Manage persistent BINA SHOR KE character metadata (asset files live outside Git)."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import voice_first

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "data" / "characters" / "registry.json"


def load_registry(path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "characters": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("characters"), list):
        raise ValueError(f"Invalid character registry schema: {path}")
    seen = set()
    for character in data["characters"]:
        record = voice_first.registry_character_record(character)
        if record["character_id"] in seen:
            raise ValueError(f"Duplicate character in registry: {record['character_id']}")
        seen.add(record["character_id"])
    return data


def save_registry(data: dict[str, Any], path: Path = DEFAULT_REGISTRY) -> None:
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("characters"), list):
        raise ValueError("Character registry must have schema_version=1 and a characters list.")
    seen = set()
    clean = []
    for character in data["characters"]:
        record = voice_first.registry_character_record(character)
        if record["character_id"] in seen:
            raise ValueError(f"Duplicate character in registry: {record['character_id']}")
        seen.add(record["character_id"])
        # Preserve non-schema metadata such as first/last used and rights review.
        record.update({k: v for k, v in character.items() if k not in record})
        clean.append(record)
    output = {"schema_version": 1, "characters": clean}
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(output, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def upsert_character(character: dict[str, Any], path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    record = voice_first.registry_character_record(character)
    registry = load_registry(path)
    existing = {item["character_id"]: index for index, item in enumerate(registry["characters"])}
    if record["character_id"] in existing:
        old = registry["characters"][existing[record["character_id"]]]
        old.update(record)
    else:
        registry["characters"].append(record)
    save_registry(registry, path)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("list", "register"))
    parser.add_argument("--input", help="JSON file containing one character object (register only).")
    args = parser.parse_args()
    if args.command == "list":
        print(json.dumps(load_registry(), ensure_ascii=False, indent=2))
        return 0
    if not args.input:
        parser.error("register requires --input")
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    print(json.dumps(upsert_character(payload), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
