# Core 5.0 MIDI Learn and master musical sync

Core 5.0 treats controller mapping as a musician-facing action. Select a target, enter Learn mode and touch one meaningful controller. The next note-on, control-change, pitch-bend or program message captures the device identity, zero-based MIDI channel, message type and control number. Note-off, unsupported messages and a non-selected device are ignored. Relearning one physical source replaces its former assignment.

Mappings are portable `org.upp.midi-mapping-set` documents saved independently from transient device attachment. A disconnected controller can return without losing its map. The target catalog supplies useful defaults for pads, sliders and knobs while preserving explicit behavior, range, curve, quantization, scale and key-sync metadata.

Mapped triggers can run immediately or on the next master quarter, eighth, sixteenth or thirty-second-note boundary. Boundaries use the authoritative master BPM and StageMesh Show Time; they do not use browser or controller arrival time. A stopped transport executes immediately because its Show Time cannot advance to a future boundary.

Key sync projects mapped note/sample/synth intent to the nearest pitch in the selected major, minor or chromatic scale rooted at the show's master key. Both input and output notes plus the semitone displacement remain visible. Raw performer MIDI and auto-notation are never rewritten, and acoustic performers are not falsely claimed to have been pitch-corrected.

Continuous mappings scale MIDI values into target ranges. Filter cutoff uses logarithmic scaling; resonance, pitch, volume, pan and tempo use bounded target ranges. Common endless-encoder CC values are recognized as relative movement and accumulate from a bounded midpoint. Native parameter actions enter the same Show-Time automation seam as cues and DAW automation. Sampler and looper mappings bind a concrete selected DAW clip to the native playback producer rather than storing a vague “selected sample” instruction.

## Safety boundary

- Saving or executing a mapping does not arm a physical audio, MIDI or lighting output.
- The original event remains recorded even when a mapped action is key-corrected.
- Pending actions are bounded and observable.
- Real controller ergonomics, encoder modes and hardware timing require qualification with the intended controller and driver.
