import os
import sys
import tempfile
import subprocess
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from native_engine import NativeEngineClient, parse_response
from runtime import StageForgeRuntime


class NativeProtocolTests(unittest.TestCase):
    def test_explicit_pcm_activation_protocol_is_backward_compatible(self):
        client = object.__new__(NativeEngineClient)
        commands = []
        client.request = lambda command: commands.append(command) or {"running":"1"}
        client.activate_audio(48000, 128, 3, 2, conversion_flags=7, sample_format="S16_LE", channels=6)
        client.activate_audio_input(48000, 128, 8, 25, 1, conversion_flags=7, sample_format="S24_3LE")
        client.activate_audio(48000, 128, 3, 2, conversion_flags=1)
        self.assertEqual(commands[0], "AUDIO_ACTIVATE 2 48000.000 128 3 7 S16_LE 6")
        self.assertEqual(commands[1], "AUDIO_INPUT_ACTIVATE 1 48000.000 128 8 25 7 S24_3LE")
        self.assertEqual(commands[2], "AUDIO_ACTIVATE 2 48000.000 128 3 1")

    def test_response_parser(self):
        ok, values = parse_response("OK engineVersion=0.3 protocol=1")
        self.assertTrue(ok)
        self.assertEqual(values["protocol"], "1")
        ok, values = parse_response("ERR code=argument message=bad_value")
        self.assertFalse(ok)
        self.assertEqual(values["message"], "bad value")

    def test_stdio_ipc_requires_spawn_token_when_configured(self):
        executable = Path(os.environ.get("STAGEFORGE_NATIVE_ENGINE") or ROOT / "build" / "native" / ("stagemesh_engine.exe" if os.name == "nt" else "stagemesh_engine"))
        if not executable.is_file():
            self.skipTest("native engine not built")
        env = os.environ.copy()
        env["STAGEFORGE_IPC_TOKEN"] = "unit-test-token"
        process = subprocess.Popen(
            [str(executable), "--stdio"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, env=env,
        )
        try:
            assert process.stdin is not None and process.stdout is not None
            process.stdin.write("HELLO\n")
            process.stdin.flush()
            ok, values = parse_response(process.stdout.readline())
            self.assertFalse(ok)
            self.assertEqual(values.get("code"), "permission")
            process.stdin.write("AUTH unit-test-token\n")
            process.stdin.flush()
            ok, values = parse_response(process.stdout.readline())
            self.assertTrue(ok)
            self.assertEqual(values.get("authenticated"), "1")
            process.stdin.write("HELLO\n")
            process.stdin.flush()
            ok, values = parse_response(process.stdout.readline())
            self.assertTrue(ok)
            self.assertEqual(values.get("protocol"), "1")
            process.stdin.write("QUIT\n")
            process.stdin.flush()
            process.wait(timeout=2)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=2)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()

    def test_native_client_when_binary_is_available(self):
        client = NativeEngineClient()
        if not client.available:
            self.skipTest(client.status().get("error", "native engine not built"))
        try:
            hello = client.request("HELLO")
            self.assertEqual(hello["protocol"], "1")
            self.assertEqual(hello["nativeMidiPerformance"], "1")
            self.assertEqual(hello["samplerVoiceEngine"], "1")
            self.assertEqual(hello["transportDiscipline"], "1")
            self.assertEqual(hello["midiClock24Ppqn"], "1")
            self.assertEqual(hello["effectChain"], "1")
            self.assertEqual(hello["physicalPcmConversion"], "1")
            self.assertEqual(hello["captureIngress"], "1")
            self.assertEqual(hello["nativeCaptureOwner"], "1" if os.name == "nt" or sys.platform == "darwin" else "0")
            self.assertEqual(hello["leUwbHub"], "1")
            self.assertEqual(hello["leIsoHardware"], "1")
            self.assertEqual(hello["uwbHardwareBridge"], "1")
            self.assertEqual(client.effect_status(0)["registered"], "0")
            core = client.core_status()
            self.assertIn("revision", core)
            self.assertIn("snapshotCommits", core)
            client.request("MONITOR_SET alex master 88")
            monitor = client.request("MONITOR_GET alex")
            self.assertEqual(float(monitor["master"]), 88.0)
            timing = client.request("TIMING_PLAN 80000000 100000000 5000000 2000000 6000000 1")
            self.assertEqual(timing["dispatchNs"], "91000000")
            client.set_clock_source("ptp-test")
            clock = client.observe_clock(1_000_000, 1_005_000)
            self.assertEqual(clock["state"], "locked")
            self.assertEqual(clock["offsetNs"], "5000")
            holdover = client.clock_status(2_100_000_000)
            self.assertEqual(holdover["state"], "holdover")
            notation = client.notation_quantize(1.27, "1/8")
            self.assertEqual(float(notation["beats"]), 1.5)
            audio_devices = client.scan_audio_devices()
            self.assertTrue(any(device["id"] == "null-audio" for device in audio_devices))
            selected = client.select_audio_device("null-audio")
            self.assertEqual(selected["execution"], "null-audio")
            route = client.set_audio_route(0, 0, 0.75)
            self.assertAlmostEqual(float(route["gain"]), 0.75, places=3)
            output = client.set_audio_output(0, 1.0, -3.0)
            self.assertAlmostEqual(float(output["ceilingDb"]), -3.0, places=3)
            drift = client.configure_audio_drift(0, enabled=True, max_ppm=1500.0, queue_gain_ppm=750.0)
            self.assertEqual(drift["enabled"], "1")
            self.assertAlmostEqual(float(drift["maxPpm"]), 1500.0, places=1)
            stream = client.audio_stream_status()
            self.assertEqual(stream["execution"], "null-audio")
            monitor_out = client.bind_audio_output_player("alex", 1)
            self.assertEqual(monitor_out["slot"], "1")
            self.assertGreaterEqual(int(monitor_out["output"]), 1)
            bind0 = client.bind_audio_input_player("alex", 0)
            bind1 = client.bind_audio_input_player("jordan", 1)
            self.assertNotEqual(bind0["source"], bind1["source"])
            self.assertEqual(client.audio_input_status(0)["source"], bind0["source"])
            self.assertEqual(client.audio_input_status(1)["source"], bind1["source"])
            alsa = next((device for device in audio_devices if device.get("backend") == "alsa" and device.get("output")), None)
            if alsa is not None:
                client.select_audio_device(alsa["id"], 0)
                client.select_audio_device(alsa["id"], 1)
                activated = client.activate_audio(48000, 64, 0, 0, conversion_flags=1)
                monitor_output = int(client.bind_audio_output_player("alex", 1)["output"])
                activated_monitor = client.activate_audio(48000, 64, monitor_output, 1, conversion_flags=1)
                self.assertEqual(activated["execution"], "alsa")
                self.assertEqual(activated_monitor["execution"], "alsa")
                time.sleep(0.02)
                stream = client.audio_stream_status(0)
                monitor_stream = client.audio_stream_status(1)
                self.assertEqual(stream["execution"], "alsa")
                self.assertEqual(monitor_stream["execution"], "alsa")
                self.assertGreater(int(stream["callbacks"]), 0)
                self.assertGreater(int(monitor_stream["callbacks"]), 0)
                self.assertIn("driftEnabled", stream)
                self.assertIn("correctionPpm", stream)
                self.assertIn("firstWriteNs", stream)
                self.assertIn("maxExcessGapNs", stream)
                self.assertIn("firstRenderShowNs", stream)
                self.assertIn("lastRenderShowNs", stream)
                self.assertIn("lastBlockEndShowNs", stream)
                self.assertEqual(float(stream["configuredRate"]), 48000.0)
                self.assertEqual(float(stream["requestedRate"]), 48000.0)
                self.assertEqual(int(stream["requestedPeriodFrames"]), 64)
                self.assertGreater(int(stream["periodFrames"]), 0)
                self.assertEqual(int(stream["channels"]), 2)
                self.assertEqual(stream["sampleFormat"], "FLOAT_LE")
                client.deactivate_audio(1)
                client.deactivate_audio(0)
                alsa_null = next((device for device in audio_devices if device.get("backend") == "alsa" and device.get("address") == "null"), None)
                if alsa_null is not None:
                    client.select_audio_device(alsa_null["id"], 0)
                    integer_output = client.activate_audio(48000, 64, 0, 0, conversion_flags=7, sample_format="S16_LE", channels=4)
                    self.assertEqual(integer_output["actualFormat"], "S16_LE")
                    self.assertEqual(integer_output["actualChannels"], "4")
                    client.deactivate_audio(0)
                    client.select_audio_input(alsa_null["id"], 0)
                    integer_input = client.activate_audio_input(48000, 64, 4, 24, 0, conversion_flags=7, sample_format="S24_3LE")
                    self.assertEqual(integer_input["actualFormat"], "S24_3LE")
                    self.assertEqual(integer_input["actualChannels"], "4")
                    client.deactivate_audio_input(0)
            client.schedule_lighting(1, 1000, 0, 1, 77)
            drained_light = client.drain_lighting(1000)
            self.assertEqual(drained_light["drained"], "1")
            artnet = client.artnet_frame_info(0)
            self.assertEqual(artnet["bytes"], "530")
            self.assertEqual(artnet["channel1"], "77")
            client.configure_lighting_network("127.0.0.1", 6454)
            client.arm_lighting_network(True)
            client.schedule_lighting(2, 2000, 0, 2, 88)
            drained_network = client.drain_lighting(2000)
            self.assertEqual(drained_network["sent"], "1")
            network = client.lighting_network_status()
            self.assertEqual(network["armed"], "1")
            self.assertGreaterEqual(int(network["packets"]), 1)
            client.arm_lighting_network(False)
            client.configure_lighting_network("127.0.0.1", 5568, protocol="sacn", universe_base=101)
            sacn_network = client.lighting_network_status()
            self.assertEqual(sacn_network["protocol"], "sacn")
            self.assertEqual(sacn_network["universeBase"], "101")
            client.arm_lighting_network(True)
            client.schedule_lighting(3, 3000, 0, 1, 99)
            drained_sacn = client.drain_lighting(3000)
            self.assertEqual(drained_sacn["sent"], "1")
            sacn = client.sacn_frame_info(0)
            self.assertEqual(sacn["bytes"], "638")
            self.assertEqual(sacn["networkUniverse"], "101")
            self.assertEqual(sacn["channel1"], "99")
            client.arm_lighting_network(False)
            devices = client.scan_midi_devices()
            self.assertIsInstance(devices, list)
            client.inject_midi_input("virtual-test", "alex", 123456789, 0x90, 60, 100)
            captured = client.poll_midi_inputs()
            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0]["playerId"], "alex")
            self.assertEqual(captured[0]["data1"], 60)
            native_mapping={"mappingId":"native-cutoff","source":{"deviceId":"virtual-test","channel":0,"message":"cc","number":74},"target":{"targetId":"filter.cutoff","parameterId":1,"minimum":20.0,"maximum":20000.0},"behavior":"absolute","quantize":"off","keySync":False,"enabled":True}
            client.upsert_native_midi_mapping(native_mapping)
            client.inject_midi_input("virtual-test","alex",0,0xB0,74,127)
            client.poll_midi_inputs();client.drain_show_events(0)
            native_map_status=client.native_midi_mapping_status()
            self.assertEqual(native_map_status["submitted"],"1")
            mapped=client.automation_parameter(client._stable_id("midi-map:filter.cutoff"),1,0)
            self.assertAlmostEqual(float(mapped["value"]),20000.0,places=3)
            client.sampler_load_pcm("test-loop",[0.25]*256,[0.125]*256,looped=True,loop_begin=32,loop_end=224,crossfade_frames=16)
            sample_mapping={"mappingId":"native-sample","source":{"deviceId":"virtual-test","channel":0,"message":"note","number":36},"target":{"targetId":"sample.trigger","resourceId":"test-loop"},"behavior":"trigger","quantize":"off","keySync":True,"enabled":True}
            client.upsert_native_midi_mapping(sample_mapping)
            client.inject_midi_input("virtual-test","alex",0,0x90,36,100)
            client.poll_midi_inputs();client.drain_show_events(0)
            sampler_status=client.sampler_status()
            self.assertEqual(sampler_status["samples"],"1")
            self.assertEqual(sampler_status["submitted"],"1")
            self.assertEqual(sampler_status["queued"],"1")
            self.assertEqual(sampler_status["physicalOutputsArmed"],"0")
            events_before = client.show_event_status()
            self.assertIn("submitted", events_before)
            loop_status = client.show_event_loop_status()
            self.assertEqual(loop_status["running"], "1")
            self.assertIn("cycles", loop_status)
            # A cue at the current paused Show Time should execute automatically
            # without EVENT_DRAIN. Poll status only; observation never drains.
            client.submit_cue_event(8999, 0, 41)
            deadline = time.monotonic() + 0.25
            while time.monotonic() < deadline:
                cue_state = client.cue_status()
                if cue_state.get("currentCueId") == "41":
                    break
                time.sleep(0.002)
            self.assertEqual(client.cue_status().get("currentCueId"), "41")
            client.submit_automation_event(9100, 0, 100, 200, 0.25, owner_id=77)
            deadline = time.monotonic() + 0.25
            auto_point = None
            while time.monotonic() < deadline:
                try:
                    auto_point = client.automation_parameter(100, 200, 0)
                    break
                except RuntimeError as exc:
                    if not str(exc).startswith("not_found:"):
                        raise
                time.sleep(0.002)
            self.assertIsNotNone(auto_point, "scheduled automation parameter was not registered")
            self.assertEqual(auto_point["ownerId"], "77")
            self.assertAlmostEqual(float(auto_point["value"]), 0.25, places=3)
            client.submit_automation_event(9101, 1_000_000, 100, 200, 1.0, duration_ms=1000, owner_id=77)
            client.drain_show_events(1_000_000)
            auto_mid = client.automation_parameter(100, 200, 501_000_000)
            self.assertAlmostEqual(float(auto_mid["value"]), 0.625, places=2)
            auto_block = client.automation_block(100, 200, 1_000_000, 250_000_000, 5)
            self.assertEqual(auto_block["frames"], "5")
            self.assertAlmostEqual(float(auto_block["first"]), 0.25, places=2)
            self.assertAlmostEqual(float(auto_block["last"]), 1.0, places=2)
            client.release_automation_owner(9102, 2_000_000_000, 100, 200, 77)
            client.drain_show_events(2_000_000_000)
            self.assertEqual(client.automation_parameter(100, 200, 2_000_000_000)["ownerId"], "0")
            consumed_auto_cue = client.next_cue_event()
            self.assertEqual(consumed_auto_cue.get("cueId"), "41")
            client.submit_cue_event(9001, 2_000_000, 42)
            routed = client.drain_show_events(2_000_000)
            self.assertEqual(routed["routed"], "1")
            cue = client.next_cue_event()
            self.assertEqual(cue["available"], "1")
            self.assertEqual(cue["cueId"], "42")
            client.submit_transport_event(9002, 3_000_000, "bpm", 133.0)
            client.drain_show_events(3_000_000)
            self.assertAlmostEqual(float(client.request("TIME")["bpm"]), 133.0, places=3)
            events_after = client.show_event_status()
            self.assertGreaterEqual(int(events_after["dispatched"]), int(events_before["dispatched"]) + 2)

            client.request("MIDI_SCHEDULE 1 1000000 144 60 100")
            drained = client.request("MIDI_DRAIN 1000000")
            self.assertEqual(drained["drained"], "1")
        finally:
            client.close()

    def test_disciplined_transport_and_midi_clock_protocol(self):
        client=NativeEngineClient()
        if not client.available:self.skipTest(client.status().get("error","native engine not built"))
        try:
            client.configure_transport_discipline(77,3,holdover_ns=1_000,max_slew_ppm=500,recovery_window_ns=5_000_000_000)
            disciplined=client.observe_transport_discipline(1,3,1_000_000,1_000_000,100_000_000,101_000_000)
            self.assertEqual(disciplined["state"],"locked");self.assertGreater(float(disciplined["appliedRate"]),1.0)
            held=client.transport_discipline_status(1_002_000);self.assertEqual(held["state"],"holdover");self.assertEqual(held["holdoverEntries"],"1")
            client.configure_midi_clock(3,120,0);client.start_midi_clock(3,0)
            self.assertEqual(client.emit_midi_clock(100_000_000)["emitted"],"5");self.assertEqual(client.midi_clock_status()["ppqn"],"24")
            client.set_midi_clock_tempo(3,60,125_000_000);self.assertEqual(client.emit_midi_clock(250_000_000)["emitted"],"4")
            client.observe_midi_clock(3,1,1_000_000);client.observe_midi_clock(3,2,21_833_333);self.assertEqual(client.midi_clock_status()["received"],"2")
            client.stop_midi_clock(3,300_000_000)
        finally:client.close()

    def test_le_uwb_hub_stdio_requires_fresh_authenticated_dual_radio_evidence(self):
        client = NativeEngineClient()
        if not client.available:
            self.skipTest(client.status().get("error", "native engine not built"))
        try:
            client.configure_le_uwb_hub(31, max_end_to_end_ns=25_000_000)
            client.register_le_uwb_node(201, 1, 0, 2_000_000, required=True)
            client.register_le_uwb_node(202, 2, 1, 3_000_000, required=True)
            now = 1_000_000_000
            client.observe_uwb_node(201, 1, 31, now, now + 80_000, 7_500, 40, 30_000)
            client.observe_le_isochronous(201, 1, 31, 1, now, 3_000_000, 100_000)
            self.assertEqual(client.plan_le_uwb_sync(now + 1_000_000, 8_000_000_000, 31)["ready"], "0")
            client.observe_uwb_node(202, 1, 31, now, now - 40_000, 11_000, 50, 40_000)
            client.observe_le_isochronous(202, 1, 31, 1, now, 4_000_000, 120_000)
            plan = client.plan_le_uwb_sync(now + 1_000_000, 8_000_000_000, 31)
            self.assertEqual(plan["ready"], "1")
            self.assertEqual(plan["physicalOutputsArmed"], "0")
            target = client.le_uwb_target(201, int(plan["generation"]))
            self.assertGreater(int(target["targetNodeNs"]), int(plan["targetHubNs"]))
            with self.assertRaises(RuntimeError):
                client.observe_uwb_node(201, 1, 31, now + 2, now + 2, 1_000, 10, 10_000)
            with self.assertRaises(RuntimeError):
                client.observe_le_isochronous(201, 2, 31, 2, now + 2, 1_000_000, 10_000, authenticated=False)
            self.assertEqual(client.le_uwb_node_status(201)["rejected"], "2")
            self.assertEqual(client.plan_le_uwb_sync(now + 600_000_000, 8_600_000_000, 31)["ready"], "0")
            self.assertEqual(client.plan_le_uwb_sync(now + 1_000_000, 8_000_000_000, 32)["ready"], "0")
        finally:
            client.close()

    def test_le_uwb_hardware_surface_stays_unarmed_without_devices(self):
        client = NativeEngineClient()
        if not client.available:
            self.skipTest(client.status().get("error", "native engine not built"))
        try:
            status = client.le_uwb_hardware_status()
            self.assertIn("kernelIsoSupported", status)
            self.assertEqual(status["uwbOpen"], "0")
            self.assertEqual(status["physicalOutputsArmed"], "0")
            polled = client.poll_le_uwb_hardware(64)
            self.assertEqual(polled["handled"], "0")
            self.assertEqual(polled["physicalOutputsArmed"], "0")
            with self.assertRaises(RuntimeError):
                client.open_uwb_hardware("/stageforge/nonexistent-uwb-device", 115_200)
            self.assertEqual(client.le_uwb_hardware_status()["uwbOpen"], "0")
            with self.assertRaises(ValueError):
                client.open_le_iso_hardware(201, "bad", "00:11:22:33:44:55")
            with self.assertRaises(ValueError):
                client.poll_le_uwb_hardware(0)
        finally:
            client.close()

    def test_record_rearm_advances_capture_generation(self):
        client = NativeEngineClient()
        if not client.available:
            self.skipTest(client.status().get("error", "native engine not built"))
        try:
            self.assertEqual(client.request("HELLO")["dawPunchLoopCapture"], "1")
            first = client.daw_record_arm(0, True)
            client.daw_record_disarm(0)
            second = client.daw_record_arm(0, True)
            self.assertGreater(int(second["generation"]), int(first["generation"]))
            status = client.daw_record_status(0)
            self.assertEqual(status["generation"], second["generation"])
            self.assertEqual(status["physicalOutputsArmed"], "0")
        finally:
            try: client.daw_record_disarm(0)
            except RuntimeError: pass
            client.close()

    def test_plugin_delay_graph_generation_swap(self):
        client=NativeEngineClient()
        if not client.available:self.skipTest(client.status().get("error","native engine not built"))
        try:
            self.assertEqual(client.request("HELLO")["pluginDelayGraph"],"1")
            client.plugin_delay_graph_prepare(1,100,[0,7,3])
            with self.assertRaises(RuntimeError):client.plugin_delay_graph_activate(99)
            client.plugin_delay_graph_activate(100);status=client.plugin_delay_graph_status()
            self.assertEqual(status["activeGeneration"],"1");self.assertEqual(status["maximumLatencyFrames"],"7");self.assertEqual(status["transactionConnected"],"1");self.assertEqual(status["audioGraphConnected"],"1");self.assertEqual(status["pathBinding"],"output-slot-index");self.assertEqual(status["physicalOutputsArmed"],"0")
            client.effect_delay_transaction_rollback(2,200)
            with self.assertRaises(RuntimeError):client.plugin_delay_graph_activate(199)
            client.plugin_delay_graph_activate(200);status=client.plugin_delay_graph_status()
            self.assertEqual(status["activeGeneration"],"2");self.assertEqual(status["rollbacks"],"1")
        finally:client.close()

    def test_realtime_audit_surface_is_bounded_and_unarmed(self):
        client=NativeEngineClient()
        if not client.available:self.skipTest(client.status().get("error","native engine not built"))
        try:
            hello=client.request("HELLO");self.assertEqual(hello["realtimeAudit"],"1");self.assertIn(hello["realtimeQualification"],("0","1"));self.assertEqual(hello["ingressAudit"],"1");status=client.realtime_audit_status(0)
            if os.environ.get("STAGEFORGE_REQUIRE_RT_QUALIFICATION") == "1":
                self.assertEqual(hello["realtimeQualification"], "1", "release gate requires qualification probes")
            self.assertEqual(status["physicalOutputsArmed"],"0");self.assertIn("deadlineMisses",status);self.assertIn("optionalShedBlocks",status);self.assertEqual(status["qualificationEnabled"],hello["realtimeQualification"]);self.assertIn("allocationAttempts",status);self.assertIn("allocatedBytes",status);self.assertIn("lockAttempts",status)
            with self.assertRaises(RuntimeError):client.realtime_audit_status(4)

            before=client.ingress_audit_status();client.inject_midi_input("audit-test","alex",1,0x90,60,100);after=client.ingress_audit_status()
            self.assertEqual(after["domain"],"midi");self.assertEqual(int(after["injectedMessages"]),int(before["injectedMessages"])+1);self.assertEqual(after["physicalOutputsArmed"],"0")
            capture=client.capture_ingress_audit_status(0);self.assertEqual(capture["domain"],"capture");self.assertEqual(capture["slot"],"0");self.assertIn("nonfiniteSamples",capture);self.assertEqual(capture["physicalOutputsArmed"],"0")
            with self.assertRaises(ValueError):client.capture_ingress_audit_status(4)
            light_before=client.lighting_ingress_audit_status();client.schedule_lighting(991,0,0,10,25);client.drain_lighting(0);light_after=client.lighting_ingress_audit_status()
            self.assertEqual(light_after["domain"],"lighting");self.assertGreaterEqual(int(light_after["accepted"]),int(light_before["accepted"])+1);self.assertGreaterEqual(int(light_after["drained"]),int(light_before["drained"])+1);self.assertEqual(light_after["physicalOutputsArmed"],"0")
            with self.assertRaises(ValueError):client.ingress_audit_status("unknown")
        finally:client.close()

    def test_independent_streaming_voice_protocol_is_bounded_and_unarmed(self):
        client=NativeEngineClient()
        if not client.available:self.skipTest(client.status().get("error","native engine not built"))
        try:
            client.streaming_voice_start(0,1,0.5,False);client.streaming_voice_block(0,1,1,[1.0]*4,[-1.0]*4,True)
            status=client.streaming_voice_status();self.assertEqual(status["diskIoInAudioCallback"],"0");self.assertEqual(status["physicalOutputsArmed"],"0");self.assertIn("activeMask",status)
            slot=client.streaming_voice_slot_status(0);self.assertEqual(slot["physicalOutputsArmed"],"0")
            with self.assertRaises(ValueError):client.streaming_voice_block(0,1,2,[0.0]*257,[0.0]*257)
            client.streaming_voice_stop(0,1)
        finally:client.close()

    def test_user_profile_layers_and_interoperability_handshake(self):
        client = NativeEngineClient()
        if not client.available:
            self.skipTest(client.status().get("error", "native engine not built"))
        try:
            hello = client.request("HELLO")
            self.assertEqual(hello["userProfile"], "1")
            self.assertEqual(hello["interoperabilityHandshake"], "1")
            self.assertEqual(hello["authenticatedInteropSession"], "1")
            self.assertEqual(hello["profileProjection"], "1")
            self.assertEqual(hello["sessionChannel"], "1")
            self.assertEqual(client.configure_user_profile(77, 12)["physicalOutputsArmed"], "0")
            client.set_user_preference(1, 10, 0, 1, 2, 0.25)
            client.set_user_preference(1, 10, 1, 2, 2, 0.75)
            client.set_user_preference(1, 10, 4, 3, 2, 0.90)
            resolved = client.user_preference(1, 10)
            self.assertEqual(resolved["layer"], "4")
            self.assertAlmostEqual(float(resolved["scalar"]), 0.9)
            with self.assertRaises(RuntimeError):
                client.set_user_preference(1, 10, 4, 3, 2, 0.5)
            self.assertEqual(client.clear_user_profile_layer(4)["removed"], "1")
            self.assertEqual(client.user_preference(1, 10)["layer"], "1")
            plan = client.configure_interoperability_handshake(
                {"participantId": 1, "protocolVersions": [1, 3], "profileSchemaVersions": [1, 2],
                 "capabilities": [{"id": 100, "required": True}, 200], "preservesUnknown": True, "offlineCapable": True},
                {"participantId": 2, "protocolVersions": [2, 4], "profileSchemaVersions": [1],
                 "capabilities": [{"id": 100, "required": True}, {"id": 300, "required": True}, 999],
                 "preservesUnknown": True, "offlineCapable": True},
                [{"from": 300, "to": 200, "quality": 95}],
            )
            self.assertEqual(plan["compatible"], "1")
            self.assertEqual(plan["protocolVersion"], "3")
            self.assertEqual(plan["translated"], "1")
            self.assertEqual(plan["unknownPreserved"], "1")
            self.assertEqual(plan["physicalOutputsArmed"], "0")
            self.assertEqual(client.interop_session_offer(1, 2, 3, 12, 1, 10_000)["state"], "offered")
            self.assertEqual(client.interop_session_authenticate(True, 1_000, 12, 0)["state"], "authenticated")
            self.assertEqual(client.interop_session_negotiate(True, 3, 1, 7, 8)["state"], "negotiated")
            self.assertEqual(client.interop_session_consent(True, 9)["state"], "consented")
            activated = client.interop_session_activate(2_000, 12, 7, 8)
            self.assertEqual(activated["state"], "active")
            self.assertEqual(client.interop_session_status()["physicalOutputsArmed"], "0")
            configured = client.configure_session_channel(10, 20, 1, [100, 200])
            self.assertEqual(configured["confidential"], "0")
            outbound = client.session_channel_outbound(100, 64)
            self.assertEqual(outbound["sequence"], "1")
            self.assertEqual(client.session_channel_inbound(10, 20, 1, 1, 100, 32, authenticated=True)["accepted"], "1")
            with self.assertRaises(RuntimeError):
                client.session_channel_inbound(10, 20, 1, 1, 100, 32, authenticated=True)
            with self.assertRaises(RuntimeError):
                client.session_channel_outbound(999, 1)
            self.assertEqual(client.rotate_session_channel(2, 2)["keyEpoch"], "2")
            self.assertEqual(client.session_channel_status()["physicalOutputsArmed"], "0")
        finally:
            client.close()

    def test_planned_handoff_stdio_fences_boundary_epoch_and_output_arm(self):
        client = NativeEngineClient()
        if not client.available:
            self.skipTest(client.status().get("error", "native engine not built"))
        try:
            self.assertEqual(client.request("HELLO").get("plannedHandoff"), "1")
            client.planned_handoff_prepare(101, 12, 13, 5_000, allow_degraded_program=False)
            with self.assertRaises(RuntimeError):
                client.planned_handoff_acknowledge(101, program_ready=False)
            client.planned_handoff_acknowledge(101, program_ready=True)
            with self.assertRaises(RuntimeError):
                client.planned_handoff_commit(101, 12, 13, 4_999)
            with self.assertRaises(RuntimeError):
                client.planned_handoff_commit(101, 12, 14, 5_000)
            committed = client.planned_handoff_commit(101, 12, 13, 5_000)
            self.assertEqual(committed["physicalOutputsArmed"], "0")
            status = client.planned_handoff_status()
            self.assertEqual(status["authorityCommitted"], "1")
            self.assertEqual(status["physicalOutputsArmed"], "0")
        finally:
            client.close()

    def test_native_core_runtime_parameter_cue_routing_journal_shadow_stack(self):
        client = NativeEngineClient()
        if not client.available:
            self.skipTest(client.status().get("error", "native engine not built"))
        try:
            hello = client.request("HELLO")
            self.assertEqual(hello.get("parameterRegistry"), "1")
            self.assertEqual(hello.get("runtimeShow"), "1")
            self.assertEqual(hello.get("coreJournal"), "1")
            client.request("PARAM_BIND_MONITOR_MASTER 9200 1 coretest 0 100 50")
            client.submit_automation_event(12001, 0, 9200, 1, 80.0, owner_id=91)
            client.drain_show_events(0)
            self.assertAlmostEqual(float(client.request("PARAM_GET 9200 1")["value"]), 80.0, places=2)

            client.request("CUE_GRAPH_BEGIN 88")
            client.request("CUE_GRAPH_ADD_AUTOMATION 9200 1 25 0 91 0")
            graph = client.request("CUE_GRAPH_COMMIT")
            self.assertEqual(graph["actions"], "1")
            client.submit_cue_event(12002, 0, 88)
            client.drain_show_events(0)
            self.assertAlmostEqual(float(client.automation_parameter(9200, 1, 0)["value"]), 25.0, places=2)

            client.request("SHOW_COMPILE_BEGIN 55 123456")
            client.request("SHOW_COMPILE_ROLE 1 0")
            client.request("SHOW_COMPILE_CUE 88 99")
            client.request("SHOW_COMPILE_PARAM 9200 1 0 100 50 2 2")
            client.request("SHOW_COMPILE_COMMIT 0")
            client.drain_show_events(0)
            runtime = client.runtime_show_status()
            self.assertEqual(runtime["sourceRevision"], "55")
            self.assertEqual(runtime["parameters"], "1")

            client.request("ROUTE_TX_BEGIN 0")
            client.request("ROUTE_TX_AUDIO 0 0 0.33 1")
            route = client.request("ROUTE_TX_COMMIT")
            self.assertEqual(route["revision"], "1")

            client.request("SHADOW_DECLARE 1 55 999 7 1 1 1")
            client.request("SHADOW_BLOCK 1 7 55 999 3000 4000 48 1")
            client.request("SHADOW_BLOCK 1 7 55 999 4000 5000 48 1")
            shadow = client.shadow_plan(3000, 1000)
            self.assertEqual(shadow["ready"], "1")
            client.request("SHADOW_INVALIDATE 56")
            self.assertEqual(client.shadow_plan(3000, 1000)["ready"], "0")

            journal = client.journal_status()
            self.assertGreaterEqual(int(journal["pending"]), 1)
            record = client.next_journal_record()
            self.assertEqual(record["available"], "1")
            self.assertNotEqual(record["hash"], "0")
        finally:
            client.close()

    def test_runtime_mirrors_monitor_when_native_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = StageForgeRuntime(Path(tmp))
            if not runtime.native.available:
                runtime.close()
                self.skipTest("native engine not built")
            try:
                revision = runtime.state.revision
                runtime.mutate(None, lambda: runtime.state.patch_monitor("alex", {"click": 17}, revision))
                monitor = runtime.native.request("MONITOR_GET alex")
                self.assertEqual(float(monitor["click"]), 17.0)
                core = runtime.native.core_status()
                self.assertEqual(int(core["externalRevision"]), runtime.state.revision)
                self.assertGreaterEqual(int(core["snapshotCommits"]), 1)
                ledger = runtime.repository.verify_ledger()
                self.assertTrue(ledger["ok"])
                self.assertGreaterEqual(int(ledger["records"]), 2)
                text = runtime.repository.ledger_path.read_text("utf-8")
                self.assertIn('"type":"native-core"', text)
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
