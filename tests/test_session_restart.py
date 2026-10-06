"""Runtime restart acceptance checks; no physical audio device is opened."""
import hashlib
import sys
import tempfile
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from runtime import StageMeshRuntime


class SessionRestartTests(unittest.TestCase):
    def test_close_cleans_native_engine_after_capture_timeout(self):
        with tempfile.TemporaryDirectory() as raw:
            runtime = self.open_runtime(Path(raw))
            with patch.object(runtime.daw_capture, "abort", side_effect=RuntimeError("take remains pending")), patch.object(runtime.native, "close", wraps=runtime.native.close) as close:
                with self.assertRaisesRegex(RuntimeError, "take remains pending"):
                    runtime.close()
                close.assert_called_once()

    def test_close_cleans_native_engine_after_producer_timeout(self):
        with tempfile.TemporaryDirectory() as raw:
            runtime = self.open_runtime(Path(raw))
            with patch.object(runtime.daw_producer, "stop", side_effect=RuntimeError("restart blocked")), patch.object(runtime.native, "close", wraps=runtime.native.close) as close:
                with self.assertRaisesRegex(RuntimeError, "restart blocked"):
                    runtime.close()
                close.assert_called_once()
                self.assertEqual(runtime.daw_capture.status()["state"], "aborted")

    def open_runtime(self, root):
        runtime = StageMeshRuntime(root)
        self.addCleanup(runtime.close)
        if not runtime.native.available:
            self.skipTest("native engine not built")
        return runtime

    def pump_until(self, runtime, predicate):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            runtime.pump_midi_once()
            if predicate():
                return
            time.sleep(.005)
        self.fail("native MIDI event did not reach the expected state")

    def prepare(self, root):
        imports = root / "imports"
        imports.mkdir()
        path = imports / "tone.wav"
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(48000)
            output.writeframes(b"\x00\x20" * 1000)
        digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        runtime = self.open_runtime(root)
        imported = runtime.daw_ingest_media({"path": "tone.wav"})
        self.assertEqual(imported["contentHash"], digest)
        self.assertEqual(imported["canonicalFrames"], 4000)
        path.unlink()  # Playback and reopen must use the managed copy.
        path = root / "media" / imported["managedPath"]
        saved = runtime.save_daw_session({
            "sessionId": "restart-acceptance", "revision": 1,
            "tracks": [{"trackId": "audio", "kind": "audio", "clips": [{
                "clipId": "pad-sample", "startFrame": 0, "lengthFrames": 2000,
                "source": {"type": "audio-file", "uri": imported["managedPath"], "contentHash": digest}
            }]}]})
        runtime.midi_mapping_learn({"targetId": "sample.trigger", "resourceId": "pad-sample", "quantize": "off"})
        runtime.native.inject_midi_input("pads", "alex", 0, 0x90, 36, 100)
        self.pump_until(runtime, lambda: len(runtime.midi_mapping_status()["mappings"]) == 1)
        mappings = runtime.midi_mapping_status()["mappings"]
        runtime.close()
        return saved, mappings, path

    def test_save_learn_reopen_and_submit_native_sample(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            saved, mappings, _ = self.prepare(root)
            runtime = self.open_runtime(root)
            self.assertEqual(runtime.daw_session(), saved)
            self.assertEqual(runtime.midi_mapping_status()["mappings"], mappings)
            self.assertEqual(runtime.daw_sampler_status()["registered"], 1)
            self.assertEqual(runtime.midi_mapping_status()["nativeExecution"]["bindings"], 1)
            plan = runtime.daw_render_plan({"startFrame": 0, "endFrame": 2000})
            self.assertEqual(plan["regions"][0]["renderFrames"], 2000)
            self.assertFalse(plan["physicalOutputsArmed"])
            runtime.daw_playback_control({"action": "start", "startFrame": 0, "endFrame": 2000})
            self.pump_until(runtime, lambda: not runtime.daw_playback_status()["producer"]["running"])
            playback = runtime.daw_playback_status()
            self.assertEqual(playback["producer"]["errors"], 0)
            self.assertEqual(playback["producer"]["producedBlocks"], 8)
            self.assertFalse(playback["physicalOutputsArmed"])
            runtime.daw_playback_control({"action": "stop"})
            receipt = runtime.daw_render({"fileName": "acceptance.wav", "startFrame": 0, "endFrame": 2000, "bits": 32})
            with wave.open(receipt["output"], "rb") as rendered:
                self.assertEqual((rendered.getframerate(), rendered.getsampwidth(), rendered.getnchannels(), rendered.getnframes()), (192000, 4, 2, 2000))
                self.assertTrue(any(rendered.readframes(2000)))
            self.assertEqual(receipt["sourceHashes"], [saved["tracks"][0]["clips"][0]["source"]["contentHash"]])
            before = int(runtime.native.sampler_status()["submitted"])
            runtime.native.inject_midi_input("pads", "alex", 0, 0x90, 36, 100)
            self.pump_until(runtime, lambda: int(runtime.native.sampler_status()["submitted"]) > before)
            self.assertEqual(runtime.native.sampler_status()["physicalOutputsArmed"], "0")
            runtime.close()

    def test_changed_media_is_not_promoted_after_restart(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            saved, mappings, path = self.prepare(root)
            with path.open("ab") as output:
                output.write(b"changed")
            runtime = self.open_runtime(root)
            self.assertEqual(runtime.daw_session(), saved)
            self.assertEqual(runtime.midi_mapping_status()["mappings"], mappings)
            self.assertEqual(runtime.daw_sampler_status()["registered"], 0)
            output = root / "exports" / "protected.wav"
            output.write_bytes(b"previous export")
            with self.assertRaisesRegex(ValueError, "media hash mismatch"):
                runtime.daw_render({"fileName": "protected.wav", "startFrame": 0, "endFrame": 2000})
            self.assertEqual(output.read_bytes(), b"previous export")
            before = runtime.daw_playback_status()["generation"]
            with self.assertRaisesRegex(ValueError, "media hash mismatch"):
                runtime.daw_playback_control({"action": "start", "startFrame": 0, "endFrame": 2000})
            self.assertEqual(runtime.daw_playback_status()["generation"], before)
            self.assertIsNone(runtime.daw_producer.thread)
            self.assertEqual(runtime.midi_mapping_status()["nativeExecution"]["bindings"], 0)
            self.assertEqual(runtime.native.sampler_status()["physicalOutputsArmed"], "0")
            runtime.close()

    def test_runtime_loop_repeats_production_and_stop_joins_worker(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.prepare(root)
            runtime = self.open_runtime(root)
            runtime.daw_playback_control({"action": "loop", "beginFrame": 256, "endFrame": 768})
            self.pump_until(runtime, lambda: runtime.daw_playback_status()["producer"]["producedBlocks"] >= 4)
            status = runtime.daw_playback_status()
            self.assertTrue(status["producer"]["looping"])
            self.assertTrue(status["producer"]["running"])
            self.assertEqual(status["looping"], "1")
            self.assertEqual(status["producer"]["errors"], 0)
            generation = status["generation"]
            runtime.daw_playback_control({"action": "loop", "beginFrame": 0, "endFrame": 300})
            self.pump_until(runtime, lambda: runtime.daw_playback_status()["producer"]["producedBlocks"] >= 3)
            arbitrary = runtime.daw_playback_status()
            self.assertGreater(arbitrary["generation"], generation)
            self.assertTrue(arbitrary["producer"]["running"])
            self.assertEqual(arbitrary["producer"]["endFrame"], 300)
            self.assertEqual(arbitrary["producer"]["errors"], 0)
            runtime.daw_playback_control({"action": "stop"})
            self.assertIsNone(runtime.daw_producer.thread)
            self.assertFalse(runtime.daw_playback_status()["producer"]["running"])
            self.assertEqual(runtime.daw_playback_status()["running"], "0")
            self.assertFalse(runtime.daw_playback_status()["physicalOutputsArmed"])
            runtime.close()
