# Audio conversion measurement (AUD-034)

`scripts/audio-conversion-quality.py` generates a deterministic reference WAV and analyzes an aligned converter capture. It produces numeric conversion error, SNR, THD+N, clipping, dropout, and sample-discontinuity observations with SHA-256 provenance.

The report is measurement evidence, not a qualification verdict. The tool deliberately leaves every `qualificationClaims` value false. Real converter routing, accepted thresholds, review of the captured files, and an owner-approved qualification report remain external requirements.

## Required bench

- Apogee BOOM connected directly to an Apple Silicon Mac running macOS 14 or newer with a known-good USB-C data cable.
- Current compatible Apogee Control 2 software, BOOM firmware, and macOS microphone permission for the recording application.
- One balanced 6.35 mm (1/4-inch) TRS cable from a BOOM line output to a BOOM line input.
- Input configured for line level with 48 V phantom power off; speaker and headphone monitoring muted; fixed output and input gain recorded in the evidence notes.
- Output and input clocked at 48 kHz. Disable automatic gain, noise suppression, normalization, sample-rate conversion, and other signal processing in the capture path.
- A clean capture application capable of recording 24-bit PCM WAV without processing. Preserve its name and version in the evidence notes.

This bench unlocks physical DAC-to-ADC loopback observations for the BOOM path. It does not qualify speakers, microphones, audible monitoring, unsupported sample rates, or other interfaces.

## Generate the reference

From a clean checkout:

```bash
python scripts/audio-conversion-quality.py generate \
  --output evidence/aud-034/reference-997hz-minus12dbfs.wav \
  --sample-rate 48000 \
  --duration 2 \
  --frequency 997 \
  --level-dbfs -12 \
  --channels 2
```

The default two-second signal contains exactly 1,994 cycles, allowing leakage-free spectral measurement. Play this file without gain or format conversion and record the physical output-to-input loop into `capture.wav` at 48 kHz. Keep the unmodified reference and capture WAV files.

## Establish alignment

Measure the integer frame offset from the beginning of the reference signal to the beginning of the captured signal. Supply that offset with `--latency-frames`; the analyzer does not guess latency. If the capture starts immediately, use zero.

The reference and capture must have the same sample rate and channel count. Their bit depths may differ. The default analysis window is the longest aligned whole-cycle window shared by both inputs. Use `--analysis-frames` only when the selected frame count also contains a whole number of 997 Hz cycles.

## Analyze the capture

```bash
python scripts/audio-conversion-quality.py analyze \
  --reference evidence/aud-034/reference-997hz-minus12dbfs.wav \
  --capture evidence/aud-034/capture.wav \
  --latency-frames 0 \
  --frequency 997 \
  --output evidence/aud-034/measurement-summary.json
```

The report contains per-channel and worst-case summary values:

- raw and gain-adjusted RMS/peak numeric error;
- gain and reference-residual SNR;
- tone SNR and THD+N from coherent fundamental/harmonic fitting;
- clipped samples, near-silent dropout runs, maximum adjacent delta, and discontinuity count;
- exact input byte counts and SHA-256 digests;
- explicit false qualification claims and the remaining review boundary.

The numeric floor for mathematically zero error is -300 dB. Harmonics through the fifth, or through the last harmonic below Nyquist, are included. The default continuity observation flags at least 32 consecutive samples at or below `1e-5` full scale and adjacent jumps of at least `0.25` full scale; preserve any overrides in the generated report.

## Evidence package and review

Retain these artifacts together:

1. `reference-997hz-minus12dbfs.wav` and the analyzer's printed generation metadata;
2. the unmodified `capture.wav`;
3. `measurement-summary.json`;
4. bench notes containing macOS version, BOOM serial/firmware, Apogee Control version, cable, routing, gain positions, capture application/version, permissions, and UTC capture time;
5. a separately reviewed qualification report that states accepted thresholds and identifies each supported conversion path tested.

These satisfy the shape of the `conversion-evidence` and `measurement-summary` inputs. AUD-034 remains blocked until the physical run, threshold decision, and qualification report are complete for every claimed path.
