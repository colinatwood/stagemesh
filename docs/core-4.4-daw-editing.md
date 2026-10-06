# Core 4.4 DAW media and editing

Media inspection accepts WAV files only from the configured StageMesh media directory. It hashes the complete source, reads bounded PCM metadata, converts sample counts into the canonical 192 kHz timeline, and creates bounded min/max waveform peaks. It does not copy, rewrite, decode into the live graph, or arm output hardware.

Arrangement edits remain non-destructive. Trim advances source offset and clip placement, split creates two references into the same source, and fades are execution metadata. Undo and redo restore complete normalized session snapshots but always issue a new revision so optimistic concurrency never moves backward.

Move edits relocate a clip on the canonical timeline and may transfer it to a
compatible track. The server applies deterministic frame-grid snapping, sorts the
destination lane, records one undo snapshot, and rejects stale `expectedRevision`
values before mutation. Audio clips may move between audio/aux tracks and MIDI
clips between MIDI tracks; incompatible moves fail closed. The browser exposes
pointer dragging with a live visual offset, beat/sixteenth/bar/off grids, Arrow-key
nudge, and Alt+Arrow 256-frame fine movement. These gestures do not arm playback.

Selected clips expose start/end trim handles plus bracket-key equivalents. Resize
requests carry both boundaries in canonical frames, use the same server-side snap
grid and revision fence, and create one undo entry. This alpha operation is
intentionally trim-only: it cannot extend beyond the clip's currently referenced
source range because source-length evidence is not guaranteed in every portable
session. Start-edge trims advance the source offset and preserved fade-span offset.

Shift/Ctrl/Command-click builds a persistent clip selection. Dragging or nudging
any selected member moves the complete selection with one `moveMany` request.
The earliest clip is the deterministic snap anchor; the applied delta is shared by
every member, preserving their relative timing. Commands are limited to 256 unique
clips and one hour of displacement. The runtime resolves and validates the entire
set, the revision, and the timeline boundary before mutation, then creates exactly
one undo snapshot. Group moves stay on their existing tracks in this slice; mixed
cross-track transfer remains disabled until destination mapping is explicit.

Portable sessions now normalize up to 1,024 uniquely identified timeline markers.
Markers carry a canonical non-negative frame, bounded name, and `note`, `section`,
or `cue` kind. Add, snapped move, and delete operations require the current session
revision and share the DAW undo history. The browser marker rail supports creation,
locating the playback-range start, pointer movement, and confirmed deletion. Marker
commands alter arrangement metadata only; locating does not seek the native engine
or arm outputs.

Each track may carry up to 4,096 normalized volume automation points. Points have
stable bounded IDs, unique canonical-frame positions, finite gain values from 0
through 2, and explicit linear interpolation. Legacy points without IDs receive
deterministic IDs during normalization. Revision-checked upsert/delete operations
share session undo history and validate collisions before mutation. The visual lane
supports track selection, precise numeric entry, point selection/deletion, and
two-dimensional pointer movement. Both native arrangement preparation and offline
export consume the same normalized point list and deterministic evaluator. Editing
automation changes metadata only and never arms playback.

The render plan carries fade metadata to the later renderer/effect-chain adapter. Core 4.4 validates this plan but does not claim that referenced media was rendered until a renderer supplies execution evidence.
