# MSI executable references

Issue [#179](https://github.com/colinatwood/stagemesh/issues/179) demonstrated that
the executable left in Tauri's build directory after bundling can differ from
the executable embedded in the MSI. Future MSI bindings must hash the payload,
not assume those bytes match.

Windows packaging runs `desktop-executable-binding.py record` with
`--extract-msi-payload`. The helper opens the MSI database read-only, resolves
the unique `stagemesh-desktop.exe` File row and its embedded Media cabinet,
then decompresses that exact cabinet member into a fresh temporary directory.
The installer is hashed before/after extraction and the payload size must agree
with the File table. No installer action or extracted executable is run.
External cabinets and unsupported layouts fail closed rather than falling back
to build output. No extra Python dependency is required.

The reference records `observation: extracted-msi-payload` and
`installerPayloadExtracted: true`, bound to installer hash, source and channel.
Both Windows channels run `tests/windows_msi_payload.py` against the generated
MSI and repeat recording with intentionally unrelated build-output bytes. The
reference must still match the actual payload. CI logs report the payload hash.

The download comparison accepts this producer observation while retaining
integrity checks for the manifest, exact installer, source and channel. Its
`candidateReferenceFromExtractedPayload` field distinguishes this reference
from the legacy post-bundle observation. The comparison itself does not extract
the MSI: its own `installerPayloadExtracted` remains false. Neither observation
authenticates the metadata or publisher, attests source provenance, checks all
installed resources, nor qualifies installation, audio or physical hardware.

NSIS still records a post-bundle build-output observation. Both Windows lanes
now require `tests/windows_nsis_payload.py` to inspect their actual generated
NSIS archive with the runner's existing 7-Zip utility. It selects one executable,
streams it without executing it, and requires its size/hash to match the reference
bound to that exact installer, source and channel. Ambiguous/unsafe members,
unexpected archive types, payload disagreement or installer mutation fail the
job. A pass establishes byte identity for that candidate's producer input and
payload; it does not change the observation into source or publisher attestation.
The required online/offline CI results remain the acceptance evidence.

Old archives and failed receipts are preserved. This change
does not retroactively make an old comparison pass or authorize replacing the
installed application. Issue #179 remains open until the real MSI lanes and
NSIS follow-up have evidence meeting its acceptance criteria.
