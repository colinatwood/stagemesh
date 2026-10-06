# Reviewed TLS reverse-proxy contract

StageMesh does not terminate public/private-LAN TLS in the Python bridge. For a
reviewed remote browser deployment, keep `stagemesh.service` bound to loopback and
select `STAGEMESH_DEPLOYMENT_PROFILE=proxy-https`.

The edge proxy MUST:

1. terminate certificate-verified TLS 1.2 or TLS 1.3 on the operator hostname;
2. add `Strict-Transport-Security` with a non-zero `max-age` once hostname/certificate
   operations are stable;
3. preserve the external `Host` header expected by `STAGEMESH_ALLOWED_HOSTS`;
4. never trust or forward client-supplied `X-StageMesh-Authenticated-User`,
   `X-StageMesh-Auth-Proxy-Token`, `X-StageMesh-Admin-Token`,
   `X-StageMesh-Adapter-Token`, witness/replication secrets, or any similar
   privilege-bearing internal header;
5. authenticate the human upstream, then inject the exact reviewed user identity
   plus the private auth-proxy credential when per-user mutations are allowed;
6. inject or otherwise provide the private StageMesh control credential to backend
   API requests. The browser must not learn that backend credential;
7. connect only to the loopback StageMesh backend. Do not make the backend itself a
   second LAN listener;
8. preserve SSE streaming without response buffering and use timeouts compatible
   with long-lived event streams;
9. apply an ingress/firewall policy outside StageMesh rather than teaching the
   bridge to trust `X-Forwarded-For` or other forwarded peer headers.

`packaging/stagemesh-proxy.env.example` contains the non-secret service settings.
The credential and authorization files must satisfy StageMesh's existing private
file checks. A root-owned parent directory with atomic, service-UID-owned 0600 file
replacement is the expected rotation pattern.

Run on the proxy/backend host after deployment:

```sh
/usr/libexec/stagemesh/stagemesh-http-qualify.py \
  --backend-url http://127.0.0.1:8765 \
  --edge-url https://stage-console.internal
```

The helper prints no tokens. The backend probe checks allowed Host/Origin, valid and
invalid control credentials, hostile Host/Origin rejection and StageMesh security
headers. The edge probe uses the platform CA store and hostname verification, then
requires TLS 1.2/1.3, HSTS and the browser security headers. This is deployment
security evidence, not controller-load, hardware, RF or show qualification.
