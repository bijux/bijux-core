# Reproducible self-hosted diagram dependency

Build the maintained Mermaid ESM graph rather than patching a minified vendor file.
The exact pins are Mermaid 11.17.2, DOMPurify 3.4.16, KaTeX 0.18.2 and esbuild 0.28.2.
Both direct dependencies and npm overrides pin the sanitizer/math dependencies that
Mermaid imports from its core ESM modules. Npm package semver metadata alone does not
identify a prebuilt browser bundle's embedded dependency versions.

The previous stock Mermaid 11.6.0/DOMPurify 3.2.4 pair predates applicable upstream
2025/2026 diagram and sanitizer fixes. Stock Mermaid 11.17.2 still embeds DOMPurify
3.4.12 in its full browser distribution. Building its dependency-resolving ESM entry
with the patched override removes the need to rely on an IN_PLACE applicability
exception. KaTeX 0.18.2 fixes the inherited-prototype trust gadget discovered by the
resolved-graph audit; its override is outside Mermaid's declared 0.16 range, so actual
math/browser compatibility is mandatory and was qualified in the local corpus.

## Governed source and generated evidence

| File | Responsibility |
| --- | --- |
| `package.json`, `package-lock.json` | Exact direct/override pins, complete transitive registry origins and integrity. |
| `install.mjs`, `Makefile` | Artifact-confined clean install/audit and install/build/check targets, with lifecycle scripts disabled. |
| `build.mjs` | Reject altered installed manifests/pins, confine output, resolve patched ESM graph, bundle one self-hosted IIFE and inventory all bundled source/license identity. |
| `provenance.json` | Retained qualified builder/lock/input/output identities and all 64 bundled package versions/licenses. |
| `THIRD-PARTY-LICENSES.txt` | Full admitted dependency license text, including README license sections where upstream has no standalone license file. |
| `qualify.mjs` | Actual Chromium/Firefox/WebKit API/render/SVG safety and math fixtures on the exact output bytes. |

Generated minified bytes and receipts go under the active repository's `artifacts/`.
The asset owner copies a qualified candidate into the governed vendor destination,
updates SRI/baseline/contract references and preserves its legal notices. This tool
never performs that copy, modifies consumer sources or publishes a website.

## Install, build and qualify

Use Node 22 or newer; the recorded local qualification used Node 24.3.0 and npm 11.4.2.
The standalone targets also support inclusion from the repository docs Make domain.
Install into artifacts with lifecycle scripts disabled and require a zero-advisory audit:

```sh
make -f shared/bijux-docs/tooling/diagrams/Makefile diagrams-install
make -f shared/bijux-docs/tooling/diagrams/Makefile diagrams-build
make -f shared/bijux-docs/tooling/diagrams/Makefile diagrams-check
```

The platform-specific esbuild package is installed by the lock's optional dependency
selection; no lifecycle script is needed for the validated platform. Do not copy
`node_modules` between operating systems. Re-run clean `npm ci` before qualified
reproduction and retain the actual bundled input hashes; an unchanged version string
is not proof of clean dependency bytes. Full build reproduction compares bytes,
provenance and legal notices from two artifact outputs. Missing installed tooling fails
qualification with its preparation command; it cannot produce a skipped green result.
A read-only prepared runtime can be supplied with `DIAGRAM_DEPENDENCIES` to Make or
`BIJUX_DIAGRAM_DEPENDENCIES` to the Python tests. `DIAGRAM_ARTIFACT_ROOT` remains confined
to the active repository's `artifacts/` directory.

The governed provenance contains platform-independent source, package, input, output
and license identity. Each generated `build-receipt.json` separately records the actual
Node version, operating system and architecture. Node 24.3.0 is an observed qualification
version, not a fabricated requirement to make JSON comparisons pass. A fresh Linux/macOS
build must match governed provenance and output bytes; cross-platform equivalence is
required by those checks but has only been executed on the recorded local platform.

After preparing the repository's existing Playwright runtime/browsers:

