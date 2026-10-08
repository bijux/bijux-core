---
title: First-Run Tutorial
audience: operators
type: operations
status: canonical
owner: bijux-dag-docs
last_reviewed: 2026-10-08
---

# First-Run Tutorial

This tutorial produces one retained local run, inspects its evidence, confirms
cache reuse, replays a selected boundary, and verifies the replay. It uses only
checked-in inputs and writes outputs under `artifacts/`.

## Prepare A Source Checkout

This tutorial uses the repository's checked-in graph and sample files. A
standalone `bijux-dag` installation does not include those inputs. If you do
not have a checkout, obtain one and enter its root:

```bash
git clone https://github.com/bijux/bijux-core.git
cd bijux-core
```

Check [Installation and Setup](installation-and-setup.md) for the pinned Rust
toolchain and local execution prerequisites. Use a checkout that matches the
version you intend to inspect; the commands below use its workspace binary.

## Fastest Proof

From that repository root:

```bash
make dag-demo
```

This is the shortest proof path for the `bijux-dag` product promise. The target
does not rely on a successful exit alone: it validates the file-processing
graph, inspects the effective graph, executes a cold run, checks retained
artifacts, performs a warm cache run, replays the reporting boundary, and
strictly verifies the replay.

The target removes and recreates `artifacts/dag-demo/`, then asserts:

| Claim | Machine-checked evidence |
| --- | --- |
| graph contract is accepted | `validate.json` has `ok = true` and `status = "ok"` |
| the expected graph is selected | `graph.json` contains exactly the four file-processing nodes |
| cold execution completed | `cold-run.json` reports four successful nodes |
| the report is retained and promotable | registry and inspection results contain `render_report:report.md`, with payload present |
| cache reuse is real | `warm-run.json` reports at least three cached nodes and one regenerated node |
| replay input is intact | `replay.json` reports verified upstream artifacts |
| replay evidence is valid | `verify.json` reports `status = "ok"` and `mode = "strict"` |

The final console lines print the artifact root, cold run, warm run, replay
run, and rendered report paths. Keep the JSON files when reviewing a failure;
they show the last completed proof boundary.

Use the manual path below when you need to understand each boundary or replace
the example paths with your own.

The demonstration proves one checked-in local workflow against the current
binary. It does not establish workload-specific correctness, hostile-code
isolation, or suitability for an environment with different storage and
process constraints.

## Prepare The Checkout

```bash
make bootstrap

GRAPH_PATH="evidence/dag/authoring/examples/file-processing-report.dag.json"
SOURCE_DIR="$(pwd)/evidence/dag/authoring/examples/file-processing-source"
RUN_ROOT="./artifacts/first-run-tutorial-runs"
CACHE_ROOT="./artifacts/first-run-tutorial-cache"
```

Cargo output remains under `artifacts/rust/target/` through repository
configuration. The tutorial invokes the workspace binary through Cargo so it
does not depend on a separately installed version.

## Confirm The Public Surface

```bash
cargo run -p bijux-dag-cli --bin bijux-dag -- version
cargo run -p bijux-dag-cli --bin bijux-dag -- commands
```

`commands` defaults to the stable operator lane.
Maintainer-only probes such as `capabilities` remain outside this
first-run path and require
`BIJUX_DAG_ENABLE_INTERNAL=1`.

The [Release Boundary](../foundation/release-boundary.md) explains stable,
experimental, simulated, internal, and unreleased lanes. The machine-readable
authority is `contracts/foundation/dag_release_truth_table.v1.json`.

## Validate Before Running

```bash
cargo run -p bijux-dag-cli --bin bijux-dag -- validate "${GRAPH_PATH}"
```

Validation proves that the graph is accepted under the current schema and
policy. It does not prove successful execution, output correctness, or
artifact integrity.

If you need structural inspection before execution, the repository-tested
`show-effective-graph` explicit-path route can expose nodes, edges, roots,
resources, and output contracts. It is not required for the stable first-run
proof.

## Create A Cold Run

```bash
cargo run -p bijux-dag-cli --bin bijux-dag -- run --json "${GRAPH_PATH}" \
  --out "${RUN_ROOT}" \
  --run-id first-run-tutorial-cold \
  --cache readwrite \
  --cache-dir "${CACHE_ROOT}" \
  --input "source_dir=${SOURCE_DIR}" \
  --input "report_title=First Run Tutorial Report"
```

The terminal envelope should report success and this retained directory:

```text
artifacts/first-run-tutorial-runs/run-first-run-tutorial-cold/
```

