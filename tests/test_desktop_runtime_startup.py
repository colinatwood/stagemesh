import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import dev_server


class DesktopRuntimeStartupTests(unittest.TestCase):
    def test_bind_failure_closes_runtime_and_native_child(self):
        arguments = ["dev_server.py", "--host", "127.0.0.1", "--port", "48123"]
        with (
            patch.object(sys, "argv", arguments),
            patch.object(
                dev_server,
                "StageMeshHTTPServer",
                side_effect=OSError("address already in use"),
            ),
            patch.object(dev_server.RUNTIME, "close") as close_runtime,
        ):
            with self.assertRaisesRegex(OSError, "address already in use"):
                dev_server.main()
        close_runtime.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
