# Art-Net interoperability notes

StageMesh emits ArtDMX over UDP from the native engine. The transport is
deliberately narrower than a general Art-Net controller: it accepts an
explicit unicast IPv4 target, defaults to UDP port `6454`, requires explicit
arming, and rejects broadcast and multicast targets. Configuration alone never
sends lighting packets.

The packet encoder follows the interoperability shape used by the
[`hobbyquaker/artnet`](https://github.com/hobbyquaker/artnet) Node.js module:

- `Art-Net` identifier
- ArtDMX opcode `0x5000`
- protocol version 14
- sequence byte, physical byte, and 15-bit universe/port address
- even DMX payload length from 2 through 512 slots

The reference module sends changed ArtDMX values at a bounded rate and refreshes
unchanged data periodically. StageMesh sends a complete universe when a
queued lighting event changes that universe during `LIGHT_DRAIN`, and now
refreshes each Art-Net universe after four seconds of inactivity. Refreshing is
bounded by the caller’s drain cadence and does not create a background send
thread.

## Qualification procedure

1. Use a loopback or isolated lighting network first.
2. Configure a unicast Art-Net node on port `6454`.
3. Explicitly arm the StageMesh lighting output.
4. Send a known channel change and capture the UDP packet.
5. Verify the identifier, opcode, version, universe, sequence progression,
   even payload length, channel value, and packet cadence.
6. Verify that no packet is sent before arming and that broadcast/multicast
   targets are rejected.

Do not treat a packet-format or loopback result as physical stage-output
qualification. Record the node model, firmware, network topology, capture,
and observed refresh behavior separately.