The command result is an orientation aid. The finalized directory is the
evidence boundary.

Do not continue to warm reuse if the cold run is not successful. A cache result
cannot repair or validate a failed source run.

## Inspect Retained Evidence

```bash
cargo run -p bijux-dag-cli --bin bijux-dag -- explain \
  "${RUN_ROOT}/run-first-run-tutorial-cold"

cargo run -p bijux-dag-cli --bin bijux-dag -- artifact registry \
  "${RUN_ROOT}/run-first-run-tutorial-cold" \
  --json

cargo run -p bijux-dag-cli --bin bijux-dag -- artifact-inspect \
  "${RUN_ROOT}/run-first-run-tutorial-cold" \
  render_report:report.md \
  --json
```

Check that:

- the manifest records `source_dir` and `report_title`;
- all four nodes reached their expected terminal states;
- the artifact registry contains the rendered report;
- artifact inspection resolves the declared `render_report:report.md` output;
- retained indexes and content digests agree.

The report payload should begin with the requested title and contain the
processed-file summary. A promotable artifact with the wrong domain content is
still the wrong result; artifact integrity and workflow correctness are
separate review decisions.

[Run Evidence Layout](../interfaces/run-evidence-layout.md) defines which
files are authoritative and which are summaries.

## Confirm Warm Reuse

Run the same graph with identical inputs and cache root:

```bash
cargo run -p bijux-dag-cli --bin bijux-dag -- run --json "${GRAPH_PATH}" \
  --out "${RUN_ROOT}" \
  --run-id first-run-tutorial-warm \
  --cache readwrite \
  --cache-dir "${CACHE_ROOT}" \
  --input "source_dir=${SOURCE_DIR}" \
  --input "report_title=First Run Tutorial Report"
```

The upstream processing stages should be reused. `render_report` is
intentionally regenerated. Cache reuse is valid only when the retained
identity and integrity checks admit it; a fast second run alone is not proof.

Compare the retained node counts rather than elapsed time. The expected warm
result has at least three cached nodes and one successful regenerated node.

## Replay And Verify

```bash
cargo run -p bijux-dag-cli --bin bijux-dag -- replay --json \
  --source-run-id first-run-tutorial-cold \
  --source-run-root "${RUN_ROOT}" \
  --out "${RUN_ROOT}" \
  --run-id first-run-tutorial-replay \
  --from-node render_report

cargo run -p bijux-dag-cli --bin bijux-dag -- verify --json \
  "${RUN_ROOT}/run-first-run-tutorial-replay" \
  --strict
```

Replay verifies retained inputs crossing into the selected boundary before
rerunning `render_report`. Strict verification then checks that the replayed
run still satisfies its retained contracts. The [Replay
Contract](../../spec/REPLAY_CONTRACT.md) defines the claim boundary.

Do not describe replay as successful if execution completed but
`upstream_artifact_verification.verified` is false or strict verification
fails. Those results preserve useful failure evidence, not a reproduction
proof.

## Failure Triage

Stop at the first failed boundary and preserve its output:

| Failure point | Inspect first | Correct response |
| --- | --- | --- |
| validation | command error and graph path | fix graph/schema input; do not create a run |
| cold run | finalized run directory and `explain` output | classify node, input, policy, or environment failure |
| artifact inspection | registry entry, payload presence, and digest evidence | repair artifact production or retention before cache testing |
| warm run | cache decisions and node counts | explain each miss; do not infer reuse from runtime duration |
| replay | upstream artifact verification | preserve the refusal and repair the retained source boundary |
| strict verification | verification JSON and replay run directory | treat the replay as unverified even if node execution succeeded |

For failures after a retained run exists, continue with [Failure
Recovery](failure-recovery.md). Never overwrite the failed run directory while
investigating it.

## Completion Evidence

The tutorial is complete when you can point to:

- accepted graph validation;
- a finalized cold run with recorded effective inputs;
- an inspectable report artifact;
- a warm run with explainable cache decisions;
- a replay carrying source and parent identity;
- a successful strict verification result.

If any item is missing, state that gap rather than describing the demonstration
as end-to-end proof. Command success, artifact integrity, domain correctness,
cache reuse, and replay verification are distinct claims.

## Next Reads

- [File Processing Workflow](file-processing-workflow.md)
- [Operator Workflows](../interfaces/operator-workflows.md)
- [Cache Behavior Workflow](cache-behavior-workflow.md)
- [Execution Security And Isolation](security-isolation-truth.md)
- [Installation And Setup](installation-and-setup.md)
