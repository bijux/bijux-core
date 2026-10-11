# Shared Make Contract

`bijux-makes` defines the language-neutral Make contract for Bijux repositories.
Repositories consume the synchronized copy under `.bijux/shared/bijux-makes/`.

## Inclusion

The repository root `Makefile` should include one repository-owned entrypoint:

```make
include makes/root.mk
```

The repository-owned entrypoint configures capabilities before loading the shared
contract:

```make
BIJUX_MAKE_COMPONENTS := docs rust
include .bijux/shared/bijux-makes/bijux.mk
```

Supported components are `docs` and `rust`. The Python Make library remains an
independent contract under `bijux-makes-py`.

## Public Behavior

- The default goal is `help`.
- `fmt` and `lint` verify source without modifying it.
- Source mutation uses explicit targets such as `format` and `format-rs`.
- Unsupported language gates are absent. They must not succeed as no-ops.
- `ci` is the canonical pull-request lane and delegates to `ci-pr`.
- `ci-fast`, `ci-pr`, `ci-nightly`, and `ci-docs` are assembled from enabled
  components.
- Generated output, caches, reports, and isolated source trees stay under
  `artifacts/`.
- `clean` refuses to remove paths outside the repository's `artifacts/`
  boundary.
- Commands preserve nonzero exit status through logging pipelines.

## Extension

Components register concrete targets through these aggregate variables:

```make
BIJUX_FORMAT_TARGETS
BIJUX_FMT_TARGETS
BIJUX_LINT_TARGETS
BIJUX_TEST_TARGETS
BIJUX_TEST_SLOW_TARGETS
BIJUX_TEST_ALL_TARGETS
BIJUX_AUDIT_TARGETS
BIJUX_SECURITY_TARGETS
BIJUX_COVERAGE_TARGETS
BIJUX_DOCTOR_TARGETS
BIJUX_CI_FAST_TARGETS
BIJUX_CI_PR_TARGETS
BIJUX_CI_NIGHTLY_TARGETS
BIJUX_CI_DOCS_TARGETS
```

Repository-owned extensions may append durable domain targets to these variables
before including `bijux.mk`. A configured target that does not exist is an error
reported by Make.

## Documentation

The common documentation component owns MkDocs execution and artifact placement.
The separate `bijux-docs` standard owns the shared visual shell, assets, and shell
validation. Repositories connect those concerns through `DOCS_PREPARE_TARGETS`
and `DOCS_SOURCE_CHECK_TARGETS`.

A managed `.bijux/docs-projection.json` record at the project root or beside
`DOCS_CONFIG` selects the `bijux-material` renderer profile. The latter boundary
covers a configured externally checked-out site. The marker paths are internal,
derived from the actual project/configuration roots, and cannot be overridden as
an admission waiver. A generic documentation caller without that ownership record
must explicitly configure `DOCS_RENDERER_PROFILE := native` or
`DOCS_RENDERER_PROFILE := bijux-material`; the default is unconfigured. Native
preserves the caller's `DOCS_RUN`, flags, configuration and custom runner, but it
cannot bypass an existing managed Bijux documentation ownership record.

`bijux-material` uses `DOCS_PYTHON_RUN` (default `python3`) both to check the
accepted Material compiler and to invoke `-m mkdocs`. A configured launcher may
include its own environment/provider prefix, but `DOCS_RUN` must equal that same
launcher followed by `-m mkdocs`. A different console script or guessed Python
interpreter is rejected before preparation or output cleanup. The default
`DOCS_MATERIAL_COMPILER` comes from the same shared root as the Make component.
Missing compiler, generated runtime drift, or installed Material outside exact
admission fails closed. This is renderer admission, not source ownership or
product plugin validation; configured source guards and strict builds still run.

`docs`, `docs-check`, and `docs-serve` complete `docs-require` before invoking
configured preparation targets. `docs-check` then runs source-check targets.
After either configured stage, the prepared renderer is admitted again before
cleanup/rendering. This catches newly projected managed ownership and changed
runtime assets, including changes made by a source-check hook. Recursive targets preserve Make flags while
ensuring `make -j` cannot prepare or clean first. Explicit `docs-clean` remains
an intentional artifact removal command independent of renderer availability.

The optional Rust component consumes this same documentation capability; it does
not add an independent renderer. A Rust-only repository has no documentation
requirement unless it enables the `docs` component. Product-owned historical
Core/GNSS/Hub wrappers and the Python Make profile are separate producer paths:
this module does not silently rewrite or qualify their execution.

## Pinned Gates

`scripts/run_pinned_gate.sh` launches an allowed Make target from an immutable,
gate-owned commit checkout under
`artifacts/<commit>/gates/<target>/frozen-repo/`. Gate outputs are isolated under
`artifacts/<commit>/gates/<target>/artifacts/`, while launcher process, log, and
exit status records remain under `artifacts/<commit>/background/`. This ownership
allows distinct gates for one commit to run concurrently without sharing source,
Cargo, or generated-output state. Repository-relative Make and Rust paths are
recomputed from the immutable checkout instead of inherited from the invoking
worktree. Pinned sources whose Rust policy requires workspace-bound artifacts
execute there and publish one stable gate-owned artifact link.
Before reusing an inactive checkout, the launcher restores tracked files changed
by the previous gate to the pinned commit. It refuses reuse when untracked files
outside the launcher-owned `artifacts/` boundary are present and never restores
a checkout while its recorded gate process is alive.
`PINNED_REF` is the canonical commit selector;
`TEST_ALL_FROZEN_REF` remains supported for established full-suite invocations.
