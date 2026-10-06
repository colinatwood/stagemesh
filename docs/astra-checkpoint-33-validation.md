# Astra checkpoint 33 validation

Checkpoint 33 makes the reviewed HTTPS reverse-proxy deployment contract executable
without moving TLS or forwarded-peer trust into the StageMesh bridge.

`STAGEMESH_DEPLOYMENT_PROFILE=proxy-https` is opt-in. When selected, startup now
fails closed unless the StageMesh backend remains on loopback, API authentication is
forced, the private HTTP credential file is configured, at least one non-loopback
allowed hostname is present, every configured browser origin is exact HTTPS on an
allowed hostname, and the private per-user authorization policy plus distinct trusted
auth-proxy credential are available. Ordinary local development remains unchanged
when the profile is unset.

The bridge still does not trust `X-Forwarded-For` or similar peer headers. The reviewed
edge proxy owns TLS/firewall/authentication policy and must strip client-supplied
StageMesh privilege headers before injecting reviewed identity/internal credentials.
`packaging/reverse-proxy/README.md` documents that contract, while
`packaging/stagemesh-proxy.env.example` provides non-secret systemd settings.
The systemd unit accepts the optional `/etc/stagemesh/stagemesh.env`; it does not
create or enable a remote deployment automatically.

`scripts/stagemesh-http-qualify.py` performs two separate checks without printing
credentials. The loopback-backend probe verifies allowed Host/Origin plus valid control
credential and expects 403 for an invalid credential, hostile Host and hostile Origin.
The TLS-edge probe uses normal CA/hostname verification, requires TLS 1.2 or 1.3,
requires HSTS and verifies the existing StageMesh browser-security headers.

Six new unit tests cover strict profile validation, opt-in compatibility, header
requirements and both probes. The installer regression now verifies the helper,
proxy contract/example and optional systemd environment file are packaged.
A live reference exercise used the real StageMesh HTTP process plus a temporary local
TLS reverse proxy and locally trusted ephemeral certificate: backend authorization and
three denial probes passed, the edge certificate verified, TLS 1.3 negotiated and HSTS
plus security headers passed. This proves the deployable software contract, not a real
venue-LAN certificate, firewall, identity provider, controller workload or production
proxy configuration.

Native source was unchanged; the existing two CTest targets pass. After checkpoint 34
landed on the same source tree, the combined Python suite passed 492 tests.
