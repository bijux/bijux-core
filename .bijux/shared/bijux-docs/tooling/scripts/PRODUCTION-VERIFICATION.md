# Production documentation verification

Builds and publication must refer to one exact static artifact. A successful
root request or Markdown build does not prove search delivery, deep routes,
anchors, canonicals, or sitemap eligibility.

When explicitly enabled with `DOCS_PUBLICATION_FRAMEWORK=1` and an admitted
verification/publication profile, the Python docs profiles use the actual
`DOCS_PYTHON` renderer for this sequence:

1. Independently verify the exact fetched shared standard before cleaning outputs.
2. Check the actual installed Material renderer and generated runtime against admission.
3. Capture effective MkDocs config, renderer dependencies and source identity.
4. Build the configured production URL into the exact `artifacts/` output.
5. Apply the admitted CSP to that output.
6. Finish build identity against the resulting exact bytes.
7. Verify route, link, sitemap and native search contracts against those bytes.

Canonical configuration excludes implementation templates and hooks from public
output. Synchronization preserves authored exclusion rules and finishes both
shared and root pathspecs with that boundary, so a root override cannot publish
the renderer's own files. Bytecode caches are disabled while the renderer and
verification tools read the managed source tree.

Local development serving retains its loopback URL and does not certify
production. Local candidate work requires `BIJUX_STD_LOCAL_VERIFY=1`; its receipts
remain `verification_only: true` and cannot pass publication admission. Accepted
publication requires the clean source checkpoint and independently fetched exact
GitHub standard supplied explicitly by a qualified framework caller. Automatic
framework workflow activation remains pending actual hosted profile qualification. No sibling checkout or
remote HEAD fallback supplies authority.

## Consumer verifier

The reviewed consumer `gh-docs-verify` or `docs-verify` command invokes:

```sh
DOCS_PYTHON=artifacts/docs/python/bin/python \
DOCS_SITE_DIR=artifacts/docs/site \
SITE_URL=https://bijux.io/bijux-core/ \
  bash .bijux/shared/bijux-docs/tooling/scripts/verify_bijux_docs_site.sh
```

Use the actual builder environment and repository production URL. The verifier
requires an exact output selection; it does not discover another artifact when
that directory or a worker is missing. With `DOCS_CONFIG_FILE` provided, a blank
URL derives the actual loaded production default from that configuration.

The source verifier also runs the artifact checks when `DOCS_SITE_DIR` is
explicitly supplied. Without that variable, it makes a source-only claim.
Rust or other custom builders must place their existing build between the same
identity capture, CSP, finish and verifier boundaries; installing the Python
Make profile into an unrelated builder is not required.

`artifacts/website-security/site-verification.json` records the mechanical scope,
individual results, exact public bundle digest, and observed development links.
It does not certify browser interaction, manual accessibility, remote
publication, or deployment health. The publication guard binds it to source,
build and CSP receipts before upload.

## Authored development examples

Active links to loopback, private, reserved or development hosts fail public
verification even when they point outside the site's local route tree. Display
commands and example URLs in code blocks when readers should not navigate them.
A tutorial that intentionally opens its own local service may supply a reviewed
repository policy with `BIJUX_DOCS_DEVELOPMENT_LINK_POLICY`:

```json
{
  "schema": 1,
  "exceptions": [
    {
      "route": "tutorial/local-server/index.html",
      "url": "http://localhost:8000/",
      "purpose": "Open the tutorial server after the reader starts it locally"
    }
  ]
}
```

Each exception identifies one exact HTML route and link URL. Its purpose and
policy digest are retained in verification. Exceptions never admit scripts,
styles, images, CSS imports, forms, or other active resources. The policy stays
in reviewed repository source outside the published artifact.

## Exact artifact publication

`make docs-deploy` rejects the rebuilding `mkdocs gh-deploy` path. MkDocs 1.6.1's
command always rebuilds before publishing and offers no option to publish only
the previously qualified artifact. That rebuild would discard the applied CSP
and disconnect the upload from its recorded bytes.

Use `make docs-check` to build and qualify the artifact, and publish through the
reviewed GitHub Pages workflow. Configure its exact `BIJUX_DOCS_SITE_DIR` and
reviewed `BIJUX_DOCS_VERIFY_COMMAND`, retaining the source, build, CSP and verifier
receipts outside the uploaded directory. The workflow must upload those same
qualified bytes; another build between qualification and upload invalidates
identity and must be rejected.
