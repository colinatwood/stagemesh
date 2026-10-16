from pathlib import Path
from threading import RLock
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from runtime import StageMeshRuntime


class AudioRecoveryTests(unittest.TestCase):
    def runtime(self):
        runtime=StageMeshRuntime.__new__(StageMeshRuntime);runtime._audio_control_lock=RLock();return runtime

    def test_output_recovery_requires_ack_and_inactive_stream(self):
        runtime=self.runtime();runtime.audio_stream_status=Mock(return_value={"active":False});runtime.activate_audio=Mock(return_value={"active":True})
        with self.assertRaisesRegex(ValueError,"acknowledgeRecovery"):
            runtime.recover_audio({"acknowledgePhysicalOutput":True})
        result=runtime.recover_audio({"acknowledgeRecovery":True,"acknowledgePhysicalOutput":True},2)
        self.assertTrue(result["recoveryAttempted"]);runtime.activate_audio.assert_called_once()
        runtime.audio_stream_status.return_value={"active":True}
        with self.assertRaisesRegex(ValueError,"already active"):
            runtime.recover_audio({"acknowledgeRecovery":True,"acknowledgePhysicalOutput":True},2)

    def test_input_recovery_requires_ack_and_inactive_stream(self):
        runtime=self.runtime();runtime.audio_input_status=Mock(return_value={"active":False});runtime.activate_audio_input=Mock(return_value={"active":True})
        with self.assertRaisesRegex(ValueError,"acknowledgeRecovery"):
            runtime.recover_audio_input({"acknowledgePhysicalInput":True})
        result=runtime.recover_audio_input({"acknowledgeRecovery":True,"acknowledgePhysicalInput":True},1)
        self.assertTrue(result["recoveryAttempted"]);runtime.activate_audio_input.assert_called_once()

    def test_stale_input_or_route_cannot_recover_a_different_selection(self):
        runtime = self.runtime()
        runtime.audio_input_status = Mock(return_value={"active":False, "desiredDeviceId":"boom", "route":{"gain":0}})
        runtime.activate_audio_input = Mock(return_value={"active":True})
        for body, message in (({"expectedDeviceId":"other"}, "selected audio input changed"),
                              ({"expectedDeviceId":"boom", "expectedRoute":{"gain":1}}, "route changed")):
            with self.assertRaisesRegex(ValueError, message):
                runtime.recover_audio_input({"acknowledgeRecovery":True, **body})
        runtime.activate_audio_input.assert_not_called()
        runtime.recover_audio_input({"acknowledgeRecovery":True, "expectedDeviceId":"boom", "expectedRoute":{"gain":0}})
        runtime.activate_audio_input.assert_called_once()
