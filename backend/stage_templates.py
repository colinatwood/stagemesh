"""Versioned, fail-closed stage-template storage for the operator UI."""
from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
from threading import RLock
from time import time
from uuid import uuid4


class StageTemplateConflict(RuntimeError):
    """A template changed since the caller last read it."""


class StageTemplateStoreCorrupt(RuntimeError):
    """The persisted template store cannot be trusted or safely replaced."""


class StageTemplateStore:
    def __init__(self, path: Path):
        self.path, self._lock = path, RLock()
        self._templates = self._load()

    def _load(self):
        temporary = self.path.with_suffix(".tmp")
        if temporary.exists():
            raise StageTemplateStoreCorrupt(
                "stage template store has an incomplete temporary write"
            )
        try:
            serialized = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        except (OSError, UnicodeDecodeError) as exc:
            raise StageTemplateStoreCorrupt(
                "stage template store is unreadable or malformed"
            ) from exc
        try:
            data = json.loads(serialized)
        except json.JSONDecodeError as exc:
            raise StageTemplateStoreCorrupt(
                "stage template store is unreadable or malformed"
            ) from exc
        self._validate_loaded(data)
        return data

    @staticmethod
    def _validate_loaded(data):
        if not isinstance(data, dict):
            raise StageTemplateStoreCorrupt(
                "stage template store is unreadable or malformed"
            )
        for template_id, document in data.items():
            if not isinstance(template_id, str) or not template_id:
                raise StageTemplateStoreCorrupt(
                    "stage template store is unreadable or malformed"
                )
            if not isinstance(document, dict):
                raise StageTemplateStoreCorrupt(
                    "stage template store is unreadable or malformed"
                )
            revision = document.get("revision")
            updated_at = document.get("updatedAt")
            objects = document.get("objects")
            if (
                document.get("version") != 1
                or not isinstance(document.get("name"), str)
                or not document["name"]
                or type(revision) is not int
                or revision < 1
                or document.get("state") not in {"draft", "published"}
                or isinstance(updated_at, bool)
                or not isinstance(updated_at, (int, float))
                or not math.isfinite(updated_at)
                or not isinstance(objects, list)
                or len(objects) > 5000
            ):
                raise StageTemplateStoreCorrupt(
                    "stage template store is unreadable or malformed"
                )
            object_ids = set()
            for item in objects:
                x = item.get("x") if isinstance(item, dict) else None
                y = item.get("y") if isinstance(item, dict) else None
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("id"), str)
                    or not item["id"]
                    or item["id"] in object_ids
                    or not isinstance(item.get("type"), str)
                    or not item["type"]
                    or len(item["type"]) > 32
                    or not isinstance(item.get("label"), str)
                    or not item["label"].strip()
                    or len(item["label"]) > 128
                    or isinstance(x, bool)
                    or not isinstance(x, (int, float))
                    or not math.isfinite(x)
                    or not 0 <= x <= 100
                    or isinstance(y, bool)
                    or not isinstance(y, (int, float))
                    or not math.isfinite(y)
                    or not 0 <= y <= 100
                ):
                    raise StageTemplateStoreCorrupt(
                        "stage template store is unreadable or malformed"
                    )
                object_ids.add(item["id"])

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._templates, sort_keys=True, indent=2))
        tmp.replace(self.path)

    @staticmethod
    def validate(document):
        if not isinstance(document, dict): raise ValueError("template must be an object")
        objects = document.get("objects", [])
        if not isinstance(objects, list) or len(objects) > 5000: raise ValueError("objects must be a bounded array")
        normalized = []
        object_ids = set()
        for item in objects:
            if not isinstance(item, dict) or not str(item.get("label", "")).strip(): raise ValueError("each object needs a label")
            x, y = float(item.get("x", 50)), float(item.get("y", 50))
            if not 0 <= x <= 100 or not 0 <= y <= 100: raise ValueError("object coordinates must be 0..100")
            object_id = str(item.get("id") or uuid4())
            if object_id in object_ids: raise ValueError("object IDs must be unique within a template")
            object_ids.add(object_id)
            normalized.append({"id": object_id, "type": str(item.get("type") or "marker")[:32], "label": str(item["label"])[:128], "x": x, "y": y})
        return {"version": 1, "name": str(document.get("name") or "Untitled stage template")[:128], "objects": normalized}

    def list(self):
        with self._lock: return [{"templateId": key, **deepcopy(value)} for key, value in self._templates.items()]

    def get(self, template_id):
        with self._lock:
            if template_id not in self._templates: raise KeyError(template_id)
            return {"templateId": template_id, **deepcopy(self._templates[template_id])}

    def create(self, document):
        normalized = self.validate(document); template_id = str(uuid4())
        with self._lock:
            self._templates[template_id] = {**normalized, "revision": 1, "state": "draft", "updatedAt": time()}
            try:
                self._save()
            except OSError:
                self._templates.pop(template_id, None)
                raise
            return self.get(template_id)

    def update(self, template_id, expected_revision, document):
        normalized = self.validate(document)
        with self._lock:
            current = self._templates.get(template_id)
            if current is None:
                raise KeyError(template_id)
            if expected_revision != current["revision"]:
                raise StageTemplateConflict(
                    f"template revision conflict: expected {expected_revision}, current {current['revision']}"
                )
            previous = deepcopy(current)
            self._templates[template_id] = {
                **normalized, "revision": current["revision"] + 1,
                "state": "draft", "updatedAt": time(),
            }
            try:
                self._save()
            except OSError:
                self._templates[template_id] = previous
                raise
            return self.get(template_id)

    def delete(self, template_id, expected_revision):
        with self._lock:
            current = self._templates.get(template_id)
            if current is None:
                raise KeyError(template_id)
            if expected_revision != current["revision"]:
                raise StageTemplateConflict(
                    f"template revision conflict: expected {expected_revision}, current {current['revision']}"
                )
            previous = self._templates.pop(template_id)
            try:
                self._save()
            except OSError:
                self._templates[template_id] = previous
                raise
            return {"deleted": True, "templateId": template_id, "physicalOutputsArmed": False}

    def validate_saved(self, template_id):
        item = self.get(template_id); self.validate(item)
        return {"valid": True, "templateId": template_id, "objectCount": len(item["objects"]), "physicalOutputsArmed": False}

    def publish(self, template_id):
        result = self.validate_saved(template_id)
        with self._lock:
            previous = deepcopy(self._templates[template_id])
            self._templates[template_id]["state"] = "published"
            self._templates[template_id]["revision"] += 1
            self._templates[template_id]["updatedAt"] = time()
            try:
                self._save()
            except OSError:
                self._templates[template_id] = previous
                raise
            return {**result, "state": "published", "revision": self._templates[template_id]["revision"], "physicalOutputsArmed": False}
