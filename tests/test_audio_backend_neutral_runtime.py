import sys,tempfile,unittest
from pathlib import Path
from threading import RLock
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"backend"))
from runtime import StageMeshRuntime


class BackendNeutralAudioRuntimeTests(unittest.TestCase):
    def runtime(self):
        runtime=StageMeshRuntime.__new__(StageMeshRuntime)
        runtime._audio_control_lock=RLock();runtime.native=Mock();runtime.native.available=True
        runtime._audio_activation_preflight={};runtime._has_authority=Mock(return_value=True)
        runtime._mapped_execution_device=Mock(return_value=None);runtime._mark_post_promotion_output=Mock()
        runtime.state=Mock();runtime.state.snapshot.return_value={"audio":{"sampleRate":48000,"bufferFrames":128}}
        return runtime

    def output_config(self):
        return {"slot":0,"deviceId":"endpoint","graphOutput":0,"playerId":"","master":1.0,"limiterCeilingDb":-1.0,"purpose":"foh","driftCompensation":{}}

    def input_config(self):
        return {"slot":0,"deviceId":"input-endpoint","playerId":"","sampleRate":48000,"route":{"output":0,"gain":0.0}}

    def test_stream_status_treats_any_non_none_backend_as_active(self):
        runtime=self.runtime();runtime._audio_output_configs=Mock(return_value=[self.output_config()]);runtime._find_audio_device=Mock(return_value={"id":"endpoint"})
        runtime.native.audio_stream_status.return_value={"execution":"wasapi","state":"2","selected":"endpoint","error":"none"}
        status=runtime.audio_stream_status(0)
        self.assertTrue(status["active"]);self.assertEqual(status["executionBackend"],"wasapi")

    def test_non_alsa_output_start_revalidates_identity_and_marks_output(self):
        runtime=self.runtime();config=self.output_config();runtime._audio_output_configs=Mock(return_value=[config])
        device={"id":"endpoint","backend":"wasapi","connected":True,"output":True}
        runtime._refresh_audio_devices=Mock();runtime._find_audio_device=Mock(return_value=device);runtime._audio_activation_check=Mock(return_value={"supported":True})
        runtime.native.activate_audio.return_value={"execution":"wasapi","running":"1","device":"endpoint","actualRate":"48000","actualFormat":"FLOAT_LE","actualChannels":"2","output":"0"}
        with patch("runtime.audio_conversion_plan",return_value={"nativeConversionFlags":0,"approved":True}):
            result=runtime.activate_audio({"acknowledgePhysicalOutput":True},0)
        self.assertTrue(result["active"]);self.assertEqual(result["executionBackend"],"wasapi")
        self.assertGreaterEqual(runtime._refresh_audio_devices.call_count,2);runtime._mark_post_promotion_output.assert_called_once_with("audio")

    def test_non_alsa_input_start_stops_if_identity_disappears_after_start(self):
        runtime=self.runtime();runtime._audio_input_configs=Mock(return_value=[self.input_config()])
        device={"id":"input-endpoint","backend":"coreaudio","connected":True,"input":True}
        runtime._refresh_audio_devices=Mock();runtime._find_audio_device=Mock(side_effect=[device,None]);runtime._audio_activation_check=Mock(return_value={"supported":True})
        runtime.native.activate_audio_input.return_value={"execution":"coreaudio","running":"1","device":"input-endpoint","actualRate":"48000","actualFormat":"FLOAT_LE","actualChannels":"2","source":"24"}
        with patch("runtime.audio_conversion_plan",return_value={"nativeConversionFlags":0,"approved":True}),self.assertRaisesRegex(RuntimeError,"disconnected during activation"):
            runtime.activate_audio_input({"acknowledgePhysicalInput":True},0)
        runtime.native.deactivate_audio_input.assert_called_once_with(0)

    def test_platform_without_preflight_adapter_fails_explicitly_before_alsa_probe(self):
        runtime=self.runtime()
        with patch("runtime.audio_preflight") as preflight,self.assertRaisesRegex(RuntimeError,"not implemented for wasapi"):
            runtime._audio_activation_check({"backend":"wasapi","address":"opaque"},"playback",48000,2,128,0)
        preflight.assert_not_called()


if __name__=="__main__":unittest.main()
