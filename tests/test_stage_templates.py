import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from stage_templates import StageTemplateConflict, StageTemplateStore


class StageTemplateStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "templates.json"
        self.store = StageTemplateStore(self.path)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def document(name="Tour"):
        return {"name": name, "objects": [{"label": "Lead vocal", "x": 50, "y": 42}]}

    def test_update_is_revision_checked_persistent_and_unpublishes(self):
        created = self.store.create(self.document())
        published = self.store.publish(created["templateId"])
        self.assertEqual(published["revision"], 2)
        updated = self.store.update(created["templateId"], 2, self.document("Festival"))
        self.assertEqual(updated["revision"], 3)
        self.assertEqual(updated["state"], "draft")
        self.assertEqual(updated["name"], "Festival")
        restored = StageTemplateStore(self.path).get(created["templateId"])
        self.assertEqual(restored, updated)

    def test_stale_update_and_delete_leave_record_unchanged(self):
        created = self.store.create(self.document())
        with self.assertRaises(StageTemplateConflict):
            self.store.update(created["templateId"], 9, self.document("Stale"))
        with self.assertRaises(StageTemplateConflict):
            self.store.delete(created["templateId"], 9)
        self.assertEqual(self.store.get(created["templateId"]), created)

    def test_delete_requires_current_revision_and_persists(self):
        created = self.store.create(self.document())
        result = self.store.delete(created["templateId"], 1)
        self.assertTrue(result["deleted"])
        self.assertFalse(result["physicalOutputsArmed"])
        with self.assertRaises(KeyError):
            StageTemplateStore(self.path).get(created["templateId"])

    def test_invalid_and_oversized_templates_are_rejected(self):
        with self.assertRaises(ValueError):
            self.store.create({"objects": [{"x": 50, "y": 50}]})
        with self.assertRaises(ValueError):
            self.store.create({"objects": [{"label": "bad", "x": 101, "y": 50}]})
        with self.assertRaises(ValueError):
            self.store.create({"objects": [{}] * 5001})

    def test_failed_create_and_publish_roll_back_memory(self):
        with patch.object(self.store, "_save", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.store.create(self.document())
        self.assertEqual(self.store.list(), [])
        created = self.store.create(self.document())
        with patch.object(self.store, "_save", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.store.publish(created["templateId"])
        self.assertEqual(self.store.get(created["templateId"]), created)

    def test_failed_persistence_rolls_back_update_and_delete(self):
        created = self.store.create(self.document())
        with patch.object(self.store, "_save", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.store.update(created["templateId"], 1, self.document("Unsaved"))
            self.assertEqual(self.store.get(created["templateId"]), created)
            with self.assertRaises(OSError):
                self.store.delete(created["templateId"], 1)
            self.assertEqual(self.store.get(created["templateId"]), created)


if __name__ == "__main__":
    unittest.main()
