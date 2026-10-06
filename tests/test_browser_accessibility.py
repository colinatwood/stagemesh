import importlib.util
from pathlib import Path
import unittest

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

if __name__=="__main__":unittest.main()
