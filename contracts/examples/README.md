# Contract Test Fixtures

These fixtures are synthetic and contain no real user or tenant data.

| Fixture | Expected result | Purpose |
|---|---|---|
| experiment-package.valid.json | PASS against experiment-package.schema.v1alpha1.json | Valid Package structure |
| experiment-package.invalid.json | FAIL | Missing required model digest and unsupported runtime mode |
| runtime-event.valid.json | PASS against runtime-event-envelope.schema.v1.json | Valid event envelope |
| dc-circuit.reference-cases.json | JSON syntax check only; expert review pending | Synthetic DC circuit reference cases |

R03.23 records one-time local execution: Package Schema meta-validation and positive/negative fixtures passed; Runtime Event Schema meta-validation and positive fixture passed. This is not yet a CI run. The repository CI must repeat these assertions with pinned dependencies on every relevant change.

Additional test suites must cover semantic references, digest verification, Package dependency resolution, license policy, model compatibility, event ordering, idempotency and tenant authorization. JSON Schema alone cannot verify these domain-level constraints.
