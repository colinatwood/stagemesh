import importlib.util
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("browser_qualification",ROOT/"scripts/stagemesh-browser-qualification.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
analyze_accessibility_tree=module.analyze_accessibility_tree


def node(role,name="",*,ignored=False,**props):
    return {"role":{"value":role},"name":{"value":name},"ignored":ignored,"properties":[{"name":key,"value":{"value":value}} for key,value in props.items()]}


class BrowserAccessibilityTests(unittest.TestCase):
    def valid_tree(self):
        return [
            node("main"),node("link","Skip to stage controls",focusable=True),
            node("button","Play or pause",focusable=True),node("button","Stop",focusable=True),
            node("spinbutton","BPM ",focusable=True,valuemin=30,valuemax=300),
            node("combobox","Key ",focusable=True),
            node("button","Drums Alex",focusable=True),node("button","Bass Sam",focusable=True),
            node("button","Keys Maya",focusable=True),node("button","Lead Vocal Jordan",focusable=True),
            node("status",live="polite"),node("status",live="polite"),node("status",live="polite"),
        ]

    def test_reference_tree_contract_passes_named_focusable_controls(self):
        result=analyze_accessibility_tree(self.valid_tree())
        self.assertTrue(result["passed"]);self.assertEqual(result["failures"],[])
        self.assertGreaterEqual(result["interactiveNodeCount"],8);self.assertEqual(result["liveRegionCount"],3)

    def test_unnamed_interactive_and_ignored_focusable_nodes_fail(self):
        tree=self.valid_tree()+[node("button","",focusable=True),node("link","hidden",ignored=True,focusable=True)]
        result=analyze_accessibility_tree(tree)
        self.assertFalse(result["passed"])
        self.assertIn("namedInteractiveControls",result["failures"])
        self.assertIn("noIgnoredFocusableNodes",result["failures"])

class BrowserProductionAssetsTests(unittest.TestCase):
    def test_workspace_and_all_declared_dependencies_are_loaded_in_order(self):
        html, scripts = module._production_assets()
        self.assertIn('id="audioReconnectStatus"', html)
        self.assertIn('id="templateCanvas"', html)
        self.assertNotIn("<script", html)
        self.assertNotIn('href="/styles.css"', html)
        names = [name for name, _ in scripts]
        self.assertLess(names.index("input-recovery.js"), names.index("app.js"))
        self.assertIn("stage-template.js", names)
        self.assertTrue(all(source for _, source in scripts))

    def test_added_script_is_discovered_without_a_second_asset_list(self):
        with tempfile.TemporaryDirectory() as temporary:
            frontend = Path(temporary)
            (frontend / "index.html").write_text("public download page")
            (frontend / "app.html").write_text(
                '<main>Operator workspace</main><script defer src="/new-module.js"></script>'
                "<script src='/app.js'></script>"
            )
            (frontend / "new-module.js").write_text("dependency")
            (frontend / "app.js").write_text("application")
            with patch.object(module, "FRONTEND", frontend):
                html, scripts = module._production_assets()
            self.assertEqual(html, "<main>Operator workspace</main>")
            self.assertEqual(scripts, [("new-module.js", "dependency"), ("app.js", "application")])

    def test_missing_or_nonlocal_dependency_refuses_partial_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            frontend = Path(temporary)
            with patch.object(module, "FRONTEND", frontend):
                for source in ("https://example.invalid/app.js", "/../outside.js"):
                    (frontend / "app.html").write_text(f'<script src="{source}"></script>')
                    with self.assertRaises(ValueError):
                        module._production_assets()
                (frontend / "app.html").write_text('<script src="/missing.js"></script>')
                with self.assertRaises(FileNotFoundError):
                    module._production_assets()


if __name__=="__main__":unittest.main()
