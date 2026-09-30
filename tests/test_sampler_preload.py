import hashlib
import json
import math
import struct
import sys
import tempfile
import unittest
import wave
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sampler_preload import MAX_NATIVE_SAMPLER_FRAMES, SamplerPreloadRegistry
from runtime import StageMeshRuntime


class FakeNativeSampler:
    supports_sampler_voice_engine = True

    def __init__(self):
        self.loads = []

    def sampler_load_pcm(self, resource_id, left, right, **settings):
        self.loads.append((resource_id, list(left), list(right), settings))
        return {"committed": "1"}


class SamplerPreloadTests(unittest.TestCase):
    def _wav(self, path: Path, frames: int = 1000) -> str:
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1); output.setsampwidth(2); output.setframerate(48000)
            output.writeframes(b"".join(struct.pack("<h", round(math.sin(index / 8) * 12000)) for index in range(frames)))
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _session(content_hash: str, revision: int = 1, length: int = 2000):
        return {"sessionId": "sampler", "revision": revision, "tracks": [{"trackId": "audio", "kind": "audio", "gain": 1,
            "pan": 0, "clips": [{"clipId": "clip-a", "startFrame": 0, "lengthFrames": length, "sourceOffsetFrames": 0,
            "source": {"type": "audio-file", "uri": "tone.wav", "contentHash": content_hash},
            "fades": {"inFrames": 16, "outFrames": 16}}]}]}

    def test_preload_resamples_verifies_and_fences_generations(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); digest = self._wav(root / "tone.wav"); native = FakeNativeSampler(); registry = SamplerPreloadRegistry(native, root)
            first = registry.preload(self._session(digest), "clip-a", looped=True, choke_group=2, crossfade_frames=128)
            self.assertEqual(first["frames"], 2000); self.assertEqual(first["sourceContentHash"], digest); self.assertFalse(first["physicalOutputsArmed"])
            self.assertEqual(len(native.loads), 1); self.assertEqual(len(native.loads[0][1]), 2000); self.assertTrue(native.loads[0][3]["looped"])
            again = registry.preload(self._session(digest), "clip-a", looped=True, choke_group=2, crossfade_frames=128)
            self.assertEqual(again["nativeResourceId"], first["nativeResourceId"]); self.assertEqual(len(native.loads), 1)
            second = registry.preload(self._session(digest, revision=2), "clip-a", looped=True, choke_group=2, crossfade_frames=128)
            self.assertNotEqual(second["nativeResourceId"], first["nativeResourceId"]); self.assertEqual(registry.status()["publishedGenerations"], 2)
            self.assertFalse(registry.status()["diskIoInAudioCallback"])

    def test_preload_rejects_hash_mismatch_and_oversized_clips(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); digest = self._wav(root / "tone.wav"); registry = SamplerPreloadRegistry(FakeNativeSampler(), root)
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                registry.preload(self._session("sha256:" + "0" * 64), "clip-a")
            with self.assertRaisesRegex(ValueError, "canonical frames"):
                registry.preload(self._session(digest, length=MAX_NATIVE_SAMPLER_FRAMES + 1), "clip-a")

    def test_runtime_preloads_persisted_sample_mapping_before_native_promotion(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);media=root/"media";media.mkdir();digest=self._wav(media/"tone.wav")
            (root/"daw-session.json").write_text(json.dumps(self._session(digest)),encoding="utf-8")
            mapping={"mappingId":"sample-pad","source":{"deviceId":"pads","channel":0,"message":"note","number":36},
                "target":{"targetId":"sample.trigger","resourceId":"clip-a"},"behavior":"trigger","quantize":"off","keySync":True,"scale":"major","enabled":True}
            (root/"midi-mappings.json").write_text(json.dumps({"revision":1,"mappings":[mapping]}),encoding="utf-8")
            runtime=StageMeshRuntime(root)
            if not runtime.native.available:
                runtime.close();self.skipTest("native engine not built")
            try:
                self.assertEqual(runtime.daw_sampler_status()["registered"],1)
                self.assertEqual(runtime.midi_mapping_status()["nativeExecution"]["bindings"],1)
                runtime.native.inject_midi_input("pads","alex",0,0x90,36,100)
                deadline=time.monotonic()+.25
                submitted=0
                while time.monotonic()<deadline:
                    runtime.pump_midi_once();submitted=int(runtime.native.sampler_status().get("submitted","0"))
                    if submitted:break
                    time.sleep(.002)
                self.assertEqual(submitted,1)
                self.assertEqual(runtime.native.sampler_status()["physicalOutputsArmed"],"0")
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
