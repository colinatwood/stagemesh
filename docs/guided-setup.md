# Guided connection setup and workspace menus

The application now opens **Setup** on first use. The top menu selects one
workspace at a time, keeping unrelated controls out of the current screen.

| Workspace | Controls |
| --- | --- |
| Setup | Guided input, output, MIDI, lighting and baseline review |
| Stage Editor | Layout design, object placement and template storage |
| Show Control | Transport, performer map, personal monitors and sample launcher |
| Studio | Separate menus for arrangement, automation, rendering/recording and recovery |
| Devices | Separate menus for input, output, MIDI, lighting, preferences, compatibility, system capacity and advanced controls |
| Reports | Readiness notes, advisor and activity |

## Setup flow

1. **Audio input:** choose a connected input and performer/source. Saving sets
   the primary input's main-mix route gain to zero and stores the selection.
2. **Audio output:** choose a connected playback device and limiter ceiling.
3. **MIDI:** bind a connected controller to a performer. Additional controllers
   and MIDI Learn remain in Devices.
4. **Lighting:** store a unicast target, protocol, port and universe, or skip.
5. **Review:** read the current configuration and stream state. Completing the
   baseline requires the native engine/discovery, known stopped streams,
   disarmed lighting and a muted input route. A non-skipped device selection
   must still be connected; ambiguous audio identities are refused.

Each Save applies only its own step through the existing authenticated,
revision-checked command path. A conflict or refusal keeps that step open.
Skip retains existing settings and is disclosed in the review. Back lets you
revisit choices. Detection requests time out after six seconds; superseded
responses cannot overwrite a newer step.

Next, Skip, navigation and Finish never activate streams or arm lighting. If
the review finds active streams, its explicitly confirmed Stop action can stop
capture, audio output and lighting; partial refusal remains visible. Finish
reads current state again before saving the local UI review preference. That
preference contains no device identities and grants no hardware authority.
It is not proof of a physical test, signing, source provenance or readiness.

After setup, choose **Devices → Audio input** to begin the installed-app BOOM
exercise. Input/output activation and route acknowledgement retain their
existing backend guards. Keyboard transport shortcuts are limited to the
visible Show Control workspace. Unfinished stage edits block leaving the
editor until saved or cancelled.

## Verification

- General Python suite: 901 tests completed, with 24 environment skips.
- Four rendered reference viewports: 1440×900, 1024×768, 768×1024 and 390×844;
  no horizontal overflow, and the setup Start button fits the initial viewport.
- Real Chromium exercises cover the complete setup flow, failed saves,
  one-workspace visibility, unique control IDs, menu switching without writes,
  state changing before Finish, confirmed stop-only requests, and preservation
  of unfinished stage edits. Browser Reference CI requires these exercises.
- Existing stage placement and rendered accessibility reference checks remain
  required. The selected workspace exposes a connection-status live region and
  its own feedback; hidden workspaces do not remain in the accessibility tree.

Installed Windows acceptance and participant-assisted BOOM cycles remain
pending until a candidate containing this UI is built and installed. The MSI
payload/reference discrepancy remains tracked separately in issue #179.
