import tempfile,sys,unittest
from pathlib import Path
from threading import Event,Lock,RLock,Thread
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"backend"))
from midi_identity import MidiIdentityStore
from runtime import StageMeshRuntime


class MidiHotplugTests(unittest.TestCase):
    def runtime(self,raw):
        runtime=StageMeshRuntime.__new__(StageMeshRuntime)
        runtime.native=Mock();runtime.native.available=True
        runtime.state=Mock();runtime.state.snapshot.return_value={"midi":{"bindings":{"win-old":"player-a"}}}
        runtime.replication=Mock();runtime.replication.is_primary.return_value=True
        runtime.midi_identities=MidiIdentityStore(Path(raw)/"midi-identities.json")
        runtime.midi_identities.record("win-old",{"persistentId":"midi-stable","identityStrength":"os-stable-endpoint","automaticRebindEligible":True})
        runtime._midi_devices=[];runtime._last_midi_scan=0;runtime._midi_scan_lock=RLock();runtime._midi_hotplug_generation=0;runtime._midi_hotplug_changes=[]
        return runtime

    def identity(self,persistent="midi-stable",eligible=True):
        return {"persistentId":persistent,"identityStrength":"os-stable-endpoint","automaticRebindEligible":eligible,"identityScope":"test"}

    def test_persistent_identity_rebinds_across_native_id_change_without_state_rewrite(self):
        with tempfile.TemporaryDirectory() as raw:
            runtime=self.runtime(raw)
            runtime._midi_devices=[{"id":"win-old","connected":True,"persistentId":"midi-stable","attached":True}]
            runtime.native.scan_midi_devices.return_value=[{"id":"win-new","backend":"windows-midi","connected":True,"input":True}]
            with patch("runtime.describe_midi_device",return_value=self.identity()):
                devices=runtime._refresh_midi_devices(rebind=True)
            runtime.native.detach_midi_input.assert_called_once_with("win-old")
            runtime.native.attach_midi_input.assert_called_once_with("win-new","player-a")
            self.assertEqual(devices[0]["reconnectsDeviceIds"],["win-old"])
            self.assertEqual(devices[0]["desiredDeviceIds"],["win-old"])
            self.assertEqual(devices[0]["playerId"],"player-a")
            self.assertEqual(devices[0]["reconnectStatus"],"persistent-match")
            self.assertEqual(runtime.state.snapshot.return_value["midi"]["bindings"],{"win-old":"player-a"})

    def test_duplicate_persistent_identity_is_not_rebound(self):
        with tempfile.TemporaryDirectory() as raw:
            runtime=self.runtime(raw)
            runtime.native.scan_midi_devices.return_value=[
                {"id":"win-a","backend":"windows-midi","connected":True,"input":True},
                {"id":"win-b","backend":"windows-midi","connected":True,"input":True},
            ]
            with patch("runtime.describe_midi_device",return_value=self.identity()):
                runtime._refresh_midi_devices(rebind=True)
            runtime.native.attach_midi_input.assert_not_called()

    def test_same_native_id_identity_change_detaches_and_preserves_pin(self):
        with tempfile.TemporaryDirectory() as raw:
            runtime=self.runtime(raw)
            runtime._midi_devices=[{"id":"win-old","connected":True,"persistentId":"midi-stable","attached":True}]
            runtime.native.scan_midi_devices.return_value=[{"id":"win-old","backend":"windows-midi","connected":True,"input":True}]
            with patch("runtime.describe_midi_device",return_value=self.identity("midi-other")):
                runtime._refresh_midi_devices(rebind=True)
            runtime.native.detach_midi_input.assert_called_once_with("win-old")
            runtime.native.attach_midi_input.assert_not_called()
            self.assertEqual(runtime.midi_identities.expected("win-old")["persistentId"],"midi-stable")
            changes=runtime.midi_hotplug_status()["changes"]
            self.assertEqual(len(changes),1);self.assertEqual(changes[0]["kind"],"identity-changed")
            self.assertTrue(changes[0]["detached"])

    def test_disconnect_detaches_and_records_hotplug_generation(self):
        with tempfile.TemporaryDirectory() as raw:
            runtime=self.runtime(raw)
            runtime._midi_devices=[{"id":"win-old","connected":True,"persistentId":"midi-stable","attached":True}]
            runtime.native.scan_midi_devices.return_value=[]
            with patch("runtime.describe_midi_device",return_value=self.identity()):
                runtime._refresh_midi_devices(rebind=True)
            runtime.native.detach_midi_input.assert_called_once_with("win-old")
            status=runtime.midi_hotplug_status();self.assertEqual(status["generation"],1)
            self.assertEqual(status["changes"][0]["kind"],"disconnected")
            self.assertFalse(status["automaticActivation"])

    def test_concurrent_midi_scans_are_serialized(self):
        with tempfile.TemporaryDirectory() as raw:
            runtime=self.runtime(raw);entered=Event();release=Event();counter=Lock();active=0;maximum=0
            def scan():
                nonlocal active,maximum
                with counter:active+=1;maximum=max(maximum,active);entered.set()
                release.wait(.5)
                with counter:active-=1
                return []
            runtime.native.scan_midi_devices.side_effect=scan
            first=Thread(target=runtime._refresh_midi_devices);second=Thread(target=runtime._refresh_midi_devices)
            first.start();self.assertTrue(entered.wait(.2));second.start()
            self.assertEqual(runtime.native.scan_midi_devices.call_count,1);release.set();first.join();second.join()
            self.assertEqual(maximum,1);self.assertEqual(runtime.native.scan_midi_devices.call_count,2)


if __name__=="__main__":unittest.main()