```sh
PLAYWRIGHT_BROWSERS_PATH="$PWD/artifacts/bijux-docs/playwright/browsers" \
  node shared/bijux-docs/tooling/diagrams/qualify.mjs \
  --bundle artifacts/website-security/dependencies/renderer/mermaid-11.17.2.min.js \
  --playwright artifacts/bijux-docs/node-runtime \
  --output artifacts/website-security/dependencies/browser-corpus.json
```

Each case has a 10-second Node-side qualification deadline; a timeout closes the browser
and retains a failed partial report. This bounds the qualification runner without claiming
a JavaScript timer can interrupt synchronous renderer work inside a page.

The 30-case corpus covers flow/sequence/class/state/Gantt/pie/math and local malicious
HTML/link/directive inputs across three engines. Valid diagrams must produce parsed
SVG; hostile HTML/directive labels may be rejected as malformed SVG, with no executable
payload. Safe rejection is separately recorded and requires source fallback in the
shared runtime. This is an API/vendor boundary test, not whole-product diagram,
phone shell, screen-reader or live-publication certification.

The browser fixture also keeps a native `.mermaid` block unrendered even when a preceding
`window.mermaid_config` requests automatic startup. The entry sets `startOnLoad` false and initializes strict defaults, then exports the
existing `window.mermaid.initialize/render` API. The application remains the sole
owner of lazy loading, SRI checks, protected configuration, serialized generation,
DOMParser insertion and source fallback. No CDN chunk or optional icon provider is
admitted by this build; any future external registration needs separate review.

Strict mode does not make a permitted `<img src>` private: Mermaid may insert sanitized
labels into temporary live HTML before sanitizing the final SVG, which can start image
requests. The application must admit diagram source before render and protect a sanitizer
policy that forbids request-bearing resources. Final SVG checks alone happen too late.
The API corpus's sanitized-output checks do not certify zero network side effects.

## Maintenance and limits

Before changing pins, read [Mermaid advisories](https://github.com/mermaid-js/mermaid/security/advisories),
[DOMPurify advisories](https://github.com/cure53/DOMPurify/security/advisories) and
[KaTeX advisories](https://github.com/KaTeX/KaTeX/security/advisories).
The admitted local graph reported zero npm audit advisories on 8 October 2026. That
is a time-scoped registry result, not proof of immunity or a substitute for explicit
feature/advisory review. Rerun it at dependency changes and publication qualification.

Rebuild, compare full identities, qualify the real diagrams and hostile corpus, retain
licenses and review the generated projection. Update provenance only from an actually
qualified rebuild; replacing an expected digest with arbitrary current bytes is not
verification. A dependency update invalidates affected diagram/runtime/consumer receipts.
Never hand-edit bundled sanitizer code or jump to a major version solely for prestige.

## Website renderer ownership

Mermaid source fences keep the authored language name `mermaid` and emit the
`bijux-diagram` class. Material must never own those nodes: its `mermaid` class
activates an independent remote renderer. The shared initializer owns discovery,
serialized render requests, palette changes, stale document completions and retry.

The baseline pins Mermaid 11.17.2 by SHA-256. Its owned vendor bundle and license
files project through the existing canonical asset projector. The initializer
loads that asset only when a diagram exists, uses SRI and strict security, and
retains the exact source in a disclosure for success and failure. Source directives
cannot change renderer security or import network resources. Source/edge admission
limits are 50,000 characters and 500 edges; these are declared limits, not evidence
of arbitrary corpus scalability. Failed or timed-out loading exposes source and
an ordinary Retry diagram button.

`sync_mkdocs_hub.py` migrates block-form Mermaid fences and removes eager versioned
vendor entries while preserving other MkDocs configuration, including the logo.
Effective root/shared configuration and the projected bundle digest are validated
before publication. Unsupported configuration shapes fail contract verification;
they must be reviewed rather than silently rewritten.

Run the asynchronous lifecycle contracts with `python3 -m unittest discover -s
tests -p test_shared_mermaid_lifecycle.py`, and the real MkDocs/Material browser
gate with `make ui-test-diagrams`. The browser gate covers no-diagram lazy loading,
actual light/dark SVG rendering, ordinary instant navigation, missing-bundle
fallback, keyboard retry and absence of remote renderer imports.
