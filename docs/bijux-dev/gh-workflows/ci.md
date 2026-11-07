---
title: Repository CI
audience: maintainers
type: operations
status: canonical
owner: bijux-dev-docs
last_reviewed: 2026-11-07
---

# Repository CI

`.github/workflows/ci.yml` validates pull requests and merge-queue candidates.
Its structure is generated from `bijux-std`; this repository owns the delegated
Make commands and native verification adapter.

## Events and admission

Pull requests and merge groups targeting `main` run the workflow. A newer commit
supersedes the previous run for the same ref. Accepted pull-request evidence is
not repeated by a push-to-main workflow. Dependabot and automated lock-refresh
pull requests retain their separate owner-review notice and skip product jobs.

## Native test verification

`continuous integration / test` accepts complete bounded worker evidence. It no
longer compiles and executes the complete Rust and Python portfolio in one job.
Each native job has a five-minute timeout and a three-minute execution target.

| Responsibility | Hosted command | Proof |
| --- | --- | --- |
| source inventory | `make gh-test TEST_CHECK=prepare` | committed source, exact lock, compiler, Python, complete target inventory and native filter |
| library preparation | `make gh-test TEST_CHECK=libraries` | shared compiled test dependencies, including binary-only workspace roots |
| runtime binaries | `make gh-test TEST_CHECK=binaries` | all-feature workspace binaries |
| maintainer and parity tools | `make gh-test TEST_CHECK=tools` | default CLI, DAG CLI and maintainer binaries |
| Rust partitions | `make gh-test TEST_CHECK=<id>` | every assigned test target and its complete compiled case catalogue |
| Python coverage | `make gh-test TEST_CHECK=python` | canonical `make test-py`, installed bridge, parity binaries, JUnit and full coverage threshold |
| terminal acceptance | `make gh-test TEST_CHECK=accept` | all producers and workers pass with complete current-source receipts |

Runtime-binary and maintainer-tool compilation run concurrently after library
preparation. Rust target partitions run with up to sixteen workers concurrently;
the Python worker runs independently. Authenticated library and binary deltas
share compilation inputs. Nested fixture builds reuse the same owned target
instead of compiling another copy inside the checkout.

All native workers use the committed `Cargo.lock`. The adapter retains
workspace-wide all-feature selection, the pinned Nextest executor, the `ci`
profile and the canonical fast filter exposed by `make gh-test-filter`.
Colliding target selectors remain together. Existing slow and ignored case
exclusions retain their governed meaning. A partition containing only existing
exclusions or an empty harness still proves that its assigned binaries compile
and have the expected catalogue; complete acceptance requires nonempty Rust and
Python case coverage across the workflow.

The Python suite remains whole so its existing coverage threshold applies to
all selected tests. The adapter does not replace its marker or coverage options.
The local `make test` and `make gh-test` commands retain the complete
single-machine native test entrypoint. Slow, ignored and frozen portfolios keep
their separate governed lanes.

## Evidence and refusal

`artifacts/native-tests/` owns plans, compilation transfers, worker receipts,
Python reports and `acceptance.json`. Workers authenticate the producer's
manifest and plan digests, source commit, lockfile, compiler and Python identity.
They verify declared source bytes before and after execution. Compilation
transfers include only owned target outputs and public registry inputs; Cargo
credentials and incremental directories are excluded.

The stable `test` check requires successful inventory, library, binary, tool,
Rust-matrix and Python jobs. Missing, duplicate, failed, stale or over-budget
receipts reject acceptance. Exact target ownership and unique compiled case
identities establish the complete native surface. Job timings must also be
reviewed against the five-minute maximum before accepting an optimization.

## Other gates and ownership

The generated formatting, lint and audit jobs retain `make fmt`, `make lint`
and `make audit`. Release-candidate formatting, all-target tests, documentation,
packaging, publication dry-runs and smoke proofs are owned by
[Release Validation](release-validation.md).

Runner, Python, Rust, executor and workflow changes belong in `bijux-std` first.
Consume its exact accepted GitHub commit and validate managed checksums when
refreshing this workflow. Repository-specific native test behavior belongs in
`.github/scripts/native_testing`, `configs/rust/native-testing.json` and the
owning Make commands. Preserve the workspace Rust/MSRV and Python compatibility
contracts when changing either boundary.
