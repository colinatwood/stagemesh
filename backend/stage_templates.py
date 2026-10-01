"""Versioned, fail-closed stage-template storage for the operator UI."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from threading import RLock
from time import time
from uuid import uuid4


class StageTemplateStore:
    def __init__(self, path: Path):
        self.path, self._lock = path, RLock()
        self._templates = self._load()

    def _load(self):
        try:
            data = json.loads(self.path.read_text())
            return data if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

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
        for item in objects:
            if not isinstance(item, dict) or not str(item.get("label", "")).strip(): raise ValueError("each object needs a label")
            x, y = float(item.get("x", 50)), float(item.get("y", 50))
            if not 0 <= x <= 100 or not 0 <= y <= 100: raise ValueError("object coordinates must be 0..100")
            normalized.append({"id": str(item.get("id") or uuid4()), "type": str(item.get("type") or "marker")[:32], "label": str(item["label"])[:128], "x": x, "y": y})
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
            self._save()
            return self.get(template_id)

    def validate_saved(self, template_id):
        item = self.get(template_id); self.validate(item)
        return {"valid": True, "templateId": template_id, "objectCount": len(item["objects"]), "physicalOutputsArmed": False}

    def publish(self, template_id):
        result = self.validate_saved(template_id)
        with self._lock:
            self._templates[template_id]["state"] = "published"; self._templates[template_id]["revision"] += 1; self._templates[template_id]["updatedAt"] = time(); self._save()
            return {**result, "state": "published", "revision": self._templates[template_id]["revision"], "physicalOutputsArmed": False}
