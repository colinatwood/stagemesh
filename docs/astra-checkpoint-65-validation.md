# Astra checkpoint 65 validation

Checkpoint 65 adds the intake/status layer on top of checkpoint 64's evidence reviewer.

For each exact-build task, StageMesh recognizes `result.json`, `review.json` and `artifacts/`. Intake revalidates the result, hashes the evidence again, verifies the authenticated review and rejects any mismatch between the current artifacts and the set that was approved. It reports `pending`, `awaiting-review`, `approved`, `rejected`, `needs-evidence` or `invalid` and never edits backlog state.

The status document is itself bound to the plan ID and source/native-engine hashes and keeps `physicalOutputsArmed=false`.

Focused status/review/installer/package tests pass. The full release Python suite passes **631 tests with zero skips**; fresh RT native CTest passes **2/2**. Automation-performance passes, all **130 JSON schemas plus OpenAPI** parse, and all **7 frontend JavaScript files** pass syntax checking.
