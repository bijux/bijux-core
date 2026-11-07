---
title: Release Validation Workflow
audience: maintainers
type: operations
status: canonical
owner: bijux-dev-docs
last_reviewed: 2026-11-06
---

# Release Validation Workflow

`.github/workflows/release-validation.yml` verifies one committed release
candidate through bounded parallel jobs. The repository-owned adapter executes
`make gh-release-validate RELEASE_CHECK=<check>` and preserves every proof family
in `configs/dag/release/release_validation_suite.json`.

## Events and source identity

Contributor pull requests and deliberate manual dispatches run the workflow.
Dependabot pull requests remain dependency notifications. A newer run supersedes
the older run for the same Git ref. No push-to-main run repeats accepted pull
request evidence.

The candidate producer exports committed `HEAD`, applies the governed release
version and public DAG patches, and records the source, lock, archive and complete
Cargo target plan identities. A shallow checkout contains the exact commit needed
for this export. All workers authenticate the same candidate before execution.

## Bounded verification

Every job has a five-minute timeout, with a three-minute execution target. Rust
`1.86.0`, Python 3.11 and Ubuntu 24.04 remain the admitted hosted environment.

| Responsibility | Work |
| --- | --- |
| candidate | prepare one archive and complete verification plan |
| compilation | compile library test inputs and runtime/maintainer binaries separately |
| target partitions | execute every workspace Cargo target with all features and the locked graph |
| source quality | format the workspace and run workspace-wide Clippy with warnings denied |
| API documentation | build workspace Rust documentation and run all documentation tests with the unified feature graph |
| public packaging | list all public DAG packages and verify each locked publish dry-run |
| runtime boundaries | verify Python installation and the DAG CLI smoke pipeline |
| acceptance | authenticate complete results and enforce coverage, identity and timing budgets |

Independent verification jobs run concurrently. Compilation archives include only
owned target outputs and public Cargo registry inputs; the binary archive contains
changes relative to the library archive. Nested CLI fixture builds share that
authenticated target and reuse the prepared default-feature CLI binary. Incremental build directories and Cargo
credentials are excluded. A restored cache accelerates compilation; a successful
worker command and authenticated terminal result establish verification.

## Terminal evidence

The stable `validate-release-candidate` check passes only after all compilation
producers and verification workers pass. Every planned check needs exactly one
result for the current candidate. Missing, duplicate, failed, stale or over-budget
results fail acceptance. Worker artifacts retain commands and elapsed time;
`artifacts/release-validation/acceptance.json` records complete coverage and any
checks above the three-minute target.

The local `make gh-release-validate` and `make release-validate-rs` commands retain
the complete single-machine suite. The hosted partitioned adapter proves the same
release obligations with explicit ownership and bounded execution.
