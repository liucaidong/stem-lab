# Contract Test Fixtures

These fixtures are synthetic and contain no real user or tenant data.

| Fixture | Expected result | Purpose |
|---|---|---|
| experiment-package.valid.json | PASS against experiment-package.schema.v1alpha1.json | Valid Package structure |
| experiment-package.invalid.json | FAIL | Missing required model digest and unsupported runtime mode |
| runtime-event.valid.json | PASS against runtime-event-envelope.schema.v1.json | Valid event envelope |

Expected outcomes are test specifications, not evidence that a JSON Schema validator has run. The CI pipeline must execute a Draft 2020-12 compliant validator and assert both positive and negative cases.

Additional test suites must cover semantic references, digest verification, Package dependency resolution, license policy, model compatibility, event ordering, idempotency and tenant authorization. JSON Schema alone cannot verify these domain-level constraints.
