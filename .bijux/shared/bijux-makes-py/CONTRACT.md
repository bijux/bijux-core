# Python artifact contract

Python repository automation keeps generated state beneath the repository
`artifacts/` tree. Root paths such as `.venv`, `.tox`, `.hypothesis`, and
`.benchmarks` are compatibility symlinks; their canonical destinations live
under `artifacts/root/`. Package aliases point to `artifacts/<package>/`.

## Configuration authority

`config/python-baseline.toml` is the versioned semantic baseline for Python
support, common development-tool compatibility envelopes, OpenAPI tooling, and
Tox execution. Repositories retain their own reproducible Python and Node
lockfiles and their product-specific Tox environments.

`make check-python-baseline` validates repository-owned configuration against
that baseline. A tool may use a narrower declared range or resolve to a
different locked version, but it must remain inside the shared compatibility
envelope. OpenAPI tooling uses one generic package identity and exact shared
tool versions so its lockfile differences reflect dependency resolution rather
than conflicting policy.

`repository/badge_renderer.py` owns badge parsing, rendering, synchronization,
and drift detection. Repository adapters identify their package-catalog table;
the catalog owns repository identity, package paths, publication surfaces, and
badge-family selection. Badge templates and rendered documentation remain
product-owned.

The shared Make environment routes Python bytecode, XDG caches, uv, pip, Tox,
pytest, coverage, Hypothesis, Ruff, Mypy, builds, documentation, SBOMs, npm,
and process scratch space beneath the same artifact tree. Package dispatch
provides package-owned locations rather than leaking root cache paths into a
package run.

## Candidate-bound SBOMs

Repositories with a locked uv workspace can set
`SBOM_REQUIRE_CANDIDATE_PROVENANCE=1` in their package profile. The SBOM task
then exports the named package's production and development dependency closures
with `uv export --frozen --offline`, refuses a virtualenv-wide fallback, and
requires a clean tagged Git candidate or a producer-owned source snapshot. The
snapshot records the original commit, Git description, and SHA-256 of every
copied input. Snapshot input integrity is checked here; authentication of its
declared repository and commit must be established by the upstream producer. The
default source set includes the workspace and package
`pyproject.toml`, `uv.lock`, and the local SBOM Make and provenance helper files;
`SBOM_EXTRA_SOURCE_INPUTS` adds other repository-relative inputs. A configured
requirements writer is refused in this mode because its source closure is not
declared. Retained requirements inputs must be repository-relative and included
in the snapshot identity.

The supported natural version is the simple `vMAJOR.MINOR.PATCH` tag with the
`guess-next-dev` distance form used by Hatch VCS. A configured version resolver
must agree with that version. Each SBOM is staged and published only after the
audit and source recheck succeed; a failed audit keeps a `.failed` artifact for
inspection. Validation and summary use the two current package artifacts by
exact name. Other package layouts retain their existing SBOM route until they
configure and validate this stricter contract.

## Setup and inspection

`make setup` creates missing canonical directories and aliases. It never
deletes or replaces a real compatibility-path directory. A real directory is
legacy state that must be inspected before relocation.

Run `make artifact-aliases-inspect` to report every root and package alias.
Inspection is read-only and reports the byte size of each legacy directory.
The underlying `migrate` command is also inspection-only unless `--apply` is
provided explicitly.

## Migration and recovery

Run `make artifact-aliases-migrate` only after reviewing the inspection. The
command moves each legacy directory to its canonical destination on the same
filesystem and creates the compatibility symlink. It does not delete the
directory contents.

If a canonical destination already contains data, migration first moves that
tree to:

```text
artifacts/recovery/artifact-aliases/<canonical-path-beneath-artifacts>
```

The command refuses to start when that recovery destination already exists.
It preflights every alias before moving any path and restores both sides if a
move or symlink operation fails.

To reverse a completed collision migration, stop repository processes, remove
only the compatibility symlink, move the migrated canonical tree back to the
original compatibility path, then move the preserved recovery tree back to
its canonical destination. Inspect both trees and record their sizes before
performing that explicit reversal.
