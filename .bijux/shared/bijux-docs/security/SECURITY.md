# Public documentation security contract

Bijux documentation is authored static MkDocs/Material content. Protect public
content integrity, trustworthy navigation/search, intentionally public artifacts,
publication credentials and the domain. Product paths on `bijux.io` share script
and storage authority; path names are not security isolation boundaries.

| Input and trust boundary | Owner and required control |
| --- | --- |
| Authored Markdown/raw HTML/diagram → rendered page | Consumer reviews content and exceptional embeds; shared renderer validates executable URLs and admitted parser behavior. Code examples use text/escaping rather than executable markup. |
| Shared scripts/template/config → consumer | Std owns tested common defaults; exact accepted source and generated checksum authority precede managed adoption. |
| Dependency/action → build or browser | Full-SHA action pins and exact frontend version/hash inventory; review actual affected advisories, not just mode/version labels. |
| PR/build → privileged publication | Read-only validation/build, nonpersisted checkout credentials, trusted event/ref and deploy-only Pages/OIDC permissions. Administrators verify actual environment/ref controls. |
| Verified output → public Pages bundle | One configured `artifacts/` path, mandatory consumer verifier, public-file admission and unchanged per-file digest before upload. |
| Theme/search/diagnostics → storage or recipient | Benign namespaced preference only; local search stays local. Redact search/query/token data from evidence; no new visitor telemetry by default. |
| Account/DNS/TLS → serving origin | Actual owner/settings/access recovery; effective response checks instead of unsupported host configuration files. |

The Mermaid renderer uses a pinned vendor, secure configuration and an explicit
trusted SVG parsing boundary. Strict mode and an integrity hash do not eliminate
vendor vulnerabilities. Qualify the exact maintained version against official
advisories and legitimate/hostile diagram corpus; a DOMParser-created SVG is still
an executable DOM boundary requiring the renderer's sanitization and URL policy.
Text source fallback, size limits and stale-generation rejection protect failed
or superseded rendering. Browser negative fixtures must prove script/link/directive
safety on the shipped version before broad release claims.

`publication.py config` rejects foreign/loopback production identities, unsupported
or PR events, feature refs, missing verification, control characters and output
traversal/symlinks. Default-branch and semantic version tags are admitted. Checked-in
shell configuration and command overrides remain reviewed author-owned code;
this is not a sandbox for a malicious repository maintainer.

`publication.py admit` inventories the exact selected output, rejects dot/private
configuration files, keys/token markers, unadmitted extensions/maps, executable URL
attributes, inline handlers, HTTP resource URLs and bad production canonicals.
Errors print classifications and file paths, never matching private bytes.
`policy.json` records size/file budgets and narrowly purpose-owned public exceptions;
pinned Material runtime/styles source maps are intentionally public. Heuristic
private-marker scanning is defense in depth and cannot prove every conceivable
secret is absent; content review remains necessary, particularly for intended
archives/downloads and sensitive scientific reports.

