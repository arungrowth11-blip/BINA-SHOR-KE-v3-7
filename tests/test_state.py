import tempfile
import unittest
from pathlib import Path

from bsk.errors import StateError
from bsk.pipeline.state import JobStore


class JobStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = JobStore(Path(self.temp.name))
        self.job = self.store.create("test_job_001", {"topic": "test"})

    def tearDown(self):
        self.temp.cleanup()

    def test_sequential_transition(self):
        self.store.transition("test_job_001", "created", "story_drafted", "unit test")
        state = self.store.read("test_job_001")
        self.assertEqual(state["stage"], "story_drafted")

    def test_out_of_order_transition_fails(self):
        with self.assertRaises(StateError):
            self.store.transition("test_job_001", "created", "voice_generated")

    def test_artifact_checksum_detects_modification(self):
        path = self.job / "note.txt"
        path.write_text("original", encoding="utf-8")
        self.store.add_artifact("test_job_001", "note", path)
        self.assertEqual(self.store.artifact_path("test_job_001", "note").read_text(), "original")
        path.write_text("tampered", encoding="utf-8")
        with self.assertRaises(StateError):
            self.store.artifact_path("test_job_001", "note")

    def test_job_id_path_traversal_is_rejected(self):
        with self.assertRaises(StateError):
            self.store.job_dir("../other")


if __name__ == "__main__":
    unittest.main()
