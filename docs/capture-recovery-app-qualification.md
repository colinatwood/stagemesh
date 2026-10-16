# Installed-app BOOM input recovery exercise

This is a pending target-host exercise for the combined recovery implementation.
PR #167 adds the explicit input recovery card; PR #168 isolates audio inventory
and servicing from MIDI enumeration instability. Both are present at source
`2200603615f74525326b306fce0ca8051bf5dbe8`. Use a desktop candidate built from
a recorded descendant containing both changes and the Connection details
follow-up described below. The baseline itself predates that panel. Do not mix
installers or evidence from independent PR builds.

## Prepare and bind the candidate

Record the source SHA, Desktop workflow run, Windows distribution channel,
artifact manifest and installer SHA-256, host/driver versions, and install result.
Verify the bundle with `scripts/verify-desktop-download.py` before installation.
Keep private device identifiers and host details in the private evidence store.
Earlier private helper run `38789578317` is baseline helper evidence only.

Open the installed app and select BOOM as input slot 0 under Audio devices.
Keep input route gain at zero and all physical playback/lighting outputs disarmed.
Use a supported format/rate; record any explicitly enabled conversion policy.
In Input connection, use Connect input once and verify Capture active. Status
polling must never issue a capture activation by itself.

Candidates containing the input-observations follow-up also expose **Connection
details** under that card. The panel reports callback-counter comparisons,
configured rate/channels/period/format and reported xruns/dropped/queued frames.
Unreported values are not zero. This is read-only status, not captured audio or
an audio-quality result. The status request has a six-second deadline; failure
marks the readings stale and disables reconnect until a fresh status succeeds.

## Repeat three physical cycles

1. Disconnect BOOM while capture is active. Observe the Input connection card
   without using Refresh or reopening the application. It must report the
   selected input disconnected/unverified and disable its connection action.
   Capture must stop; a different connected input must not substitute.
2. Reconnect the same BOOM. Record cable insertion and the first Ready to
   connect display times. Discovery may take longer than the two-second UI
   polling interval; preserve the measured wait rather than assuming a bound.
   Capture must remain stopped until an explicit click. Connection details can
   show time from the first unverified UI sample to the first verified return;
   this is not anchored to cable-insertion time and is not cable-to-ready latency.
3. Click Reconnect input once. Record click and Capture active display times
   separately from device discovery. Confirm the selected input remains BOOM,
   and expand Connection details. A successful cycle requires a physical execution
   backend and at least two fresh active status samples showing increasing callback
   counts after rearm, not just an ACTIVE label. The activation response alone
   cannot reuse pre-rearm counters. Record drops, xruns and any errors without
   capturing audio. Read-only `/api/v1/audio/input` diagnostics can also be preserved
   privately if available. Connect response time measures request-to-acknowledgement
   and excludes route-confirmation wait; it is not first-callback or audio latency.
4. Repeat until three complete cycles are observed. Finally use Deactivate
   input and confirm capture remains idle and outputs remain disarmed.

Keep the per-cycle evidence in this shape:

| Cycle | Disconnect recognized | Device-ready wait | Click-to-active wait | Fresh callback delta | Drops/xruns/errors | Explicit rearm only |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Pending | Pending | Pending | Pending | Pending | Pending |
| 2 | Pending | Pending | Pending | Pending | Pending | Pending |
| 3 | Pending | Pending | Pending | Pending | Pending | Pending |

If return stays unverified, record the failure and leave capture stopped. Do not
change the desired input to make a failed cycle pass. Wrong-device or ambiguous
identity, automatic restart, capture continuing after loss, or a false active
result fails this exercise. Stop and preserve the transcript/status evidence.

The zero-gain exercise does not test the nonzero-route confirmation in a live
signal path. Software regression coverage checks confirmation, stale selection
and stale route refusal; physical routing requires its own supervised exercise.
This result also cannot qualify audible/recording quality, latency/dropout soak,
NVDA/VoiceOver announcements, signing, clean-host lifecycle, macOS churn, or
public release readiness. Keep those backlog gates open.
