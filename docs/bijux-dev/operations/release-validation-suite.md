---
title: Release Validation Suite
audience: maintainers
type: operations
status: canonical
owner: bijux-dev-docs
last_reviewed: 2026-11-06
---

# Release Validation Suite

The release validation suite answers one narrow question: can the committed
Rust release candidate be built, tested, documented, packaged, and dry-run
published from an isolated tree?

It is not a substitute for focused development tests, and launching it is not
evidence that it passed.

## Canonical Entrypoints

| Context | Entrypoint | Responsibility |
| --- | --- | --- |
| local release review | `make release-validate-rs` | runs the canonical Rust release suite |
| hosted CI | `make gh-release-validate RELEASE_CHECK=<check>` | proves the complete suite through bounded parallel workers |
| maintainer control plane | `cargo run -q -p bijux-dev --bin bijux-dev-cli -- release verify` | coordinates release readiness and compatibility evidence |

The CI wrapper must remain thin. A check that exists only in hosted workflow
YAML or only in a local shell path creates two release definitions.

## Evidence States

| State | Honest claim |
| --- | --- |
| prepared | an isolated release tree was created from a named commit |
| running | one or more suite commands have started; no pass claim is valid |
| failed | the candidate or validation infrastructure failed at a recorded command |
| passed | every required suite command exited successfully for the same prepared tree |
| superseded | a newer commit exists; the result remains historical evidence for the older commit |

A PID, log path, prepared workspace, readiness file, or partial command list
does not establish `passed`. Release review needs the source commit, terminal
status, and complete command outcomes from one run.

## Isolation Boundary

The suite exports committed `HEAD` into
`artifacts/rust/release-validation/<run-id>/workspace/` before Cargo
validation. Uncommitted files in the live worktree are intentionally absent.
This makes a local run comparable to CI and prevents ambient edits from making
an unpublishable commit appear healthy.

The prepared tree patches the public DAG family into a local crates.io view
for topological dry-run verification before those versions exist remotely.
That mechanism simulates publication order; it must not conceal a private
dependency in a public package manifest.

The local full-suite command reuses one governed target directory. Hosted
verification prepares one source archive, compiles reusable library and binary
inputs, then gives each verification worker its own extracted candidate and Cargo
target directory. Workers share authenticated input bytes and execute independently.

The hosted planner reads the complete workspace Cargo target inventory. It assigns
every library, binary, integration test and benchmark target exactly once, isolates
measured slow test targets, and separately requires formatting, workspace-wide Clippy
and Rust documentation, public package listings, each locked publish dry-run,
Python installation, and the DAG CLI smoke pipeline. The existing local suite
remains the complete sequential entrypoint.

`configs/rust/release-verification.json` owns the 180-second target and 300-second
maximum. Every hosted job has a five-minute timeout, and worker commands reserve
cleanup time within that limit. Missing, duplicate, failed, stale, modified or
out-of-budget evidence prevents the final acceptance check from passing.

Only public registry inputs and compiled outputs enter compilation archives;
Cargo credentials and unrelated outputs are excluded. Candidate, plan, compiler,
Python runtime and lock identities bind each worker result to the same source.
The final `validate-release-candidate` job requires every producer and verification
worker to succeed and retains `artifacts/release-validation/acceptance.json`.

## Required Proof

The suite covers these proof classes:

| Proof class | Required observation |
| --- | --- |
| source quality | formatting and Clippy pass with warnings denied |
| behavior | workspace tests pass with the release feature surface |
| API documentation | Rust documentation builds without dependency docs |
| package contents | every public DAG crate produces the intended file list |
| publication | every public DAG crate passes locked dry-run publication in governed order |
| installed boundary | the DAG CLI smoke pipeline passes from the release tree |

The concrete command contract is:

