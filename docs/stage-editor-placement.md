# Stage Editor placement and orientation

Right-click an object type in the palette or a layout in the library to open
its options beneath the choice (kept within the visible window). Keyboard users
can focus that choice and press Shift+F10 or the Context Menu key. **Add to stage**
also opens object placement options.

1. Choose **Place on stage**, move onto the canvas, then left-click once to place.
2. Set orientation in degrees, edit the label for a single object, and adjust
   X/Y or drag the preview. A layout moves and rotates as a group; all object
   centers must remain within the stage.
3. Left-click the stage again, or choose **Save placement**, to save the local
   draft. Releasing a drag only ends the move; the following deliberate click
   saves the placement.

Left-click a saved object to reopen its options. Escape or **Cancel** discards
the preview and restores the previous draft. A layout preview replaces the
current stage only when saved. The library's existing **Apply** shortcut still
applies a preset directly.

While a placement is open, import, export, template rename, replacement and
server mutations wait for Save or Cancel. A local-storage refusal preserves the
saved draft and keeps the preview available for retry or cancellation. Local
placement saves do not create a server revision; use **Save template** afterward.
Orientation is preserved in JSON interchange and server persistence. Existing
version-1 objects without orientation retain their original appearance.

Validation: 899 general-suite tests completed with 24 environment skips, plus
the separate real Chromium placement/reopen/rotation/drag/cancel/storage-refusal
exercise. Browser Reference CI requires that exercise; it is outside general
discovery so the release suite retains its strict no-unexpected-skip rule.
The existing rendered-browser reference passed
at all four viewports with zero horizontal overflow and passing accessibility
tree checks. These software checks do not qualify installed Windows behavior,
assistive technology or physical hardware.
