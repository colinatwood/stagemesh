#!/usr/bin/env python3
"""Generate and analyze deterministic WAV evidence for AUD-034.

This tool records measurements; it never declares physical hardware qualified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import wave


DOCUMENT_TYPE = "org.stagemesh.audio-conversion-measurement"
DB_FLOOR = -300.0
MAX_CHANNELS = 32
MAX_SECONDS = 600
MAX_PCM_BYTES = 256 * 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _db(value: float) -> float:
    return DB_FLOOR if value <= 0.0 else 20.0 * math.log10(value)


def _ratio_db(numerator_power: float, denominator_power: float) -> float:
    if numerator_power <= 0.0:
        return DB_FLOOR
    if denominator_power <= 0.0:
        return -DB_FLOOR
    return 10.0 * math.log10(numerator_power / denominator_power)


def _decode_pcm(raw: bytes, sample_width: int) -> list[int]:
    if sample_width == 2:
        return [value[0] for value in struct.iter_unpack("<h", raw)]
    if sample_width == 3:
        values = []
        for offset in range(0, len(raw), 3):
            value = int.from_bytes(raw[offset : offset + 3], "little", signed=False)
            values.append(value - (1 << 24) if value & (1 << 23) else value)
        return values
    if sample_width == 4:
        return [value[0] for value in struct.iter_unpack("<i", raw)]
    raise ValueError("only 16-bit, 24-bit, and 32-bit PCM WAV files are supported")


def read_pcm_wav(path: Path) -> dict:
    path = Path(path)
    with wave.open(str(path), "rb") as source:
        channels = source.getnchannels()
        sample_width = source.getsampwidth()
        sample_rate = source.getframerate()
        frame_count = source.getnframes()
        compression = source.getcomptype()
        if compression != "NONE":
            raise ValueError(f"{path.name}: compressed WAV input is not supported")
        if channels < 1 or channels > MAX_CHANNELS:
            raise ValueError(f"{path.name}: channel count must be between 1 and {MAX_CHANNELS}")
        if sample_rate < 8_000 or sample_rate > 384_000:
            raise ValueError(f"{path.name}: sample rate is outside the 8-384 kHz measurement range")
        if frame_count < 1 or frame_count > sample_rate * MAX_SECONDS:
            raise ValueError(f"{path.name}: WAV duration must be between one frame and {MAX_SECONDS} seconds")
        expected_bytes = frame_count * channels * sample_width
        if expected_bytes > MAX_PCM_BYTES:
            raise ValueError(f"{path.name}: PCM payload exceeds the 256 MiB analysis limit")
        raw = source.readframes(frame_count)
        if len(raw) != expected_bytes:
            raise ValueError(f"{path.name}: truncated PCM data")

    integers = _decode_pcm(raw, sample_width)
    scale = float(1 << (sample_width * 8 - 1))
    deinterleaved = [list() for _ in range(channels)]
    for index, value in enumerate(integers):
        deinterleaved[index % channels].append(value / scale)
    return {
        "path": path,
        "sampleRateHz": sample_rate,
        "channels": channels,
        "bitsPerSample": sample_width * 8,
        "frames": frame_count,
        "samples": deinterleaved,
    }


def _encode_pcm24(value: float) -> bytes:
    integer = max(-(1 << 23), min((1 << 23) - 1, round(value * (1 << 23))))
    return (integer & 0xFFFFFF).to_bytes(3, "little")


def generate_reference(
    output: Path,
    *,
    sample_rate: int = 48_000,
    duration_seconds: float = 2.0,
    frequency_hz: float = 997.0,
    level_dbfs: float = -12.0,
    channels: int = 2,
) -> dict:
    if sample_rate < 8_000 or sample_rate > 384_000:
        raise ValueError("sample rate must be between 8 kHz and 384 kHz")
    if channels < 1 or channels > MAX_CHANNELS:
        raise ValueError(f"channel count must be between 1 and {MAX_CHANNELS}")
    if duration_seconds <= 0.0 or duration_seconds > MAX_SECONDS:
        raise ValueError(f"duration must be greater than zero and at most {MAX_SECONDS} seconds")
    if frequency_hz <= 0.0 or frequency_hz >= sample_rate / 2.0:
        raise ValueError("frequency must be greater than zero and below Nyquist")
    if level_dbfs > 0.0 or level_dbfs < -120.0:
        raise ValueError("level must be between -120 and 0 dBFS")

    frames = round(sample_rate * duration_seconds)
    if frames * channels * 3 > MAX_PCM_BYTES:
        raise ValueError("generated PCM payload exceeds the 256 MiB limit")
    cycles = frames * frequency_hz / sample_rate
    if not math.isclose(cycles, round(cycles), abs_tol=1e-9):
        raise ValueError("duration and frequency must produce a whole-cycle reference signal")
    amplitude = 10.0 ** (level_dbfs / 20.0)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(3)
        target.setframerate(sample_rate)
        payload = bytearray()
        for frame in range(frames):
            sample = amplitude * math.sin(2.0 * math.pi * frequency_hz * frame / sample_rate)
            encoded = _encode_pcm24(sample)
            payload.extend(encoded * channels)
        target.writeframes(payload)
    return {
        "path": output.name,
        "sha256": _sha256(output),
        "bytes": output.stat().st_size,
        "sampleRateHz": sample_rate,
        "channels": channels,
        "bitsPerSample": 24,
        "frames": frames,
        "durationSeconds": frames / sample_rate,
        "frequencyHz": frequency_hz,
        "levelDbfs": level_dbfs,
        "wholeCycles": round(cycles),
    }


def _rms(samples: list[float]) -> float:
    return math.sqrt(sum(value * value for value in samples) / len(samples))


def _dropout_runs(samples: list[float], silence_threshold: float, minimum_frames: int) -> tuple[int, int]:
    runs = 0
    frames = 0
    current = 0
    for sample in samples:
        if abs(sample) <= silence_threshold:
            current += 1
        else:
            if current >= minimum_frames:
                runs += 1
                frames += current
            current = 0
    if current >= minimum_frames:
        runs += 1
        frames += current
    return runs, frames


def _tone_metrics(samples: list[float], sample_rate: int, frequency_hz: float) -> dict:
    count = len(samples)
    mean = sum(samples) / count
    components: list[tuple[float, float]] = []
    maximum_harmonic = min(5, int((sample_rate / 2.0) // frequency_hz))
    for harmonic in range(1, maximum_harmonic + 1):
        angular = 2.0 * math.pi * frequency_hz * harmonic / sample_rate
        sine = 2.0 * sum(value * math.sin(angular * index) for index, value in enumerate(samples)) / count
        cosine = 2.0 * sum(value * math.cos(angular * index) for index, value in enumerate(samples)) / count
        components.append((sine, cosine))

    powers = [(sine * sine + cosine * cosine) / 2.0 for sine, cosine in components]
    residual_power = 0.0
    for index, sample in enumerate(samples):
        fitted = mean
        for harmonic, (sine, cosine) in enumerate(components, 1):
            angle = 2.0 * math.pi * frequency_hz * harmonic * index / sample_rate
            fitted += sine * math.sin(angle) + cosine * math.cos(angle)
        residual_power += (sample - fitted) ** 2
    residual_power /= count
    fundamental_power = powers[0]
    harmonic_power = sum(powers[1:])
    return {
        "dcOffset": mean,
        "fundamentalRms": math.sqrt(fundamental_power),
        "noiseRms": math.sqrt(residual_power),
        "harmonicRms": math.sqrt(harmonic_power),
        "snrDb": _ratio_db(fundamental_power, residual_power),
        "thdPlusNoiseDb": _ratio_db(harmonic_power + residual_power, fundamental_power),
        "thdPlusNoiseRatio": math.sqrt((harmonic_power + residual_power) / fundamental_power),
        "harmonicsAnalyzed": maximum_harmonic,
    }


def _channel_metrics(
    reference: list[float],
    capture: list[float],
    *,
    sample_rate: int,
    frequency_hz: float,
    clip_threshold: float,
    silence_threshold: float,
    dropout_minimum_frames: int,
    discontinuity_threshold: float,
) -> dict:
    reference_power = sum(value * value for value in reference)
    if reference_power <= 0.0:
        raise ValueError("reference signal has no measurable energy")
    gain = sum(expected * observed for expected, observed in zip(reference, capture)) / reference_power
    raw_error = [observed - expected for expected, observed in zip(reference, capture)]
    residual = [observed - gain * expected for expected, observed in zip(reference, capture)]
    residual_rms = _rms(residual)
    reference_rms = _rms(reference)
    capture_rms = _rms(capture)
    dropout_runs, dropout_frames = _dropout_runs(capture, silence_threshold, dropout_minimum_frames)
    adjacent_deltas = [abs(capture[index] - capture[index - 1]) for index in range(1, len(capture))]
    discontinuities = sum(delta >= discontinuity_threshold for delta in adjacent_deltas)
    tone = _tone_metrics(capture, sample_rate, frequency_hz)
    return {
        "referenceRms": reference_rms,
        "captureRms": capture_rms,
        "capturePeak": max(abs(value) for value in capture),
        "gainRatio": gain,
        "gainDb": _db(abs(gain)),
        "rawErrorRms": _rms(raw_error),
        "rawErrorPeak": max(abs(value) for value in raw_error),
        "gainAdjustedErrorRms": residual_rms,
        "gainAdjustedErrorPeak": max(abs(value) for value in residual),
        "gainAdjustedErrorDbfs": _db(residual_rms),
        "referenceResidualSnrDb": _ratio_db(reference_rms ** 2, residual_rms ** 2),
        "clippedSamples": sum(abs(value) >= clip_threshold for value in capture),
        "dropoutRuns": dropout_runs,
        "dropoutFrames": dropout_frames,
        "maximumAdjacentDelta": max(adjacent_deltas, default=0.0),
        "discontinuities": discontinuities,
        "continuousObservation": dropout_runs == 0 and discontinuities == 0,
        **tone,
    }


def analyze(
    reference_path: Path,
    capture_path: Path,
    *,
    frequency_hz: float = 997.0,
    latency_frames: int = 0,
    analysis_frames: int | None = None,
    silence_threshold: float = 1e-5,
    dropout_minimum_frames: int = 32,
    discontinuity_threshold: float = 0.25,
) -> dict:
    reference = read_pcm_wav(reference_path)
    capture = read_pcm_wav(capture_path)
    if reference["sampleRateHz"] != capture["sampleRateHz"]:
        raise ValueError("reference and capture sample rates must match")
    if reference["channels"] != capture["channels"]:
        raise ValueError("reference and capture channel counts must match")
    if latency_frames < 0:
        raise ValueError("latency frames cannot be negative")
    if frequency_hz <= 0.0 or frequency_hz >= reference["sampleRateHz"] / 2.0:
        raise ValueError("fundamental frequency must be greater than zero and below Nyquist")
    if silence_threshold <= 0.0 or silence_threshold >= 1.0:
        raise ValueError("silence threshold must be between zero and one")
    if dropout_minimum_frames < 2:
        raise ValueError("dropout minimum must be at least two frames")
    if discontinuity_threshold <= 0.0 or discontinuity_threshold > 2.0:
        raise ValueError("discontinuity threshold must be greater than zero and at most two")

    available = min(reference["frames"], capture["frames"] - latency_frames)
    if available <= 0:
        raise ValueError("latency leaves no captured frames to analyze")
    if analysis_frames is None:
        rounded_frequency = round(frequency_hz)
        if not math.isclose(frequency_hz, rounded_frequency, abs_tol=1e-9):
            raise ValueError("automatic coherent window selection requires an integer-Hz fundamental")
        period_frames = reference["sampleRateHz"] // math.gcd(reference["sampleRateHz"], rounded_frequency)
        analysis_frames = available - available % period_frames
    if analysis_frames <= 0 or analysis_frames > available:
        raise ValueError("analysis frame count must fit both aligned inputs")
    cycles = analysis_frames * frequency_hz / reference["sampleRateHz"]
    if not math.isclose(cycles, round(cycles), abs_tol=1e-9):
        raise ValueError("analysis window must contain a whole number of fundamental cycles")

    clip_threshold = 1.0 - 1.0 / float(1 << (capture["bitsPerSample"] - 1))
    channels = []
    for channel in range(reference["channels"]):
        expected = reference["samples"][channel][:analysis_frames]
        observed = capture["samples"][channel][latency_frames : latency_frames + analysis_frames]
        channels.append({
            "channel": channel + 1,
            **_channel_metrics(
                expected,
                observed,
                sample_rate=reference["sampleRateHz"],
                frequency_hz=frequency_hz,
                clip_threshold=clip_threshold,
                silence_threshold=silence_threshold,
                dropout_minimum_frames=dropout_minimum_frames,
                discontinuity_threshold=discontinuity_threshold,
            ),
        })

    report = {
        "documentType": DOCUMENT_TYPE,
        "schemaVersion": 1,
        "backlogIds": ["AUD-034"],
        "measurementStatus": "observed",
        "inputs": {
            "reference": {
                "path": Path(reference_path).name,
                "sha256": _sha256(Path(reference_path)),
                "bytes": Path(reference_path).stat().st_size,
            },
            "capture": {
                "path": Path(capture_path).name,
                "sha256": _sha256(Path(capture_path)),
                "bytes": Path(capture_path).stat().st_size,
            },
        },
        "format": {
            "sampleRateHz": reference["sampleRateHz"],
            "channels": reference["channels"],
            "referenceBitsPerSample": reference["bitsPerSample"],
            "captureBitsPerSample": capture["bitsPerSample"],
            "referenceFrames": reference["frames"],
            "captureFrames": capture["frames"],
        },
        "configuration": {
            "fundamentalHz": frequency_hz,
            "latencyFrames": latency_frames,
            "analysisFrames": analysis_frames,
            "wholeCycles": round(cycles),
            "silenceThreshold": silence_threshold,
            "dropoutMinimumFrames": dropout_minimum_frames,
            "discontinuityThreshold": discontinuity_threshold,
            "decibelFloor": DB_FLOOR,
        },
        "channels": channels,
        "summary": {
            "maximumGainAdjustedErrorRms": max(item["gainAdjustedErrorRms"] for item in channels),
            "minimumReferenceResidualSnrDb": min(item["referenceResidualSnrDb"] for item in channels),
            "minimumToneSnrDb": min(item["snrDb"] for item in channels),
            "maximumThdPlusNoiseDb": max(item["thdPlusNoiseDb"] for item in channels),
            "clippedSamples": sum(item["clippedSamples"] for item in channels),
            "dropoutRuns": sum(item["dropoutRuns"] for item in channels),
            "dropoutFrames": sum(item["dropoutFrames"] for item in channels),
            "discontinuities": sum(item["discontinuities"] for item in channels),
            "continuousObservation": all(item["continuousObservation"] for item in channels),
        },
        "qualificationClaims": {
            "conversionNumericErrorQualified": False,
            "conversionSnrQualified": False,
            "conversionThdPlusNQualified": False,
            "conversionContinuityQualified": False,
            "physicalHardwareQualified": False,
        },
        "evidenceBoundary": {
            "softwareMeasurementComplete": True,
            "thresholdsApplied": False,
            "ownerReviewComplete": False,
            "readyForQualificationReview": False,
            "statement": "Metrics are observations only; real converter routing, accepted thresholds, and owner review are external requirements.",
        },
    }
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate", help="write a deterministic 24-bit PCM sine reference")
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--sample-rate", type=int, default=48_000)
    generate.add_argument("--duration", type=float, default=2.0)
    generate.add_argument("--frequency", type=float, default=997.0)
    generate.add_argument("--level-dbfs", type=float, default=-12.0)
    generate.add_argument("--channels", type=int, default=2)

    measure = subparsers.add_parser("analyze", help="measure an aligned converter capture")
    measure.add_argument("--reference", type=Path, required=True)
    measure.add_argument("--capture", type=Path, required=True)
    measure.add_argument("--output", type=Path)
    measure.add_argument("--frequency", type=float, default=997.0)
    measure.add_argument("--latency-frames", type=int, default=0)
    measure.add_argument("--analysis-frames", type=int)
    measure.add_argument("--silence-threshold", type=float, default=1e-5)
    measure.add_argument("--dropout-minimum-frames", type=int, default=32)
    measure.add_argument("--discontinuity-threshold", type=float, default=0.25)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "generate":
            result = generate_reference(
                args.output,
                sample_rate=args.sample_rate,
                duration_seconds=args.duration,
                frequency_hz=args.frequency,
                level_dbfs=args.level_dbfs,
                channels=args.channels,
            )
        else:
            if args.output and args.output.resolve() in {
                args.reference.resolve(),
                args.capture.resolve(),
            }:
                raise ValueError("measurement output cannot overwrite an input WAV file")
            result = analyze(
                args.reference,
                args.capture,
                frequency_hz=args.frequency,
                latency_frames=args.latency_frames,
                analysis_frames=args.analysis_frames,
                silence_threshold=args.silence_threshold,
                dropout_minimum_frames=args.dropout_minimum_frames,
                discontinuity_threshold=args.discontinuity_threshold,
            )
        encoded = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if args.command == "analyze" and args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded, encoding="utf-8")
        else:
            print(encoded, end="")
        return 0
    except (OSError, ValueError, wave.Error) as exc:
        print(f"audio conversion measurement failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
