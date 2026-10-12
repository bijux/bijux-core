# Changelog
<a id="top"></a>

All notable changes to **bijux-core** are documented here.
This project adheres to [Semantic Versioning](https://semver.org) and the
[Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format.

<a id="unreleased"></a>

---

<!-- towncrier start -->

<a id="v0-4-1"></a>

## Unreleased


### Changed

- Keep repository new-tab warnings compact and accessible, and align catalogue input identities with independent publication admission ([#149](https://github.com/bijux/bijux-core/pull/149)).
- Bind documentation render dates to committed source, permit repository-owned workflow badge images, and batch publication custody checks ([#148](https://github.com/bijux/bijux-core/pull/148)).
- Resolve the patched rustls TLS dependency for RUSTSEC-2026-0285 ([#145](https://github.com/bijux/bijux-core/pull/145)).

- Adopt trusted manual publication admission and accepted shared documentation policy ([#145](https://github.com/bijux/bijux-core/pull/145)).
## 0.4.1 – 2026-07-25

### Added
- Added a corresponding GHCR package target for every public Rust crate, giving `bijux-cli` and each crate in the `bijux-dag` family an independently addressable container package.
- Added documentation contracts that reject unsafe Mermaid identifiers and README links without canonical public destinations.
- Added deployed documentation to the version-tag release coordinator alongside crates.io, PyPI, GHCR, and GitHub Release publication.

### Changed
- Advanced the workspace and all package dependency constraints to the `v0.4.1` release line without rewriting the `v0.4.0` release record.
- Aligned the canonical DAG product sentence and new plugin scaffold host floor with `v0.4.1` while preserving the `v0.4.0` compatibility boundary and release notes.
- Standardized the repository and package badge surfaces around four stable rows for repository health, registries, GHCR packages, and deployed documentation.
- Updated the release-validation Python action and consolidated the pending `base64`, `clap`, `libc`, and `serde_json` dependency updates.
- Aligned the managed PyPI workflow with trusted publishing for the maturin lane, retaining token bootstrap only for a confirmed missing project.

### Fixed
- Corrected the GHCR release matrix so its six package slugs exactly match the six crates.io publication targets.
- Corrected repository CI and package badge links so they resolve to the owning GitHub workflow, registry package, or deployed `bijux.io` page.
- Replaced repository-relative README hyperlinks with stable GitHub source links or deployed documentation routes.
- Corrected Mermaid node identifiers that prevented DAG diagrams from rendering on the public site.

<a id="v0-4-0"></a>

## 0.4.0 – 2026-07-24

Operator-facing DAG release notes:
[`docs/bijux-dag/operations/v0-4-0-release-notes.md`](docs/bijux-dag/operations/v0-4-0-release-notes.md)

### Added
- Published the public `bijux-dag` Rust crates for the first DAG release: `bijux-dag-core`, `bijux-dag-artifacts`, `bijux-dag-runtime`, `bijux-dag-app`, and `bijux-dag-cli`.
- Shipped the first public `bijux-dag` local operator line with stable graph authoring, execution, replay, artifact inspection, cache explanation, and verification surfaces.

### Changed
- Advanced the repository release line to `v0.4.0` across workspace metadata, release automation, and maintained compatibility defaults.
- Declared the visible `bijux-dag --help` surface as the stable local operator boundary for `v0.4.0`, while keeping experimental and maintainer routes callable by explicit path.
- Aligned release operations around the combined `bijux` and `bijux-dag` publication path, including the repository-internal maintainer role of `bijux-dev`.
- Refreshed the `v0.4.0` publication record on Friday, July 24, 2026 with the latest repository documentation updates so CLI, DAG, core, and maintainer handbooks now state release authority, evidence flow, and operator-facing boundaries consistently.
- Brought the release branch onto the current `bijux-std` governance baseline and folded the outstanding GitHub Actions and Rust dependency updates into the release line, superseding the blocked Dependabot pull requests for workflow pins and Cargo packages.

### Fixed
- Removed stale package and release references that still treated the DAG crates as internal-only or deferred beyond the active release line.
- Aligned mounted-app and release-facing fixtures with the `v0.4.0` compatibility floor so release evidence and examples report the same version line as published artifacts.
- Restored managed docs shell source-of-truth coverage, release and distribution proof contracts, and Rust gate bootstrapping so publication checks no longer depend on unrelated Python bootstrap paths.

<a id="v0-3-6"></a>

## 0.3.6 – 2026-04-21

### Added
- Introduced policy-driven `bijux-std` verification as a first-class workflow for this repository, including shared checksum validation and explicit update/refresh flow for `.bijux/shared` consumers.
- Brought `deploy-docs` activation and standards-managed release workflow contracts into the active CI surface, so release lanes and docs publication now track the shared governance baseline.

### Changed
- Migrated standards/doc tooling consumption to the `.bijux/shared` layout and kept the repository manifests/checksums in sync with upstream `bijux-std` updates.
- Reworked the documentation shell and handbook navigation behavior (program strips, detail rows, scoped sidebars, and mobile drawer behavior) to match the current multi-handbook structure.
- Expanded the `bijux-core` and `bijux-dag` handbook visuals and section maps so architecture, operations, release, and evidence flows are documented as explicit decision and lifecycle diagrams.
- Standardized badge generation so documentation badges follow a single contract across managed surfaces: repository docs first, package docs second, and package rust-docs third when available.
- Updated Rust docs badges from status-style to stable label-style (`rust-docs | <package>`) with Rust iconography for consistency with the broader badge catalog.

### Fixed
- Corrected docs deployment and standards checks to resolve shared-manifest paths through `.bijux` consumers, eliminating path drift between local and CI execution.
- Restored standards-managed `release-pypi` workflow wiring and aligned release workflow lane expectations with contract tests.
- Fixed badge/footer GHCR links so package/profile references scope to `bijux-core` artifacts instead of broader organization targets.

<a id="v0-3-5"></a>

## 0.3.5 – 2026-04-12

### Changed
- Grouped shared release-channel badges onto one line and shared documentation badges onto one line across repository and package surfaces.
- Advanced the repository release metadata and compatibility defaults to the `v0.3.5` line.

### Fixed
- Removed badge ordering drift between the root README, package READMEs, and docs landing pages by regenerating all managed badge blocks from the shared catalog.

<a id="v0-3-4"></a>

## 0.3.4 – 2026-04-06

### Changed
- Updated release metadata and automation to align with the unified `bijux-core` repository model.
- Corrected release-tree stamping and DAG workflow package references to use `bijux-dev` consistently.
- Aligned DAG CI toolchains and paths with the current workspace structure.

### Fixed
- Prevented accidental crates.io publication of `bijux-dag-*` crates by marking them internal-only.
- Corrected root documentation links and release guidance to match the current docs tree and repository boundaries.
- Added explicit release policy documentation: publish `bijux-cli` at `v0.3.4`; defer DAG publication to `v0.4.0`.

<a id="v0-3-0"></a>

## 0.3.0 – 2026-03-14

### Added
- Rust-owned runtime crates for the end-user binary (`bijux`), the Python bridge package, and the workspace-only maintainer control plane (`bijux-dev-cli`)
- Typed command routing, execution-kernel contracts, structured output schemas, and parity coverage across the binary, core runtime, Python bridge, and routed REPL surface
- Runtime support for config, history, memory, install, version, completion, and state-doctor behavior that is backed by focused parity, corruption, and resilience coverage
- Shipped plugin lifecycle management with routed execution, install/inspect/check/explain/enable/disable/uninstall flows, reserved-namespace enforcement, and Cookiecutter-backed Python and Cargo templates
- Interactive REPL execution with shared CLI semantics, history compatibility, completion, diagnostics, and hostile-session resilience coverage
- Installation diagnostics, first-run state setup, explicit shell completion output, official-product install alias resolution, and stable state-path reporting
- Python packaging through the crate-owned `bijux-cli-python` surface with maturin/pyo3 bindings, native facade fallbacks, and bridge-vs-runtime parity checks
- Opt-in structured telemetry and bounded trace diagnostics for runtime and maintainer execution paths
- Maintainer command contracts and evidence reports for runtime identity, route audits, parity, repository health, docs audits, and publish-time contract assets

### Changed
- Migrated the repository from the older Python-first layout to a Rust-first workspace with `crates/`, `configs/`, `contracts/`, `makes/`, and canonical docs sections
- Reduced the public root runtime surface to shipped commands, moved maintainer automation behind `bijux-dev-cli`, and kept the `cli` namespace as the canonical compatibility surface
- Standardized runtime identity so checkout builds derive from the latest real git tag line while release workflows stamp exact tagged versions into release artifacts
- Reworked plugin compatibility handling, manifest contracts, scaffold defaults, and template guidance around the current plugin runtime and pre-1.0 host boundaries
- Consolidated release engineering around stamped release trees, pinned workflow/toolchain inputs, stable package metadata, and explicit publish gates for crates.io and PyPI artifacts
- Rebuilt the public docs canon, changelog policy, contributor guidance, and security policy around current runtime behavior instead of historical Python-era assumptions
- Moved maintainer evidence generation from legacy scripts into `bijux-dev-cli` report/query surfaces and contract-driven documentation publishing

### Removed
- Legacy `bijux-cli` compatibility executable naming; `bijux` is now the only runtime command name
- Legacy runtime ownership of maintainer/dev namespaces from the end-user command surface
- Legacy `scripts/` automation paths, root git-hook wiring, root OpenAPI/Node release remnants, and the previous MkDocs builder pipeline
- Legacy duplicate Python distribution/test roots outside `crates/bijux-cli-python`
- Legacy docs trees, stale policy fragments, and compatibility shims that no longer matched the canonical runtime/docs layout
- Demo-grade root commands, placeholder plugin execution paths, and stale maintainer fallback behavior that no longer matched the shipped runtime contract

### Fixed
- Corrected plugin routing so installed plugins and aliases execute through the runtime instead of stopping at placeholder errors
- Hardened `doctor`, `status`, install diagnostics, state-path handling, and registry/history/memory recovery so health output reflects actual runtime conditions
- Corrected config precedence, config mutation flows, help/usage handling, completion shell selection, and root/`cli` route normalization to match the current runtime law
- Aligned Rust, Python, and release metadata around supported hosts, package ownership, explicit completion shells, and tag-derived version provenance
- Tightened plugin manifest validation, runtime floors, registry locking, and scaffold build behavior for Python and Rust plugin projects
- Strengthened REPL hostile-session behavior, history bounds, multiline parsing, completion registries, and shared CLI/REPL execution parity
- Bounded runtime and maintainer telemetry fields, trace payloads, and observability lifecycle reporting so diagnostics stay structured under failure and scale
- Reduced Python bootstrap noise in common Make workflows and cleared remaining release-line/documentation drift around the shipped runtime boundary

<a id="v0-2-0"></a>

## 0.2.0 – 2026-01-26

### Added
- Linear bootstrap flow with explicit bootstrap boundaries and a first-class `CLIIntent`
- Rebuilt E2E suite with domain taxonomy, invariants, and a subprocess harness
- Nightly fuzz and stress suites under `tests/nightly` with dedicated markers
- Expanded regression coverage for bootstrap paths, flags matrix, plugin loader/metadata, and real serializer roundtrips
- Benchmarks with thresholds for startup, discovery (cold/warm), config load, REPL, and help/version fast paths
- API contract gating with stricter schema validation and schemathesis checks
- Docs rebuilt into concepts/guides/reference/examples with section indexes
- API purity guard enabled in CI to prevent IO in API calls

### Changed
- Centralized CLI policy resolution for routing, exit intent, and precedence
- Infra strictness: explicit formats/targets required; no guessing
- Plugin lifecycle contract with explicit states and early metadata validation
- Test organization aligned to `src/` with merged regression suite and nightly rename
- MkDocs generator and nav rebuilt to match the new docs tree

### Fixed
- Help output routing for structured formats
- Exit-policy invariants to detect real Python tracebacks only
- API validation error payloads now JSON-encoded with stable schema

### Removed
- Legacy root docs pages and ADR directory (decisions moved into canonical docs)
- Thin CLI core wrappers (emit/validation) consolidated



<a id="v0-1-3"></a>

## 0.1.3 – 2025-08-20

### Added
* **ADR-0005:** Zero-root-pollution via **Makefile-orchestrated artifact containment** (all generated outputs under `artifacts/`).  
* **Curated release assets:** zipped bundles for **tests (py311/py312/py313)** and for **lint, quality, security, api, docs, sbom, citation, build**, plus consolidated **checksums**.
* **End-to-end automation:** GitHub Actions to **publish to PyPI**, **create a GitHub Release** with curated bundles, and **deploy docs**.

### Changed
* **Makefiles + workflows** brought into **full ADR-0005 compliance**: CI uploads/downloads only `artifacts/**`; docs deploy hydrates from CI artifacts and builds from `artifacts/docs/**`.


---

<a id="v0-1-2"></a>

## 0.1.2 – 2025-08-17

### Added
* **New Documentation Engine:** Introduced a new modular documentation builder in `scripts/docs_builder/` that replaces the previous helper script.
* **CI Artifact Pages:** The documentation site now automatically generates detailed pages for all CI artifacts, including tests, linting, code quality, security, API tests, SBOMs, and citation files.
* **Release Evidence:** The `publish` workflow now downloads all artifacts from the `CI` run, packages them as `evidence/*.tar.gz` bundles, and attaches them to the GitHub Release for traceability.
* **Build Hygiene:** Makefiles now enforce a "hygienic" build process, ensuring all temporary files, caches, and build outputs are stored under the `artifacts/` directory to prevent root directory pollution.

### Changed
* **CI/CD Overhaul:**
    * The `ci.yml` workflow now uploads each category of artifact separately for better organization and downstream consumption.
    * The `docs.yml` workflow now waits for the main `CI` run to complete, downloads all artifacts, and uses them to build a data-rich documentation site.
    * The `publish.yml` workflow has been streamlined and made more robust, removing the optional "wait for docs" step and improving tag detection.
* **Documentation Content:** All top-level Markdown documents (`README.md`, `USAGE.md`, `TESTS.md`, `TOOLING.md`, `CONTRIBUTING.md`, etc.) have been significantly rewritten and expanded with tables of contents, `back-to-top` links, and cross-references to the new artifact pages.
* **Build System:**
    * All `Makefile` modules have been refactored to use the new hygienic `artifacts/` directory structure for outputs and caches.
    * `tox.ini` has been updated to align with the new Makefile targets and to run a comprehensive suite of checks for the `py311` environment, mirroring the full CI validation process.
* **API Schema:** The OpenAPI `schema.yaml` has been improved with stricter validation (`additionalProperties: false`), better descriptions, response links, and more detailed examples.
* **Source Code:** Refactored async handling in `src/bijux_cli/api.py` and improved type safety across multiple modules with clearer casts.

### Fixed
* **Type Safety:** Resolved numerous previously ignored type errors throughout the codebase and test suite.
* **API Endpoint Logic:** Corrected the item update logic in `src/bijux_cli/httpapi.py` by removing a faulty check for duplicate names that was causing incorrect 409 Conflict errors.
* **Test Suite:** Improved the stability and correctness of E2E tests by enhancing golden file comparisons and fixing brittle assertions.


---

<a id="v0-1-1"></a>

## 0.1.1 – 2025-08-14

### Added
* **Publish pipeline:** GitHub Actions `publish.yml` that publishes via `make publish` only after required checks are green and a tag is present.
* **Project map:** `PROJECT_TREE.md` (and `docs/project_tree.md`) with a curated overview.
* **Developer Tooling page:** `TOOLING.md` (and `docs/tooling.md`) with embedded configs, Makefile snippets, and CI workflows via `include-markdown`.
* **Docs assets:** Community landing page, Plausible analytics partial, and CSS overrides.

### Changed
* **Docs generator (`scripts/docs_builder/mkdocs_manager.py`):**
  * Copies **README**, **USAGE**, **TESTS**, **PROJECT_TREE**, and **TOOLING** into the site with link rewrites and `{#top}` anchors.
  * Generates mkdocstrings pages for all modules under `src/bijux_cli/**`.
  * Builds **one** consolidated **API Reference** with this structure:
    * top: **Api Module**, **Cli Module**, **Httpapi Module**
    * sections (collapsed by default): **Commands**, **Contracts**, **Core**, **Infra**, **Services**
    * nested groups for command subpackages (`config/`, `dev/`, `history/`, `memory/`, `plugins/`) beneath **Commands**.
  * Emits `reference/**/index.md` to power Material’s section indexes.
* **MkDocs config (`mkdocs.yml`):** tightened plugin ordering and settings for `include-markdown`, enabled section indexes, and strict mode; added watch paths for configs and scripts.
* **README / USAGE:** Refined copy; standardized **top anchors** and links to **TESTS.md**/**PROJECT_TREE.md**/**TOOLING.md**.
* **SECURITY.md:** Rewritten with clearer reporting, SLAs, scope, and safe harbor.
* **Makefiles:** macOS-safe env handling; Cairo-less Interrogate wrapper for doc coverage.
* **Config:** Expanded lints/dictionary.

### Fixed
* **Docs build (strict):** resolved broken/unknown links in **TOOLING.md** and removed duplicate **API Reference** sections; left sidebar now stays populated when deep-linking into API pages.
* **Tests:** E2E version fixtures cleaned up.

### Packaging
* **PyPI links corrected:** `project.urls` now points to accurate Homepage/Docs/Changelog/Issues/Discussions.
* **Dynamic versioning from Git tags:** Using `hatch-vcs` with `dynamic = ["version"]`; annotated tags like `v0.1.1` define the release version. `commitizen` tags as `v$version`.
* **Richer PyPI description:** `hatch-fancy-pypi-readme` renders **README.md** + **CHANGELOG.md** on PyPI.
* **Wheel/Sdist layout:** Explicit Hatch build config ensures `py.typed`, licenses, and metadata are included.


---

<a id="v0-1-0"></a>

## 0.1.0 – 2025-08-12

### Added

* **Core runtime**

    * Implemented Dependency Injection kernel, REPL shell, plugin loader, telemetry hooks, and shell completion (bash/zsh/fish).
    * Added core modules: `api`, `cli`, `httpapi`, `core/{constants,context,di,engine,enums,exceptions,paths}`.

* **Contracts layer** (`contracts/`)

    * Defined protocols for `audit`, `config`, `context`, `docs`, `doctor`, `emitter`, `history`,
      `memory`, `observability`, `process`, `registry`, `retry`, `serializer`, `telemetry`.
    * Added `py.typed` markers for downstream type checking.

* **Services layer**

    * Implemented concrete services for `audit`, `config`, `docs`, `doctor`, `history`, `memory`.
    * Built plugin subsystem: `plugins/{entrypoints,groups,hooks,registry}`.

* **Infra layer** (`infra/`)

    * Implemented `emitter`, `observability`, `process`, `retry`, `serializer`, `telemetry`.

* **Command suite**

    * Added top-level commands: `audit`, `docs`, `doctor`, `help`, `repl`, `sleep`, `status`, `version`.
    * Added `config/` commands: `clear`, `export`, `get`, `list`, `load`, `reload`, `set`, `unset`, `service`.
    * Added `dev/` commands: `di`, `list-plugins`, `service`.
    * Added `history/` commands: `clear`, `service`.
    * Added `memory/` commands: `clear`, `delete`, `get`, `list`, `set`, `service`.
    * Added `plugins/` commands: `check`, `info`, `install`, `list`, `scaffold`, `uninstall`.

* **Structured output & flags**

    * Added JSON/YAML output via `--format`, pretty printing, and deterministic global flag precedence ([ADR-0002](https://bijux.io/bijux-core/bijux-cli/)).

* **API contract validation & testing**

    * Automated lint/validation of `api/*.yaml` with Prance, OpenAPI Spec Validator, Redocly, and OpenAPI Generator.
    * Added **Schemathesis** contract testing against the running server.
    * Pinned OpenAPI Generator CLI version via `OPENAPI_GENERATOR_VERSION` and automated Node.js toolchain setup in Makefile.

* **Documentation tooling**

    * Integrated MkDocs (Material), mkdocstrings, literate-nav, and ADR index generation.

* **Quality & security pipeline**

    * Added formatting/linting: `ruff` (+format).
    * Added typing: `mypy`.
    * Added docs style/coverage: `pydocstyle`, `interrogate`.
    * Added code health: `vulture`, `deptry`, `radon`, `codespell`, `reuse`.
    * Added security: `bandit`, `pip-audit`.
    * Added mutation testing: `mutmut`, `cosmic-ray`.

* **SBOM**

    * Generated CycloneDX JSON for prod/dev dependencies via `make sbom` (uses `pip-audit`).

* **Citation**

    * Validated `CITATION.cff` and added export to BibTeX/RIS/EndNote formats via `make citation`.

* **Makefile architecture**

    * Modularized the Makefile into `makefiles/*.mk` for maintainability and clear separation of concerns.
    * Centralized all developer workflows (`test`, `lint`, `quality`, `security`, `api`, `docs`, `build`, `sbom`, `citation`, `changelog`, `publish`) in one consistent interface.
    * Added `bootstrap` target for idempotent virtualenv setup and Git hook installation from `scripts/git-hooks` (skips re-installation if already linked).
    * Added `all-parallel` target to run independent checks (`quality`, `security`, `api`, `docs`) concurrently for faster CI/CD.
    * Added `make help` for self-documenting targets with grouped sections.
    * Provided helper macros (`run_tool`, `read_pyproject_version`) to standardize tooling invocation.

* **tox orchestration**

    * Configured multi-Python test envs (`py311`, `py312`, `py313`).
    * Mapped Makefile workflows into tox envs (`lint`, `quality`, `security`, `api`, `docs`, `build`, `sbom`, `changelog`, `citation`) to ensure reproducibility.
    * Passed `MAKEFLAGS` to execute Makefile targets inside tox-managed virtualenvs.

* **Continuous Integration**

    * Added **GitHub Actions** workflow running tox across Python versions with Node.js 20 and Java 17 for API checks.
    * CI/CD pipelines directly leverage the modularized Makefile for consistent local/CI behavior.

* **Packaging / PyPI page**

    * Built dynamic long description via **hatch-fancy-pypi-readme** from **README.md** and **CHANGELOG.md** for PyPI/TestPyPI.
    * Packaged with `LICENSES/`, `REUSE.toml`, `CITATION.cff`, and `py.typed` included in source distributions.

### Changed

* Released initial public version.

### Fixed

* None


[Unreleased]: https://github.com/bijux/bijux-core/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/bijux/bijux-core/compare/v0.3.6...v0.4.0
[0.3.6]: https://github.com/bijux/bijux-core/compare/v0.3.5...v0.3.6
[0.3.5]: https://github.com/bijux/bijux-core/compare/v0.3.4...v0.3.5
[0.3.0]: https://github.com/bijux/bijux-core/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/bijux/bijux-core/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/bijux/bijux-core/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/bijux/bijux-core/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/bijux/bijux-core/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/bijux/bijux-core/releases/tag/v0.1.0

[Back to top](#top)
