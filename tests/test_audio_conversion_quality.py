import importlib.util
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import wave


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audio-conversion-quality.py"


def load_script():
    spec = importlib.util.spec_from_file_location("audio_conversion_quality", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tone(frames=48_000, sample_rate=48_000, frequency=997.0, amplitude=0.25):
    return [
        amplitude * math.sin(2.0 * math.pi * frequency * frame / sample_rate)
        for frame in range(frames)
    ]


def write_pcm16(path: Path, samples, sample_rate=48_000, channels=1):
    with wave.open(str(path), "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(2)
        target.setframerate(sample_rate)
        payload = bytearray()
        for sample in samples:
            integer = max(-32768, min(32767, round(sample * 32768)))
            payload.extend(struct.pack("<h", integer) * channels)
        target.writeframes(payload)


class AudioConversionQualityTests(unittest.TestCase):
    def setUp(self):
        self.module = load_script()

    def test_identical_capture_has_low_numeric_error_and_no_continuity_faults(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = root / "reference.wav"
            capture = root / "capture.wav"
            samples = tone()
            write_pcm16(reference, samples)
            write_pcm16(capture, samples)

            report = self.module.analyze(reference, capture)

            self.assertEqual(report["measurementStatus"], "observed")
            self.assertEqual(report["channels"][0]["gainAdjustedErrorRms"], 0.0)
            self.assertGreater(report["channels"][0]["snrDb"], 85.0)
            self.assertLess(report["channels"][0]["thdPlusNoiseDb"], -85.0)
            self.assertTrue(report["summary"]["continuousObservation"])
            self.assertEqual(report["summary"]["clippedSamples"], 0)
            self.assertFalse(any(report["qualificationClaims"].values()))
            self.assertFalse(report["evidenceBoundary"]["readyForQualificationReview"])

    def test_explicit_latency_and_gain_are_measured_without_guessing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = root / "reference.wav"
            capture = root / "capture.wav"
            samples = tone()
            latency = 53
            write_pcm16(reference, samples)
            write_pcm16(capture, [0.0] * latency + [sample * 0.5 for sample in samples])

            report = self.module.analyze(reference, capture, latency_frames=latency)

            channel = report["channels"][0]
            self.assertAlmostEqual(channel["gainRatio"], 0.5, places=4)
            self.assertGreater(channel["referenceResidualSnrDb"], 80.0)
            self.assertEqual(report["configuration"]["latencyFrames"], latency)

    def test_harmonic_and_noise_reduce_measured_quality(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = root / "reference.wav"
            capture = root / "capture.wav"
            samples = tone()
            observed = []
            for frame, sample in enumerate(samples):
                harmonic = 0.0025 * math.sin(2.0 * math.pi * 1994.0 * frame / 48_000)
                deterministic_noise = 0.0002 if frame % 2 else -0.0002
                observed.append(sample + harmonic + deterministic_noise)
            write_pcm16(reference, samples)
            write_pcm16(capture, observed)

            report = self.module.analyze(reference, capture)

            channel = report["channels"][0]
            self.assertLess(channel["snrDb"], 70.0)
            self.assertGreater(channel["thdPlusNoiseDb"], -50.0)
            self.assertLess(channel["thdPlusNoiseDb"], -30.0)

    def test_dropout_and_clipping_are_reported_as_observations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = root / "reference.wav"
            capture = root / "capture.wav"
            samples = tone()
            observed = list(samples)
            observed[10_000:10_100] = [0.0] * 100
            observed[20_000] = 1.0
            write_pcm16(reference, samples)
            write_pcm16(capture, observed)

            report = self.module.analyze(reference, capture)

            self.assertEqual(report["summary"]["dropoutRuns"], 1)
            self.assertEqual(report["summary"]["dropoutFrames"], 100)
            self.assertGreaterEqual(report["summary"]["clippedSamples"], 1)
            self.assertFalse(report["summary"]["continuousObservation"])
            self.assertFalse(report["qualificationClaims"]["conversionContinuityQualified"])

    def test_mismatched_format_and_invalid_latency_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = root / "reference.wav"
            capture = root / "capture.wav"
            write_pcm16(reference, tone())
            write_pcm16(capture, tone(sample_rate=44_100, frames=44_100), sample_rate=44_100)
            with self.assertRaisesRegex(ValueError, "sample rates must match"):
                self.module.analyze(reference, capture)
            with self.assertRaisesRegex(ValueError, "cannot be negative"):
                self.module.analyze(reference, reference, latency_frames=-1)

    def test_generation_size_limit_fails_before_allocating_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "256 MiB"):
                self.module.generate_reference(
                    Path(temporary) / "too-large.wav",
                    sample_rate=384_000,
                    duration_seconds=600,
                    channels=32,
                )

    def test_cli_generates_reference_and_writes_hashed_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = root / "reference.wav"
            report_path = root / "measurement-summary.json"
            generated = subprocess.run(
                [sys.executable, str(SCRIPT), "generate", "--output", str(reference), "--channels", "1"],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(generated.returncode, 0, generated.stderr)
            generation = json.loads(generated.stdout)
            self.assertEqual(generation["wholeCycles"], 1994)
            self.assertEqual(len(generation["sha256"]), 64)

            measured = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "analyze",
                    "--reference",
                    str(reference),
                    "--capture",
                    str(reference),
                    "--output",
                    str(report_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(measured.returncode, 0, measured.stderr)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["documentType"], "org.stagemesh.audio-conversion-measurement")
            self.assertEqual(report["inputs"]["reference"]["sha256"], generation["sha256"])
            self.assertFalse(any(report["qualificationClaims"].values()))

            overwrite = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "analyze",
                    "--reference",
                    str(reference),
                    "--capture",
                    str(reference),
                    "--output",
                    str(reference),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(overwrite.returncode, 2)
            self.assertIn("cannot overwrite", overwrite.stderr)


if __name__ == "__main__":
    unittest.main()
