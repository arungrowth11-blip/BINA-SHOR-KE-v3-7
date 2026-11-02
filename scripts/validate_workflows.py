from pathlib import Path
import yaml

root = Path(__file__).resolve().parents[1]
workflow_dir = root / ".github" / "workflows"
paths = sorted(workflow_dir.glob("*.yml"))
if not paths:
    raise SystemExit("No GitHub Actions workflow found.")
for path in paths:
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(content, dict):
        raise SystemExit(f"Invalid workflow structure: {path}")
    triggers = content.get("on", content.get(True, {}))
    if "schedule" in (triggers or {}):
        raise SystemExit(f"Scheduled runs are prohibited in v4 foundation: {path}")
    print(f"YAML OK: {path.relative_to(root)}")
