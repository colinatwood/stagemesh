# Astra checkpoint 38 validation

Updated 2026-09-13. This checkpoint qualifies the current HTTP controller/rate policy with repeatable software workloads while preserving separate physical and deployment gates.

## Deterministic rate model

The harness replays four independent controllers at 20 requests/second each beside one abusive peer at 300 requests/second for five seconds using the actual StageMesh `RequestRateLimiter` with a controlled monotonic clock. Result:

- controller requests allowed: **400**
- controller requests denied: **0**
- abusive requests allowed: **698**
- abusive requests denied: **802**

The abusive peer is processed first each 10 ms tick. The default 100 rps per-peer cap keeps that peer bounded beneath the 200 rps aggregate refill, leaving capacity for the 80 rps controller workload.

## Live local-reference workload

`python3 scripts/stagemesh-http-workload.py --json` launches the real loopback StageMesh bridge with a temporary data directory and native execution disabled, then runs normal and abusive HTTP bursts. Checkpoint reference result:

- normal mixed control requests: **120/120 HTTP 200**
- normal p50: **13.233 ms**
- normal p95: **22.903 ms**
- normal maximum: **1031.790 ms**
- abusive requests: **320**
- abusive HTTP 200: **287**
- abusive HTTP 429: **33**
- unexpected abusive statuses: **0**

The p95 gate is 1000 ms for this local reference. Individual maximum latency is reported but does not fail the run because short host scheduling stalls are not treated as a stage timing guarantee. The JSON result is preserved at `qualification/http-workload-reference.json`.

## Regression and release validation

Three workload-helper regressions cover percentile behavior, deterministic rate-policy admission and result-envelope pass/fail semantics. Full release validation passed:

- Python: **513 tests**, zero skips.
- Native CTest: **2/2**.
- Automation performance: passed.
- OpenAPI: parsed.
- JSON schemas: **117** parsed.
- Frontend JavaScript: **7/7** syntax checks passed.

## Claim boundary

The report explicitly sets `physicalControllerQualified=false` and `deployedLanQualified=false`. Physical controller timing/reconnect, independent witness/clock behavior, deployed proxy/IdP/firewall behavior and hardware/stage qualification remain open.
