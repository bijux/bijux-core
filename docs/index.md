---
title: Bijux Core Documentation
audience: mixed
type: index
status: canonical
owner: bijux-core-docs
last_reviewed: 2026-10-08
---

# Bijux Core

`bijux-core` is the release and verification workspace for the `bijux` command
runtime and the local-first `bijux-dag` toolchain.

[CLI installation](bijux-cli/operations/installation-and-setup.md) · [First-run tutorial](bijux-dag/operations/first-run-tutorial.md)

## Start With One Product

| What you want to do | Prepare the command | Continue with |
| --- | --- | --- |
| Use `bijux` commands, configuration, or plugins | [CLI installation](bijux-cli/operations/installation-and-setup.md) | [Command surface](bijux-cli/interfaces/cli-surface.md) |
| Run a local workflow and retain its results | [DAG installation](bijux-dag/operations/installation-and-setup.md) | [First-run tutorial](bijux-dag/operations/first-run-tutorial.md), using a source checkout for its checked-in inputs |

The CLI and DAG are installed separately. Choose the product first; the
handbooks below explain its behavior and verification boundaries.

<!-- bijux-core-badges:generated:start -->
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-0F766E)](https://github.com/bijux/bijux-core/blob/main/LICENSE)
[![CI](https://github.com/bijux/bijux-core/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/bijux/bijux-core/actions/workflows/ci.yml?query=branch%3Amain)
[![Docs](https://github.com/bijux/bijux-core/actions/workflows/deploy-docs.yml/badge.svg?branch=main)](https://github.com/bijux/bijux-core/actions/workflows/deploy-docs.yml?query=branch%3Amain)
[![Crates Publish](https://github.com/bijux/bijux-core/actions/workflows/release-crates.yml/badge.svg?branch=main)](https://github.com/bijux/bijux-core/actions/workflows/release-crates.yml)
[![PyPI Publish](https://github.com/bijux/bijux-core/actions/workflows/release-pypi.yml/badge.svg?branch=main)](https://github.com/bijux/bijux-core/actions/workflows/release-pypi.yml)
[![GHCR Publish](https://github.com/bijux/bijux-core/actions/workflows/release-ghcr.yml/badge.svg?branch=main)](https://github.com/bijux/bijux-core/actions/workflows/release-ghcr.yml)
[![GitHub Release](https://github.com/bijux/bijux-core/actions/workflows/release-github.yml/badge.svg?branch=main)](https://github.com/bijux/bijux-core/actions/workflows/release-github.yml)
[![Release](https://img.shields.io/github/v/release/bijux/bijux-core?display_name=tag&label=release)](https://github.com/bijux/bijux-core/releases)
[![GHCR packages](https://img.shields.io/badge/ghcr-6%20packages-181717?logo=github)](https://github.com/bijux?tab=packages&repo_name=bijux-core)
[![Public crates](https://img.shields.io/badge/public%20crates-6-2563EB)](https://github.com/bijux/bijux-core/tree/main/crates)

[![bijux-cli](https://img.shields.io/crates/v/bijux-cli?label=bijux--cli&logo=rust)](https://crates.io/crates/bijux-cli)
[![bijux-dag-artifacts](https://img.shields.io/crates/v/bijux-dag-artifacts?label=artifacts&logo=rust)](https://crates.io/crates/bijux-dag-artifacts)
[![bijux-dag-core](https://img.shields.io/crates/v/bijux-dag-core?label=core&logo=rust)](https://crates.io/crates/bijux-dag-core)
[![bijux-dag-runtime](https://img.shields.io/crates/v/bijux-dag-runtime?label=runtime&logo=rust)](https://crates.io/crates/bijux-dag-runtime)
[![bijux-dag-app](https://img.shields.io/crates/v/bijux-dag-app?label=app&logo=rust)](https://crates.io/crates/bijux-dag-app)
[![bijux-dag-cli](https://img.shields.io/crates/v/bijux-dag-cli?label=bijux--dag&logo=rust)](https://crates.io/crates/bijux-dag-cli)
[![bijux-cli](https://img.shields.io/pypi/v/bijux-cli?label=bijux--cli&logo=pypi)](https://pypi.org/project/bijux-cli/)

[![bijux-cli](https://img.shields.io/badge/bijux--cli-ghcr-181717?logo=github)](https://github.com/bijux/bijux-core/pkgs/container/bijux-core%2Fbijux-cli)
[![bijux-dag-artifacts](https://img.shields.io/badge/artifacts-ghcr-181717?logo=github)](https://github.com/bijux/bijux-core/pkgs/container/bijux-core%2Fbijux-dag-artifacts)
[![bijux-dag-core](https://img.shields.io/badge/core-ghcr-181717?logo=github)](https://github.com/bijux/bijux-core/pkgs/container/bijux-core%2Fbijux-dag-core)
[![bijux-dag-runtime](https://img.shields.io/badge/runtime-ghcr-181717?logo=github)](https://github.com/bijux/bijux-core/pkgs/container/bijux-core%2Fbijux-dag-runtime)
[![bijux-dag-app](https://img.shields.io/badge/app-ghcr-181717?logo=github)](https://github.com/bijux/bijux-core/pkgs/container/bijux-core%2Fbijux-dag-app)
[![bijux-dag-cli](https://img.shields.io/badge/bijux--dag-ghcr-181717?logo=github)](https://github.com/bijux/bijux-core/pkgs/container/bijux-core%2Fbijux-dag-cli)

[![Repository docs](https://img.shields.io/badge/docs-repository-2563EB?logo=materialformkdocs&logoColor=white)](https://bijux.io/bijux-core/)
[![bijux-cli docs](https://img.shields.io/badge/docs-bijux--cli-2563EB?logo=materialformkdocs&logoColor=white)](https://bijux.io/bijux-core/bijux-cli/packages/bijux-cli/)
[![bijux-dag-artifacts docs](https://img.shields.io/badge/docs-artifacts-2563EB?logo=materialformkdocs&logoColor=white)](https://bijux.io/bijux-core/bijux-dag/packages/bijux-dag-artifacts/)
[![bijux-dag-core docs](https://img.shields.io/badge/docs-core-2563EB?logo=materialformkdocs&logoColor=white)](https://bijux.io/bijux-core/bijux-dag/packages/bijux-dag-core/)
[![bijux-dag-runtime docs](https://img.shields.io/badge/docs-runtime-2563EB?logo=materialformkdocs&logoColor=white)](https://bijux.io/bijux-core/bijux-dag/packages/bijux-dag-runtime/)
[![bijux-dag-app docs](https://img.shields.io/badge/docs-app-2563EB?logo=materialformkdocs&logoColor=white)](https://bijux.io/bijux-core/bijux-dag/packages/bijux-dag-app/)
[![bijux-dag-cli docs](https://img.shields.io/badge/docs-bijux--dag-2563EB?logo=materialformkdocs&logoColor=white)](https://bijux.io/bijux-core/bijux-dag/packages/bijux-dag-cli/)
[![bijux-cli-python docs](https://img.shields.io/badge/docs-bijux--cli--python-2563EB?logo=materialformkdocs&logoColor=white)](https://bijux.io/bijux-core/bijux-cli/packages/bijux-cli-python/)
<!-- bijux-core-badges:generated:end -->

Both products make operational authority visible. `bijux` resolves a command
to one owner and preserves streams and exit semantics. `bijux-dag` turns a
graph into a validated plan, executes it through an explicit backend, and
retains the evidence needed to inspect, compare, or replay the result.

The same repository carries private verification surfaces that test release
claims against code, schemas, fixtures, and generated evidence. Those
maintainer tools validate the products; they are not hidden product APIs.

<div class="bijux-callout"><strong>Two executables, two result models.</strong>
<code>bijux</code> resolves one command and preserves process semantics.
<code>bijux-dag</code> executes one graph and retains an integrity-bearing run
record. Repository and maintainer material governs ownership and proof around
those products.</div>

<div class="bijux-panel-grid">
  <div class="bijux-panel"><h3>Repository</h3><p>Package boundaries, dependency direction, compatibility, release policy, and shared ownership.</p></div>
  <div class="bijux-panel"><h3>CLI</h3><p>Command semantics, routing, plugins, configuration, state, REPL behavior, and Python distribution.</p></div>
  <div class="bijux-panel"><h3>DAG</h3><p>Graph admission, planning, scheduling, backends, retained evidence, cache, comparison, and replay.</p></div>
  <div class="bijux-panel"><h3>Maintainer</h3><p>Toolchains, repository gates, evidence production, security checks, automation, release, and incident response.</p></div>
</div>

<div class="bijux-quicklinks">
<a class="md-button md-button--primary" href="bijux-core/">Open the repository handbook</a>
<a class="md-button" href="bijux-cli/">Open the CLI handbook</a>
<a class="md-button" href="bijux-dag/">Open the DAG handbook</a>
<a class="md-button" href="bijux-dev/">Open the maintainer handbook</a>
</div>

## Released Product Boundary

| Surface | Delivery | What you can rely on today |
| --- | --- | --- |
| `bijux` | Rust crate, PyPI distribution, release bundles | the visible `bijux --help` runtime, including apps, plugins, layered config, REPL, diagnostics, history, and memory |
| `bijux-dag` | Rust crates and release bundles | the visible `bijux-dag --help` local DAG surface for validate, plan, run, replay, inspect, compare, cache, and verify workflows |
| maintainer tooling | repository-internal only | contributor and release workflows, not end-user product API |

`bijux-dag` is intentionally honest about its current boundary. The stable lane
is local-first. Experimental, simulated, and maintainer-only routes exist in
the repository, but they are not presented here as the default product story.

## Operational Model

```mermaid
flowchart LR
    intent["operator intent"]
    admission["parse · validate · resolve policy"]
    work["owned execution boundary"]
    result["process result or retained run"]
    integrity["diagnose · verify · compare"]
    decision["bounded decision"]

    intent --> admission --> work --> result --> integrity --> decision
    admission -->|"unsupported or unsafe"| refuse["refuse before effects"]
    integrity -->|"missing or inconsistent"| quarantine["preserve and investigate"]
```

Admission prevents unsupported work from becoming effects. Integrity checks
prevent an incomplete or corrupted result from becoming trusted evidence. The
CLI and DAG runtimes implement different versions of that lifecycle, while the
maintainer control plane applies the same discipline to tests, documentation,
packages, and releases.

## Two Execution Paths

```mermaid
flowchart TB
    operator["operator or automation"]

    subgraph cli_path["Command runtime"]
        cli_input["CLI, REPL, or Python launcher"]
        cli_route["normalize config and resolve route"]
        cli_run["built-in, mounted app, or plugin execution"]
        cli_result["stdout · stderr · exit status"]
    end

    subgraph dag_path["Workflow runtime"]
        dag_input["graph source"]
        dag_plan["validate, canonicalize, and plan"]
        dag_run["backend execution"]
        dag_result["run directory · traces · artifacts · identity"]
    end

    operator --> cli_input --> cli_route --> cli_run --> cli_result
    operator --> dag_input --> dag_plan --> dag_run --> dag_result
```

The paths deliberately end differently. A CLI command returns process-facing
streams and status. A DAG run also leaves an integrity-bearing record because
replay, comparison, and post-run verification depend on durable evidence.

## Trust Properties

| Property | What the repository preserves | Where to verify it |
| --- | --- | --- |
| owned command routing | aliases normalize to canonical routes; delegated processes retain native streams and exit status | [CLI execution model](bijux-cli/architecture/execution-model.md) |
| explicit configuration | layered values can be traced to their source and secret-like fields are redacted by default | [CLI configuration guide](bijux-cli/interfaces/config-guide.md) |
| deterministic graph meaning | canonical graph and plan identities are separate from runtime and artifact identity | [DAG reproducibility model](bijux-dag/interfaces/reproducibility-model.md) |
| failure evidence | failed, skipped, blocked, cancelled, cached, and successful work remain distinguishable | [DAG failure recovery](bijux-dag/operations/failure-recovery.md) |
| honest isolation | enforced checks are separated from host, container, scheduler, and cluster assumptions | [Execution security](bijux-dag/operations/security-isolation-truth.md) |
| release traceability | publication boundaries and required evidence are machine-readable and contract-tested | [Repository release operations](bijux-core/operations/release-and-versioning.md) |

## Choose By Responsibility

| If you want to... | Open this handbook |
| --- | --- |
| run `bijux`, mount apps, work with plugins, or debug runtime behavior | [CLI Handbook](bijux-cli/index.md) |
| author DAGs, run them locally, inspect artifacts, or replay a run | [DAG Handbook](bijux-dag/index.md) |
| understand what the repository publishes, how crates divide work, or how release boundaries are enforced | [Repository Handbook](bijux-core/index.md) |
| work on repository gates, release proof, or documentation and automation pipelines | [Maintainer Handbook](bijux-dev/index.md) |

## First Operational Journeys

- To automate `bijux`, begin with the
  [CLI surface](bijux-cli/interfaces/cli-surface.md), then use the
  [configuration guide](bijux-cli/interfaces/config-guide.md) and
  [diagnostics guide](bijux-cli/operations/diagnostics-guide.md).
- To execute a real graph, follow the
  [first-run tutorial](bijux-dag/operations/first-run-tutorial.md), then read
  the [run evidence layout](bijux-dag/interfaces/run-evidence-layout.md).
- To diagnose a failed run, preserve it and follow
  [observability and diagnostics](bijux-dag/operations/observability-and-diagnostics.md)
  before attempting recovery.
- To evaluate a release or repository change, start with
  [testing and validation](bijux-core/operations/testing-and-validation.md)
  and the [maintainer gate map](bijux-dev/operations/repository-gates.md).

## Evidence Strength

```mermaid
flowchart LR
    request["command or graph request"]
    contract["validated route, schema,<br/>graph, or policy"]
    execution["owned execution"]
    outcome["streams, status,<br/>state, or run directory"]
    verification["diagnostics, integrity,<br/>replay, or gate"]
    decision["bounded operational decision"]

    request --> contract --> execution --> outcome --> verification --> decision
    verification -->|"missing or inconsistent evidence"| refuse["refuse or narrow the claim"]
```

| Outcome | Trust it for | Do not infer |
| --- | --- | --- |
| successful `bijux` result | that one route completed under the observed state | that delegated code was isolated or all plugins are healthy |
| accepted DAG validation | that graph syntax and semantics passed the active contract | that any node executed |
| finalized run directory | that execution reached a retained terminal result | that files remain intact or domain output is correct |
| strict verification | that retained structural and integrity contracts pass | scientific, business, or workload correctness |
| replay or semantic comparison | the recorded identity and difference classification | equivalence outside the selected evidence and environment |
| green maintainer gate | the exact selected suite at the recorded revision | omitted platforms, external services, or broader release claims |

Evidence becomes stronger only when the next authority is present. A process
status establishes completion, retained state establishes what was recorded,
integrity establishes whether that state is intact, and replay or comparison
establishes only the equivalence claim encoded by its selected contract.

The [v0.4.0 Release Notes](bijux-dag/operations/v0-4-0-release-notes.md) define
the current DAG release. [Future Direction](bijux-dag/foundation/future-direction.md)
is non-binding direction; if it conflicts with the release boundary, the
narrower shipped claim wins.
