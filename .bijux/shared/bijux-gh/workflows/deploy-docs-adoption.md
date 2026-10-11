# Documentation publication adoption

Adopt the shared workflow and its publication guard from the same accepted exact
`bijux-std` GitHub SHA. Generated consumer workflow copies must remain synchronized;
product owners configure their build/content rather than hand-editing managed copies.

1. Inspect the consumer's actual strict build, verifier and output directory.
   Expose `gh-docs-install`, `gh-docs-build` and `gh-docs-verify`, or configure reviewed
   equivalent commands. A missing verifier fails publication instead of being skipped.
2. Select one output directory under `artifacts/` and the exact production identity:
   hub `https://bijux.io/`; product `https://bijux.io/REPOSITORY/`. Build commands receive
   `DOCS_BUILD_SITE_URL`, `SITE_URL` and `DOCS_SITE_DIR`; they must actually honor them.
3. Configure repository variables or reviewed `.github/docs-deploy.env` when defaults
   differ. Masterclass, for example, may select `artifacts/site/bijux-masterclass`
   with its series build/verify commands. No stale directory discovery is allowed.
4. Qualify the exact generated output using the consumer verifier and shared
   publication guard. Include missing search, bad canonical, private-file and wrong
   output fixtures. Keep public downloads/source-map exceptions narrow and justified.
   Adopt the actual-renderer `build_identity.py begin/finish` boundaries around
   MkDocs build and CSP transformation. Use identical interpreter/environment and
   effective config; finish after CSP, then run mechanical route/search/URL checks.
   Required receipts are `source-identity.json`, `build-identity.json`,
   `site-verification.json` and `csp.json` under `artifacts/website-security/`.
   Missing, stale or candidate-only receipts cannot publish.
5. Verify managed checksum/source authority. Record branch/base, tested commit order,
   source/std/toolchain/config, bundle identity and concrete PR/publication handoff.
   A framework-enabled caller must fetch the tracked exact pin independently and
   reject dirty source or consumed shared trees differing from it. The ordinary
   shared workflow handles trusted refs, exact output and mandatory verifier;
   automatic framework wiring remains pending hosted profile/caller qualification. Retain relevant generator-specific
   evidence for custom or series builds; setup defaults are not actual toolchain proof.
6. Have the actual repository administrator review Pages and environment/ref settings.
   Deploy accepts the default branch or version tags and refuses pull-request events;
   reusable callers receive the same restriction. Run only already authorized remote
   publication actions, then verify live root/deep/menu/search/metadata and identity.

Every published consumer, including Atlas, requires an actual verifier. Shared
workflow changes do not create missing consumer targets, correct a build that ignores
production configuration or prove account settings. Complete local qualification
before publication; keep blocked remote/admin/manual evidence accurately unresolved.

Use [security](../../bijux-docs/security/SECURITY.md) for trust and public-artifact
admission and [operations](../../bijux-docs/security/OPERATIONS.md) for local smoke,
cache compatibility, monitoring limits and recovery.

Repository publication entrypoints can be explicitly selected in the canonical
repository manifest through `workflow_execution_policy.publication_entrypoints`.
The supported `deploy-docs`, `release-github`, `release-ghcr` and `release-crates`
entries accept `mode: manual-only` or `mode: canonical`. Manual-only removes the
reusable `workflow_call` API while preserving the exact dispatch inputs, defaults,
help text and publication jobs. Canonical mode and an absent selection retain the
shared callable API. Local workflow or wrapper calls to a selected manual-only
publisher fail canonical preparation before files are written; internal
`release-artifacts` calls remain callable.

This selection supplies no publication authorization, profile qualification or
production evidence. Ref admission and existing source/artifact/verifier guards
remain separate requirements. Release tag resolution still honors an explicit
input before its existing defaults; changing workflow entrypoint selection does
not change that resolver.

Documentation owners can explicitly select
`publication_entrypoints.deploy-docs: {mode: manual-only, refs: main-only}`
in the canonical repository policy. This restricts both publication jobs to
`workflow_dispatch` on the literal `refs/heads/main`, independently of the
repository default branch. The existing deploy dependency and `site_available`
check remain intact. The named publication event/ref shell guard runs first,
before checkout, configuration, installation or artifact writes, and repeats
the same exact event/ref restriction. Tags, other branches and reusable calls
cannot qualify this selected publication path.

Projection admits the reviewed build/deploy conditions and shell guard before
writing managed output. Missing, ambiguous or changed guard bodies and job
predicates require review of the canonical source; they are not silently
rewritten. All other dispatch, build, artifact, profile and deployment content
stays source-owned. Absent policy or `refs: canonical` preserves the canonical
ref guard. This selection does not authorize publication or establish deployed,
manual or profile evidence.

## Canonical workflow verification

The existing `policy / github` job verifies managed runtime bytes without rewriting
those files. Consumer verification reads the full tracked standard pin and fetches
that exact official GitHub source into the repository's `artifacts/` cache. The
source's own verifier checks the origin, full SHA and clean source independently,
then derives the selected repository policy and compares every governed input and
managed runtime. A local checksum or source snapshot does not establish accepted
source authority. The owning standard may qualify its current candidate explicitly;
that result does not certify accepted consumer adoption.

The governed `workflow-sources` snapshots preserve both base workflow originals and
the finite canonical input hashes. The standard must refresh these generated
snapshots when their actual owning inputs change. Verification checks the snapshots
against the original inputs and rejects source changes during comparison.

Only policies that require structural workflow projection provision the pinned
`ruby/setup-ruby` action and Ruby `3.3.12` in the existing policy job. The job asserts
the actual Ruby version and Psych parsing API before verification. The default raw
workflow path uses the Python standard library without this parser prerequisite.
Actual hosted parser execution and consumer adoption remain separate qualifications.
