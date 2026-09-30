# StageMesh hardware qualification bench kit

Status: blocked on access to physical equipment. No hardware is qualified by this kit.
Baseline source checkpoint: Core 5.10.5, engine handshake 5.0, public ABI 1.67.

## Observed preflight

On 2026-09-11, `python3 scripts/stagemesh-qualify.py` found zero sound cards,
zero Bluetooth controllers, zero candidate UWB serial devices, and no
`bluetoothctl`. `/dev/snd` and USB device passthrough were not exposed in this
environment. The machine reported Linux 6.18.35 x86_64. This observation concerns
the assistant execution environment, not the user's stage computer.

The source baseline passed software gates previously. That evidence does not
measure hardware performance. The included analyzer computes statistics from
supplied timing samples; it does not itself capture hardware, authenticate sample
provenance, measure acoustic latency or certify a device.

## First bench session: wired audio

Start with one named interface on the intended Linux host. Record model, firmware,
driver, kernel, connection, input/output channel pair, clock source, sample rate
and period size in `run-manifest-template.json`. Use a line-level loopback appropriate
to the interface, with speakers and performer monitors disconnected. Record the
actual routing and measurement method; never connect a speaker-level output to a
line input. Explicitly arm only the selected bench channels through the existing
application controls.

1. Run the platform probe below on that host. Save its unedited output.
2. Build Core with qualification probes using the complete Core source archive.
   Record the engine handshake and audit status before and after each run.
3. Capture a known impulse or repeatable test sequence through physical output
   and input. Keep the raw recording and reference. Derive round-trip delay from
   their sample offset and actual capture rate. Do not call half the round-trip
   delay a measured one-way delay without separate clock/path calibration.
4. Repeat for each intended native sample rate and period size. Begin with the
   interface's supported 48 kHz mode, then test other supported modes needed by
   the show, including 192 kHz only if the interface supports it. The internal
   192 kHz engine domain does not establish physical-device capability.
5. Under a representative session and plugin load, record xruns, underruns,
   recording gaps, nonfinite samples, callback deadline misses, allocation/lock
   attempts, and latency distribution. Record callback counts so unused probes
   cannot be mistaken for clean results.
6. Perform controlled disconnect/reconnect and process-restart tests with bench
   outputs only. Confirm silence/disarm and explicit reactivation behavior.
7. Run a sustained session covering the expected show duration plus an agreed
   margin. Record the actual duration and every discontinuity.

Choose numerical acceptance limits before measurements, per intended route/use.
The supplied manifest deliberately leaves them null. A missing limit, unexercised
path, missing raw evidence or unexplained dropout leaves that configuration
unqualified. A result applies only to the tested configuration and workload.

## Following sessions

| Area | Required evidence |
| --- | --- |
| MIDI | Named controller/transport; input-to-action timing against a calibrated reference; pad, knob and slider bursts; reconnect; queue drops and mapping continuity |
| LE Audio | Controller and endpoint models/firmware; verified BAP/ISO support; codec, frame duration, interval and presentation settings; actual end-to-end delay, loss and drift under representative RF conditions |
| UWB | Identified radio and timestamp adapter; paired clock observations with units and uncertainty; sequence gaps, range/clock error, holdover and obstruction tests |
| Combined LE/UWB | Correlated raw observations from both radios; device clock calibration; synchronization error over load, distance and interference changes |
| Two-node handoff | Separate hosts and independent witnesses; documented clock setup; source last-output and target first-output observations; physical gap/overlap; witness/network/process failure tests |

Run wired audio first to establish a baseline before introducing radio timing.
Discovery of a serial port does not identify or qualify a UWB radio. Controller
discovery does not prove LE Audio BAP support. A named device in an analyzer report
is operator-supplied metadata, not verified hardware provenance.

## Commands and returned evidence

Run from the kit root on the bench host (Python is required):

```sh
python3 scripts/stagemesh-qualify.py > platform-observation.json
```

For LE/UWB only, an actual timestamp adapter must capture JSON Lines records with
`sequence`, `transportLatencyNs`, `jitterNs`, and `clockOffsetNs`. Keep the original
capture file. The kit does not supply a universal device driver or capture adapter.
Then use the existing analyzer, substituting real paths, IDs and measured duration:

```sh
python3 scripts/stagemesh-hardware-bench.py --input captured.jsonl --source hardware --duration-ms ACTUAL_DURATION_MS --uwb-device ACTUAL_UWB_ID --le-controller ACTUAL_LE_ID --output timing-summary.json
```

Do not label synthetic/loopback fixtures as hardware evidence. The analyzer's
`measured-hardware` label is not an acceptance verdict. Review finite values,
sequence continuity, device identity, provenance and pre-agreed limits separately.

Return the filled manifest, platform observation, raw captures, timing summaries,
engine audit snapshots, and run notes. The first missing information is the bench
computer OS/kernel and the audio-interface model; LE/UWB device models are needed
before selecting their capture adapters. Authorized rejoin of a persistently
fenced node remains unfinished software work and must not be improvised during
handoff testing.

## HTTP controller/rate workload reference

Run `python3 scripts/stagemesh-http-workload.py --json` from the repository root.
The harness records normal loopback control responsiveness and abusive-rate containment
using the current HTTP policy. `http-workload-reference.json` is the checkpoint-38
reference result; it is not physical-controller, LAN, proxy/IdP/firewall or hardware
qualification.