```bash
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --all-features --locked -- -D warnings
cargo test --workspace --all-targets --all-features --locked
cargo doc --workspace --all-features --no-deps
cargo package -p bijux-dag-core --list
cargo package -p bijux-dag-artifacts --list
cargo package -p bijux-dag-runtime --list
cargo package -p bijux-dag-app --list
cargo package -p bijux-dag-cli --list
cargo publish -p bijux-dag-core --dry-run --locked
cargo publish -p bijux-dag-artifacts --dry-run --locked
cargo publish -p bijux-dag-runtime --dry-run --locked
cargo publish -p bijux-dag-app --dry-run --locked
cargo publish -p bijux-dag-cli --dry-run --locked
cargo test -p bijux-dag-cli --test smoke_pipeline --locked -- --nocapture
```

The publish order and public/private boundary are governed by
`contracts/foundation/workspace_package_boundary.v1.json`.

## Performance And Environment Evidence

Release validation does not execute benchmarks, soak workloads, or
live-environment scenarios. Those claims have separate evidence boundaries:

| Claim | Required authority |
| --- | --- |
| release-relevant performance | `bijux-dev-dag performance-evidence-report` evaluated against `evidence/perf/metadata.json` |
| benchmark regression | a completed benchmark report under `artifacts/benchmarks/` and the governed threshold referenced by the scenario |
| soak behavior | a named soak command, duration, workload, terminal status, and retained artifact directory |
| live environment | the exact platform or service, configuration boundary, command, and retained result |

A release recommendation may cite those results alongside this suite, but it
must not imply that release validation produced them. Missing external evidence
means the corresponding claim is unverified, not implicitly covered by a green
release result.

## What A Pass Does Not Prove

A green release validation result does not by itself prove:

- that uncommitted work in the live checkout is correct;
- that Python packaging or Python tests passed;
- that external services, remote workers, or unavailable platforms work;
- that performance, soak, or live-environment claims were exercised;
- that a later commit is releaseable;
- that release notes accurately describe the candidate.

Those claims need their own lanes and evidence. Do not broaden the release
suite result in a pull request or tag recommendation.

## Outputs And Provenance

| Output | Purpose |
| --- | --- |
| `artifacts/rust/release-validation/<run-id>/workspace/` | exact prepared release tree |
| `artifacts/rust/release-validation/<run-id>/target/` | isolated Cargo products |
| `artifacts/rust/release-validation/<run-id>/` | command logs, statuses, and run evidence |
| `artifacts/release/readiness_report.json` | readiness observations consumed by release review |
| `artifacts/release/compatibility_matrix.json` | compatibility observations for the candidate |

Readiness and compatibility files are evidence, not independent pass signals.
They are trustworthy only when their provenance identifies the candidate and
the producing command completed successfully.

## Failure Ownership

| Failure | First owner to inspect |
| --- | --- |
| format, lint, test, doc, package, publish, or smoke command | candidate code, manifest, lockfile, or governed release input |
| release-tree export | `.github/scripts/prepare_release_tree.py` |
| local/CI command disagreement | `makes/gh.mk` and `.github/workflows/release-validation.yml` |
| missing or ambiguous terminal status | release-suite orchestration and status recording |
| stale readiness or compatibility output | producing maintainer command and source revision |

Fix the cause. Do not delete a command, weaken a warning policy, or relabel an
incomplete run to obtain a green release claim.

## When To Run It

Run the suite before recommending a tag and after changes to:

- public crate manifests, package contents, or publish order;
- release-tree preparation or CI delegation;
- release compatibility and readiness contracts;
- the installed DAG CLI boundary.

During implementation, use the smallest honest lane from
[Repository Gates](repository-gates.md). Release validation is deliberately
broader and more expensive because it evaluates a candidate, not an edit.

## Review Record

A release recommendation should record:

- full source commit SHA;
- suite entrypoint and terminal status;
- artifact run directory;
- failed command and exit status when not green;
- checks outside this suite that support additional claims;
- any relevant platform or environment omissions.

## Related Surfaces

- [Repository Gates](repository-gates.md)
- [Release Operations](release-operations.md)
- [release-validation workflow](../gh-workflows/release-validation.md)
- [Release Surfaces](../makes/release-surfaces.md)
