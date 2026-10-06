# Core 4.0 authenticated interoperability

Core 4.0 binds the complete participant offer, target identity, authority epoch, monotonic sequence, nonce, validity window and authentication metadata into one canonical SHA-256 transcript. The development bridge authenticates that digest with HMAC-SHA256. Production extensions may replace the verifier with hardware-backed asymmetric signatures through the provider-neutral ABI; authentication algorithms are not hard-coded into show semantics.

The design follows the transcript-binding and downgrade-resistance principles documented for TLS 1.3 in RFC 8446. It does not claim TLS wire compatibility. Constrained transports may instead host UPP messages inside a standardized secure channel such as EDHOC/OSCORE rather than inventing a new key exchange.

Session lifecycle is `offered → authenticated → negotiated → consented → active → expired`. Expiry, replay, authority-epoch changes, profile revisions and capability-registry revisions invalidate activation. A session never grants physical output authority.

Profile projection produces a digest-bound preview. Role, venue or session values that displace a durable user choice require explicit consent. User accessibility preferences outrank cosmetic venue values. Unknown profile data remains preserved.

The conformance runner executes canonical authentication, tamper, expiry, target, replay, downgrade, capability and profile-projection cases:

```bash
python3 scripts/stagemesh-conformance.py
```

The hardware bench analyzer consumes adapter-captured JSON Lines evidence:

```bash
python3 scripts/stagemesh-hardware-bench.py --input capture.jsonl --source hardware \
  --uwb-device /dev/ttyACM0 --le-controller hci0 --duration-ms 60000
```

`--source loopback` is always marked `simulation-only`. `--source hardware` requires explicit UWB and LE controller identities and at least one valid sample before `measured=true`. Even measured reports retain `physicalOutputsArmed=false`.

References:

- RFC 8446, TLS 1.3: https://www.rfc-editor.org/rfc/rfc8446
- RFC 9528, EDHOC: https://www.rfc-editor.org/rfc/rfc9528
- FiRa specifications and UCI overview: https://www.firaconsortium.org/resource-hub/specifications
- Linux `socket(2)` manual: https://www.kernel.org/doc/man-pages/online/pages/man2/socket.2.html
