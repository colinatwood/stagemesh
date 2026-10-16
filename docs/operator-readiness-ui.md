# Operator readiness observations

The desktop workspace uses its native navigation and stage inspector. The old
`mockup-console.js` overlay is no longer loaded: it inserted a second navigation
bar, repeated readiness cards, and fixed macOS and design-validation claims.
The prototype source is retained for history but does not execute in the app.

Readiness cards distinguish live observations from acceptance work:

| Card | Evidence and meaning |
| --- | --- |
| Release Checks Required | The app cannot attest its own exact-build release checks; review the candidate's recorded evidence. |
| Native Engine Connected | The native status endpoint currently reports `available: true`. This is an engine connection observation only. |
| Native Engine Unavailable | The endpoint reports `available: false`, including its documented HTTP 503 response. Hardware state remains unverified. |
| Native Engine Status Unavailable | The request failed, timed out or returned an unsupported availability value. The UI retries. |
| Physical Loopback Required | Physical audio qualification remains open. |
| Assistive Tech Review Required | Actual NVDA/VoiceOver and operator acceptance remain open. |

The engine check runs initially and every five seconds, admits one outstanding
request, and aborts after four seconds. A failed check removes the green engine
connection state. Repeating the same result does not rewrite the polite live
region. These checks never start or stop a stream, change routing, or establish
whether physical output is running. Device-specific status remains authoritative
for those observations.

## Software validation

The Node workflow exercises connected/unavailable/unknown transitions, malformed
responses, HTTP errors, the structured unavailable response, overlapping requests,
timeout recovery and unchanged-status announcement suppression.

The real Chromium headless reference passes at 1440×900, 1024×768, 768×1024 and
390×844. Every viewport has zero horizontal overflow, one native navigation bar,
and zero prototype UI nodes. The desktop accessibility-tree reference contains
116 interactive nodes, zero unnamed interactive controls, zero ignored focusable
nodes and eight polite status regions. This is renderer evidence with the native
engine unavailable; it does not qualify hardware or a screen reader.

The Browser Reference workflow installs pinned browser tooling, runs the same
production assets against the real loopback handler, and uploads screenshots and
the JSON report on frontend/backend/helper changes. Its fetch bridge keeps the
networking boundary explicit: browser-to-LAN, TLS/IdP/firewall, native webview,
physical hardware and installed-app acceptance remain separate exercises.
