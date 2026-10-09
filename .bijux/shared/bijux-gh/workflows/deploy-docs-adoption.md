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
