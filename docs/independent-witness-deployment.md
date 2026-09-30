# Independent witness deployment

StageMesh can use a strict **independent-witness topology** for primary/standby authority. The purpose is to make a single node, witness process, credential, or declared failure domain insufficient to manufacture authority.

This mode is intentionally stricter than the legacy shared-secret witness configuration. A production topology declares a majority quorum, one identity and one failure domain per witness, and one pairwise HMAC keyring per witness endpoint. StageMesh verifies those signed identity/failure-domain facts on every quorum response and rejects responses whose server clock exceeds the configured skew bound.

## Recommended topology

Use three witness hosts for a 2-of-3 quorum:

```text
Primary StageMesh node ─┬─ HTTPS ─ Witness A / failure domain A
                         ├─ HTTPS ─ Witness B / failure domain B
Standby StageMesh node ─┴─ HTTPS ─ Witness C / failure domain C
```

The witnesses do not render audio, run plugins or arm physical outputs. They only persist and authenticate cluster lease/fencing decisions. The practical network load is tiny; reliability and independence matter far more than bandwidth.

For production, do not place all three witnesses on the primary/standby hosts, one hypervisor, one UPS, one switch, or one failure-prone management domain and then call them independent. Configuration labels are declarations, not evidence.

## Witness host configuration

Install the StageMesh package on each witness host, create a private keyring owned by the `stagemesh` service account, and populate `/etc/stagemesh/witness.env` from `packaging/stagemesh-witness.env.example`.

Each host needs unique values for:

- `STAGEMESH_WITNESS_ID`
- `STAGEMESH_WITNESS_FAILURE_DOMAIN`
- `STAGEMESH_WITNESS_KEYRING_FILE`

Strict mode sets `STAGEMESH_WITNESS_INDEPENDENT=1`. It refuses the legacy `STAGEMESH_WITNESS_SECRET` / replication-secret fallback. The packaged `stagemesh-witness.service` binds the Python witness server to loopback. Put an HTTPS reverse proxy in front of it and expose only that TLS endpoint to the StageMesh performance nodes.

The witness keyring uses the same bounded rotating-keyring document as other cluster HMAC paths:

```json
{
  "version": 1,
  "activeKeyId": "2026-q3",
  "keys": {
    "2026-q3": "replace-with-at-least-32-printable-secret-characters"
  }
}
```

The file must be an absolute-path regular file, owned by the service effective UID, with no group/other permissions. Rotate each witness credential independently. During a rotation window, keep only the explicit old/new overlap needed for that one witness.

## StageMesh node topology

Both performance nodes receive a private topology file and set:

```text
STAGEMESH_WITNESS_TOPOLOGY_FILE=/etc/stagemesh/independent-witness-topology.json
```

See `examples/independent-witness-topology.json`.

The strict loader requires:

- an explicit majority quorum;
- unique witness URLs;
- unique witness identities;
- unique declared failure domains;
- unique per-witness keyring paths;
- a bounded `maxClockSkewMs` between 50 and 10000 ms;
- HTTPS for every non-loopback witness URL.

Plain HTTP is accepted only when `allowInsecureLoopback` is true **and** the endpoint is loopback. That exception exists solely for local reference qualification.

## Clock requirements

Witness leases contain wall-clock expiry, so the participating hosts need disciplined clocks. Use normal production time synchronization (for example NTP/chrony, or PTP where the deployment already requires it) and choose a skew bound that the deployment can actually maintain.

StageMesh measures the absolute difference between the local node clock and each signed `serverUnixMs`. A witness outside `maxClockSkewMs` does not count toward quorum. The setting is therefore a safety bound, not a knob to silence clock alarms by making the number enormous.

## Network requirements

A witness needs only low-bandwidth HTTPS request/response traffic. Prefer wired, stable connectivity. Firewall rules should allow only the StageMesh performance nodes or their trusted network segment to reach the witness TLS endpoint. Do not expose the raw loopback witness listener or publish the witness service directly to the Internet.

DNS is acceptable when its failure behavior is understood; fixed addresses are also acceptable. What matters is that a network partition cannot give both sides a majority. Avoid designing all witness paths through one switch/router/firewall if that device is itself the failure you expect quorum to survive.

## Reference qualification

Run:

```bash
/usr/libexec/stagemesh/stagemesh-witness-qualify.py
```

or from a source checkout:

```bash
./scripts/stagemesh-witness-qualify.py
```

The helper launches three separate loopback witness processes with three identities, three declared failure domains and three credentials. It verifies:

1. 3/3 acquisition forms quorum;
2. loss of one witness still permits a 2/3 named-successor transfer;
3. the successor can renew with the remaining 2/3 witnesses;
4. loss of two witnesses prevents quorum.

Its result deliberately contains:

```json
{"referenceOnly":true,"physicalIndependenceQualified":false}
```

Passing that drill proves the software topology/quorum behavior. It does **not** prove the production witnesses are truly independent.

## Production qualification still required

Before advertising production independent-witness qualification, run the same authority/recovery scenarios across the actual independent hosts and capture evidence for:

- separate host/hypervisor/power/network failure domains;
- clock skew during steady state and disturbance;
- loss of each individual witness;
- loss of two witnesses;
- primary isolation and standby promotion;
- planned handoff with one witness unavailable;
- persistently fenced-node recovery through the independent quorum;
- restart/credential-rotation behavior;
- observed program/output continuity and the fact that promotion/recovery remains physically disarmed until explicit arming policy permits it.

StageMesh status intentionally reports `physicalIndependenceQualified: false` from configuration alone. Physical independence is an evidence claim, not a JSON field humans can award to themselves.
