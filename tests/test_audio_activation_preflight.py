from pathlib import Path
import sys
import unittest
from threading import RLock
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from runtime import StageMeshRuntime


class AudioActivationPreflightTests(unittest.TestCase):
    def runtime(self):
        runtime = StageMeshRuntime.__new__(StageMeshRuntime)
        runtime._audio_control_lock = RLock()
        runtime._audio_activation_preflight = {}
        return runtime

    def test_supported_exact_request_is_recorded(self):
        expected = {"status":"constraints-supported", "supported":True, "streamStarted":False}
        with patch("runtime.audio_preflight", return_value=expected) as probe:
            result = self.runtime()._audio_activation_check({"address":"hw:2,1"}, "playback", 96000, 2, 128, 3)
        self.assertIs(result, expected)
        probe.assert_called_once_with({"address":"hw:2,1", "direction":"playback", "format":"FLOAT_LE",
                                       "sampleRate":96000, "channels":2, "periodFrames":128})


    def test_explicit_integer_multichannel_request_is_preflighted_exactly(self):
        expected = {"status":"constraints-supported", "supported":True, "streamStarted":False}
        with patch("runtime.audio_preflight", return_value=expected) as probe:
            self.runtime()._audio_activation_check({"address":"hw:3,0"}, "playback", 48000, 8, 256, 1, "S24_3LE")
        probe.assert_called_once_with({"address":"hw:3,0", "direction":"playback", "format":"S24_3LE",
                                       "sampleRate":48000, "channels":8, "periodFrames":256})

    def test_unknown_and_unsupported_block_before_activation(self):
        for supported, status in ((None,"busy"),(False,"constraints-unsupported")):
            runtime = self.runtime()
            with self.subTest(status=status), patch("runtime.audio_preflight", return_value={"supported":supported,"status":status}), self.assertRaisesRegex(RuntimeError,status):
                runtime._audio_activation_check({"address":"hw:0,0"}, "capture", 48000, 1, 64, 0)
            self.assertEqual(runtime._audio_activation_preflight[("input",0)]["status"], status)

    def test_plugin_endpoint_cannot_bypass_exact_preflight(self):
        runtime = self.runtime()
        with self.assertRaisesRegex(RuntimeError, "numeric ALSA"):
            runtime._audio_activation_check({"address":"default"}, "playback", 48000, 2, 256, 0)
        self.assertEqual(runtime._audio_activation_preflight, {})
