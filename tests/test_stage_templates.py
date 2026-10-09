import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from stage_templates import (
    StageTemplateConflict,
    StageTemplateStore,
    StageTemplateStoreCorrupt,
)


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

    def test_duplicate_object_ids_reject_create_and_update_without_mutation(self):
        created = self.store.create(self.document())
        before = self.path.read_bytes()
        duplicate = {"name": "Ambiguous", "objects": [
            {"id": "same", "label": "Lead", "x": 20, "y": 30},
            {"id": "same", "label": "Drums", "x": 70, "y": 40},
        ]}
        with self.assertRaisesRegex(ValueError, "object IDs must be unique"):
            self.store.create(duplicate)
        with self.assertRaisesRegex(ValueError, "object IDs must be unique"):
            self.store.update(created["templateId"], 1, duplicate)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.store.get(created["templateId"]), created)
        self.assertEqual(len(self.store.list()), 1)

    def test_duplicate_persisted_object_ids_fail_closed_and_preserve_source(self):
        created = self.store.create(self.document())
        saved = json.loads(self.path.read_text())
        first = saved[created["templateId"]]["objects"][0]
        saved[created["templateId"]]["objects"].append({**first, "label": "Other component"})
        self.path.write_text(json.dumps(saved))
        before = self.path.read_bytes()
        with self.assertRaises(StageTemplateStoreCorrupt):
            StageTemplateStore(self.path)
        self.assertEqual(self.path.read_bytes(), before)

    def test_object_ids_are_unique_per_template_and_missing_ids_are_generated(self):
        document = {"name": "Distinct", "objects": [{"label": "Lead"}, {"label": "Drums"}]}
        first = self.store.create(document)
        self.assertEqual(len({item["id"] for item in first["objects"]}), 2)
        second = self.store.create({"name": "Other", "objects": first["objects"]})
        self.assertEqual(second["objects"], first["objects"])

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

    def test_malformed_store_fails_closed_without_changing_source(self):
        malformed = b'{"template":'
        self.path.write_bytes(malformed)
        with self.assertRaisesRegex(
            StageTemplateStoreCorrupt,
            "stage template store is unreadable or malformed",
        ):
            StageTemplateStore(self.path)
        self.assertEqual(self.path.read_bytes(), malformed)

    def test_invalid_persisted_schema_fails_closed(self):
        invalid_documents = (
            [],
            {"template": {"version": 1}},
            {
                "template": {
                    "version": 2,
                    "name": "Future",
                    "objects": [],
                    "revision": 1,
                    "state": "draft",
                    "updatedAt": 1.0,
                }
            },
        )
        for document in invalid_documents:
            with self.subTest(document=document):
                self.path.write_text(json.dumps(document), encoding="utf-8")
                with self.assertRaises(StageTemplateStoreCorrupt):
                    StageTemplateStore(self.path)

    def test_incomplete_temporary_write_fails_closed_and_is_preserved(self):
        self.store.create(self.document())
        temporary = self.path.with_suffix(".tmp")
        temporary.write_bytes(b"incomplete replacement")
        with self.assertRaisesRegex(
            StageTemplateStoreCorrupt,
            "stage template store has an incomplete temporary write",
        ):
            StageTemplateStore(self.path)
        self.assertEqual(temporary.read_bytes(), b"incomplete replacement")


if __name__ == "__main__":
    unittest.main()
