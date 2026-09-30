import tempfile,sys,unittest
from pathlib import Path
from threading import Event, Lock, RLock, Thread
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"backend"))
from audio_identity import AudioIdentityStore
from runtime import StageMeshRuntime


class AudioHotplugTests(unittest.TestCase):
    def runtime(self,raw):
        runtime=StageMeshRuntime.__new__(StageMeshRuntime);runtime.native=Mock();runtime.native.available=True
        runtime.state=Mock();runtime.state.snapshot.return_value={"audio":{"sampleRate":192000,"bufferFrames":256,"outputs":[{"slot":0,"deviceId":"alsa-old"}],"inputs":[]}}
        runtime.audio_identities=AudioIdentityStore(Path(raw)/"audio-identities.json");runtime.audio_identities.record("alsa-old",{"persistentId":"audio-serial","identityStrength":"hardware-serial","automaticReconnectEligible":True})
        runtime._audio_devices=[];runtime._audio_control_lock=RLock();runtime._audio_scan_lock=RLock();runtime._audio_hotplug_generation=0;runtime._audio_hotplug_changes=[];runtime._last_audio_scan=0
        return runtime

    def test_concurrent_scans_are_serialized(self):
        with tempfile.TemporaryDirectory() as raw:
            runtime=self.runtime(raw);entered=Event();release=Event();counter=Lock();active=0;maximum=0
            def scan():
                nonlocal active,maximum
                with counter:active+=1;maximum=max(maximum,active);entered.set()
                release.wait(.5)
                with counter:active-=1
                return []
            runtime.native.scan_audio_devices.side_effect=scan
            first=Thread(target=runtime._refresh_audio_devices);second=Thread(target=runtime._refresh_audio_devices)
            first.start();self.assertTrue(entered.wait(.2));second.start()
            self.assertEqual(runtime.native.scan_audio_devices.call_count,1);release.set();first.join();second.join()
            self.assertEqual(maximum,1);self.assertEqual(runtime.native.scan_audio_devices.call_count,2)

    def test_serial_replacement_is_reselected_but_never_activated(self):
        with tempfile.TemporaryDirectory() as raw:
            runtime=self.runtime(raw);runtime.native.scan_audio_devices.return_value=[{"id":"alsa-new","backend":"alsa","address":"hw:3,0","connected":True,"input":False,"output":True}]
            identity={"persistentId":"audio-serial","identityStrength":"hardware-serial","automaticReconnectEligible":True,"identityScope":"test"}
            with patch("runtime.describe_audio_device",return_value=identity):devices=runtime._refresh_audio_devices(reselect=True)
            self.assertEqual(devices[0]["reconnectsDeviceIds"],["alsa-old"]);self.assertEqual(devices[0]["reconnectStatus"],"serial-match")
            runtime.native.select_audio_device.assert_called_once_with("alsa-new",0);runtime.native.activate_audio.assert_not_called()
            status=runtime.audio_hotplug_status();self.assertEqual(status["generation"],1);self.assertEqual(status["changes"][0]["kind"],"connected");self.assertFalse(status["automaticActivation"])

    def test_repeated_scans_cannot_adopt_replacement_at_same_id(self):
        with tempfile.TemporaryDirectory() as raw:
            runtime=self.runtime(raw)
            runtime.native.scan_audio_devices.return_value=[{"id":"alsa-old","backend":"alsa","address":"hw:2,0","connected":True,"output":True}]
            identity={"persistentId":"audio-other","automaticReconnectEligible":True}
            with patch("runtime.describe_audio_device",return_value=identity):
                runtime._refresh_audio_devices(reselect=True)
                runtime._refresh_audio_devices(reselect=True)
            runtime.native.select_audio_device.assert_not_called()
            self.assertIsNone(runtime._find_audio_device("alsa-old","output"))
            self.assertEqual(runtime.audio_identities.expected("alsa-old")["persistentId"],"audio-serial")

    def test_same_id_identity_change_stops_stream_and_emits_once(self):
        with tempfile.TemporaryDirectory() as raw:
            runtime=self.runtime(raw);runtime._audio_devices=[{"id":"alsa-old","connected":True,"output":True,"persistentId":"audio-serial"}]
            runtime.native.scan_audio_devices.return_value=[{"id":"alsa-old","backend":"alsa","address":"hw:2,0","connected":True,"output":True}]
            runtime.native.audio_stream_status.side_effect=lambda slot:{"selected":"alsa-old","execution":"alsa","state":"2"} if slot==1 else {}
            identity={"persistentId":"audio-other","identityStrength":"hardware-serial","automaticReconnectEligible":True}
            with patch("runtime.describe_audio_device",return_value=identity):
                runtime._refresh_audio_devices(reselect=True);runtime._refresh_audio_devices(reselect=True)
            runtime.native.deactivate_audio.assert_called_once_with(1);runtime.native.select_audio_device.assert_not_called()
            changes=[item for item in runtime.audio_hotplug_status()["changes"] if item["kind"]=="identity-changed"]
            self.assertEqual(len(changes),1);self.assertEqual(changes[0]["previousPersistentId"],"audio-serial");self.assertEqual(changes[0]["currentPersistentId"],"audio-other")

    def test_explicit_identity_replacement_reselects_without_activation(self):
        with tempfile.TemporaryDirectory() as raw:
            runtime=self.runtime(raw);runtime.native.scan_audio_devices.return_value=[{"id":"alsa-new","backend":"alsa","address":"hw:3,0","connected":True,"output":True}]
            runtime.native.audio_stream_status.return_value={"execution":"none","state":"0"};runtime.native.audio_input_status.return_value={"execution":"none","state":"0"}
            identity={"persistentId":"audio-new","identityStrength":"topology","automaticReconnectEligible":False,"identityScope":"test"}
            with patch("runtime.describe_audio_device",return_value=identity):
                receipt=runtime.replace_audio_identity({"desiredDeviceId":"alsa-old","currentDeviceId":"alsa-new","direction":"output","acknowledgeIdentityReplacement":True})
            self.assertTrue(receipt["selected"]);self.assertFalse(receipt["streamsStarted"]);self.assertFalse(receipt["physicalOutputsArmed"])
            self.assertEqual(runtime.audio_identities.expected("alsa-old")["persistentId"],"audio-new")
            runtime.native.select_audio_device.assert_called_with("alsa-new",0);runtime.native.activate_audio.assert_not_called()

    def test_identity_replacement_requires_ack_and_inactive_direction(self):
        with tempfile.TemporaryDirectory() as raw:
            runtime=self.runtime(raw)
            with self.assertRaisesRegex(ValueError,"acknowledgeIdentityReplacement"):runtime.replace_audio_identity({})
            runtime.native.scan_audio_devices.return_value=[{"id":"alsa-new","backend":"alsa","address":"hw:3,0","connected":True,"output":True}]
            runtime.native.audio_stream_status.return_value={"execution":"alsa","state":"2"};identity={"persistentId":"audio-new","identityStrength":"hardware-serial","automaticReconnectEligible":True}
            with patch("runtime.describe_audio_device",return_value=identity),self.assertRaisesRegex(ValueError,"stop all active"):
                runtime.replace_audio_identity({"desiredDeviceId":"alsa-old","currentDeviceId":"alsa-new","direction":"output","acknowledgeIdentityReplacement":True})

    def test_disconnect_advances_generation_and_after_filter_is_bounded(self):
        with tempfile.TemporaryDirectory() as raw:
            runtime=self.runtime(raw);runtime.native.scan_audio_devices.return_value=[{"id":"null-audio","backend":"null","address":"null","connected":True,"input":False,"output":True}]
            runtime._refresh_audio_devices();runtime.native.scan_audio_devices.return_value=[];runtime._refresh_audio_devices()
            self.assertEqual(runtime.audio_hotplug_status()["generation"],2);changes=runtime.audio_hotplug_status(after=1)["changes"];self.assertEqual(len(changes),1);self.assertEqual(changes[0]["kind"],"disconnected")

    def test_disconnected_active_streams_stop_before_reselection(self):
        with tempfile.TemporaryDirectory() as raw:
            runtime=self.runtime(raw);runtime._audio_devices=[{"id":"alsa-old","connected":True,"output":True,"input":True}]
            runtime.native.scan_audio_devices.return_value=[]
            runtime.native.audio_stream_status.side_effect=lambda slot:{"selected":"alsa-old","execution":"alsa","state":"2"} if slot==1 else {}
            runtime.native.audio_input_status.side_effect=lambda slot:{"selected":"alsa-old","execution":"alsa","state":"2"} if slot==2 else {}
            runtime._refresh_audio_devices(reselect=True)
            runtime.native.deactivate_audio.assert_called_once_with(1);runtime.native.deactivate_audio_input.assert_called_once_with(2)
            change=runtime.audio_hotplug_status()["changes"][0];self.assertEqual(change["stoppedOutputSlots"],[1]);self.assertEqual(change["stoppedInputSlots"],[2])


if __name__=="__main__":unittest.main()

class CrossPlatformAudioHotplugTests(AudioHotplugTests):
    def test_non_alsa_active_stream_stops_on_unsafe_identity_change(self):
        with tempfile.TemporaryDirectory() as raw:
            runtime=self.runtime(raw)
            runtime._audio_devices=[{"id":"endpoint-old","connected":True,"output":True,"persistentId":"audio-serial"}]
            runtime.native.scan_audio_devices.return_value=[{"id":"endpoint-old","backend":"wasapi","connected":True,"output":True}]
            runtime.native.audio_stream_status.side_effect=lambda slot:{"selected":"endpoint-old","execution":"wasapi","state":"2"} if slot==2 else {}
            identity={"persistentId":"audio-other","identityStrength":"os-stable-endpoint","automaticReconnectEligible":True}
            with patch("runtime.describe_audio_device",return_value=identity):
                runtime._refresh_audio_devices(reselect=True)
            runtime.native.deactivate_audio.assert_called_once_with(2)
            runtime.native.select_audio_device.assert_not_called()
