# Publication validation ownership

`validate_site_routes.py` is the public command for checking an already built
artifact. It selects the site root and production URL, then combines route and
search qualification. Its command arguments, reports and refusal behavior
remain stable.

| Module | Responsibility |
| --- | --- |
| `routes.py` | Build the deterministic HTML inventory, combine document and graph checks, and emit route records. |
| `documents.py` | Parse HTML anchors, canonical and refresh declarations, responsive image candidates, inline SVG references and Material search configuration. |
| `destinations.py` | Resolve URLs against the selected artifact, distinguish neighboring published products and enforce public origin authority. |
| `redirects.py` | Admit explicit refresh destinations and traverse redirect graphs for cycles. |
| `resources.py` | Resolve stylesheet and SVG resource references against actual owned files and symbol IDs. |
| `style_references.py` | Tokenize stylesheet resource syntax with source positions. |
| `svg_references.py` | Interpret SVG resource declarations and standalone symbol inventories. |
| `sitemaps.py` | Reconcile canonical route membership and plain/compressed sitemap equality. |
| `search.py` | Validate the emitted index and worker against route and anchor ownership. |

The route coordinator owns qualification order. Parsing modules collect evidence;
URL resolution owns production and artifact boundaries; graph validators consume
those facts. Resource parsing does not grant remote or neighboring-site authority.
Sitemap admission uses eligible canonical routes after redirect and noindex
interpretation. Keep diagnostics in their original deterministic order, including
source positions and recorded exception observations.

These checks inspect a local generated artifact. They do not fetch external sites,
run a browser, publish a site or certify live delivery. Missing, malformed and
private destinations remain refusals. An authored development-link exception
cannot authorize an automatic redirect or active resource.

The existing `tests/test_public_site_routes.py` suite exercises deliberately
broken artifacts through the public qualification entrypoint. The owning
`tests/test_docs_site_verification.py` suite exercises command and generated
output behavior. Use those checks for changes to these boundaries; rendering and
browser qualification belong to the affected website candidate.
