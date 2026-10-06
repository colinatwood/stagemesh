# Core 4.1 session channel

`UPPF` is a transport-neutral authenticated envelope for post-handshake UPP control messages. It is not a new network transport and does not replace TLS, DTLS, EDHOC/OSCORE or platform-local protected IPC.

The fixed header is 84 bytes in network byte order:

| Field | Size |
| --- | ---: |
| Magic `UPPF` | 4 |
| Version, flags, header size | 4 |
| Session ID | 16 |
| Key epoch | 8 |
| Sequence | 8 |
| Capability ID | 8 |
| Payload size | 4 |
| HMAC-SHA256 tag | 32 |

Payloads are bounded to 4,096 bytes. Version 1 flags must be zero. The authentication tag covers the complete prefix and payload. Directional keys are derived from the root key, Core 4.0 transcript hash, key epoch and direction label.

Receivers enforce a strictly increasing sequence watermark. Key rotation retains the immediately previous epoch only for a bounded configured sequence grace. Checkpoints are authenticated and cannot change the session identity, transcript or negotiated capability set.

The channel authorizes only capability IDs established by the session negotiation. Successful frame authentication never grants authority to operate physical outputs.

Run the independent vector runner with:

```bash
python3 scripts/stagemesh-channel-conformance.py
```
