import unittest
from pathlib import Path
import yaml


class WorkflowSafetyTests(unittest.TestCase):
    def test_v4_workflow_has_no_schedule_or_secrets(self):
        path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "quality-gates.yml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        triggers = data.get("on", data.get(True, {}))
        self.assertNotIn("schedule", triggers)
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("KAGGLE_KEY", text)
        self.assertNotIn("GEMINI_API_KEY", text)
        self.assertEqual(data["permissions"]["contents"], "read")


if __name__ == "__main__":
    unittest.main()
