import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "desktop-windows-channel.py"


def load_script():
    spec = importlib.util.spec_from_file_location("desktop_windows_channel", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DesktopWindowsChannelTests(unittest.TestCase):
    def fixture(self, root: Path) -> Path:
        target = root / "desktop" / "src-tauri" / "tauri.conf.json"
        target.parent.mkdir(parents=True)
        shutil.copy2(ROOT / "desktop" / "src-tauri" / "tauri.conf.json", target)
        return target

    def test_configures_each_supported_channel_deterministically(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self.fixture(root)
            script = load_script()
            self.assertEqual(script.configure(root, "online"), "downloadBootstrapper")
            online = config.read_bytes()
            self.assertEqual(
                json.loads(online)["bundle"]["windows"]["webviewInstallMode"]["type"],
                "downloadBootstrapper",
            )
            self.assertEqual(script.configure(root, "online"), "downloadBootstrapper")
            self.assertEqual(config.read_bytes(), online)
            self.assertEqual(script.configure(root, "offline"), "offlineInstaller")

    def test_rejects_unknown_channels_and_ambiguous_mode_objects(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self.fixture(root)
            script = load_script()
            with self.assertRaisesRegex(ValueError, "online or offline"):
                script.configure(root, "skip")
            document = json.loads(config.read_text(encoding="utf-8"))
            document["bundle"]["windows"]["webviewInstallMode"]["path"] = "unexpected"
            config.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exactly the type field"):
                script.configure(root, "online")


if __name__ == "__main__":
    unittest.main()