Published SVG files must also remain passive when opened directly as documents.
The admission guard requires bounded UTF-8 XML and rejects executable elements,
event attributes, animation-driven mutation, entity declarations, stylesheet
instructions, resource base overrides and external automatic resources, including
escaped CSS URLs. Static scientific figures may retain local glyphs/clips and
embedded raster images. The default 16 MiB SVG ceiling is an admission budget,
not a hosting limit. Flatten intentional interactive figures to passive artwork
or review a distinct delivery boundary; public-file exceptions do not bypass this
guard. Runtime Mermaid SVG belongs to the separately qualified renderer boundary.
[SVG image restrictions](https://developer.mozilla.org/en-US/docs/Web/SVG/Guides/SVG_as_an_image)
do not protect directly opened SVG documents, and XML parsers require explicit
[entity and resource considerations](https://docs.python.org/3/library/xml.html#xml-vulnerabilities).

Publication requires a clean source checkpoint, the tracked exact
`.github/standards/bijux-std.sha` and a clean checkout independently fetched from
the official GitHub origin into `artifacts/`. The consumed shared documentation
must match that fetched tree; ignored extra standard inputs cannot inherit its
commit identity. Local-source bypasses and candidate-only receipts cannot publish.

The source-derived reconstruction framework is optional. Its source-owned profile
registry currently admits the retained Darwin environments for verification only;
no Linux publication profile is approved. Enable `DOCS_PUBLICATION_FRAMEWORK=1`
only with an explicitly selected accepted shared directory and actual renderer.
Candidate builds can produce attributable receipts under the retained verification
profiles; a clean source checkpoint cannot promote them to publication. Approve
hosted runtime/startup/native/plugin/callback closure through a reviewed source
change before enabling publication for a caller. Renderer observation reports
never create admission by themselves.

Reviewed producer adapters preserve actual redirects, revision-date configuration,
registered callbacks and the two observed source asset/root icon recipes. Unknown
plugins/hooks, shadow imports, replaced callbacks, unlisted physical inputs and
mismatched bytecode fail. Generated catalog Markdown outside the tracked source
requires its own generator/source attribution; a build-date fallback proves
neither authored freshness nor science qualification.

Run [build_identity.py](build_identity.py) with the actual `DOCS_PYTHON` immediately
before rendering and after CSP transformation. It records the loaded MkDocs
configuration, resolved environment values as a digest, source/override inputs,
actual renderer interpreter/packages/plugins and Material policy-template bytes.
It rejects input, configuration, policy-processor or toolchain changes between
those boundaries. The guard's system Python is not substituted for the renderer.
Generated inputs under `artifacts/` remain the reviewed builder's responsibility;
authored renderer inputs outside artifacts must belong to the selected Git tree.

The publication manifest identifies every public file, the exact standard/source,
policy and four retained receipts: clean source, completed actual renderer, passed
route/search/public URL checks and applied early CSP. All artifact receipts must
identify the same production URL, output directory and bundle bytes. CSP processor
and canonical override hashes must match accepted source; its installed-template
hashes must match the actual renderer. Missing checks, stale receipts, changed
exception policies and broadened or late CSP fail admission.

Keep receipts outside the uploaded bundle. `verify --require-qualified` repeats
source and receipt admission immediately before upload. Ordinary `verify` checks
retained bytes/policy for offline previous-good recovery; it does not claim a new
source qualification. Neither mode proves live deployment, repository environment
protections, browser/manual acceptance or a provider's deployment identity.

From a consumer with synchronized shared source:

```sh
python3 .bijux/shared/bijux-docs/security/publication.py config \
  --repository bijux/bijux-core --event workflow_dispatch --ref refs/heads/main \
  --default-branch main --site-url https://bijux.io/bijux-core/ \
  --site-dir artifacts/docs/site --verify-command 'make gh-docs-verify'
python3 .bijux/shared/bijux-docs/security/build_identity.py capture-source \
  --source-sha "$BIJUX_SOURCE_SHA" \
  --standard-root artifacts/website-security/accepted-standard \
  --site-dir artifacts/docs/site --site-url https://bijux.io/bijux-core/ \
  --build-command 'make docs-check' --verify-command 'make gh-docs-verify' \
  --output artifacts/website-security/source-identity.json
DOCS_PUBLICATION_FRAMEWORK=1 BIJUX_DOCS_SHARED_DIR=.bijux/shared/bijux-docs \
  DOCS_SOURCE_IDENTITY=artifacts/website-security/source-identity.json \
  BIJUX_STD_ROOT=artifacts/website-security/accepted-standard \
  make docs-check
python3 .bijux/shared/bijux-docs/security/publication.py admit \
  --site-dir artifacts/docs/site --site-url https://bijux.io/bijux-core/ \
  --source-sha "$BIJUX_SOURCE_SHA" \
  --source-identity artifacts/website-security/source-identity.json \
  --build-identity artifacts/website-security/build-identity.json \
  --verification-report artifacts/website-security/site-verification.json \
  --csp-report artifacts/website-security/csp.json \
  --output artifacts/website-security/publication.json
python3 .bijux/shared/bijux-docs/security/publication.py verify \
  --manifest artifacts/website-security/publication.json --require-qualified
```

Prepare `accepted-standard` at the tracked pin before capture; capture fetches that
exact object again and checks clean HEAD/origin/tree. Framework caller wiring must
provide this checkpoint explicitly; the ordinary shared workflow currently owns
event/ref, exact output and consumer verifier mechanics. Automatic framework
activation remains pending actual hosted profile and caller qualification.
Custom builders must produce the same renderer/CSP/verifier receipts using their
actual configuration and interpreter. A multi-generator consumer must also retain
its generator-specific inputs/toolchain evidence; the shared renderer receipt does
not invent evidence for unused Node, Rust or application Python environments.

Static native Pages has no assumed arbitrary response-header/purge interface.
Prefer effective response CSP when supported; correctly ordered HTML meta CSP has
limited scope and cannot supply framing/report-only controls. HSTS/nosniff and
other response policies require actual hosting support; document a bounded residual
risk or reviewed serving-layer decision instead of treating ignored files as
controls. No automatic hosting migration, preload, analytics, consent banner,
authentication, payment or upload feature is required for documentation.

Inventory actual cookies/storage/network recipients with purpose/data/retention/
owner; theme preferences are not automatically tracking. Provider request behavior
requires current provider evidence. Legal disclosure/consent depends on confirmed
processing and applicable jurisdiction, reviewed by the responsible owner. Reopen
this model if visitor contributions, forms, uploads, sessions/APIs or less-trusted
interactive applications are introduced.
