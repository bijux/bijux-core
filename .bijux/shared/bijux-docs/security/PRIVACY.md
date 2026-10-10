# Documentation data flows

The shared documentation shell serves public static content. This document
explains its browser data flows and the boundaries consumers must review. Each
consumer owns its authored embeds, provider activation and visitor-facing
privacy information. Hosting administrators own actual request logging, access
and retention settings. A local search algorithm does not establish that every
consumer makes no third-party requests.

## Browser preferences and local search

The `bijux:theme` localStorage record stores the admitted auto/light/dark choice
and palette signature. Product paths on one origin deliberately share this
benign setting. Material also uses path-scoped `__palette` and, with linked
content tabs, `__tabs` label preferences. Persistent preferences have no
configured time expiry; the visitor or browser clears them. The shared storage
API bounds records and keeps an in-memory fallback when persistence is denied.
Product path names are not security isolation from scripts on the same origin.

Search loads the site's intentionally public `search_index.json` and sends
queries to a dedicated local worker. The shared adapters admit same-origin HTTP
or HTTPS index and worker URLs; the worker URL must remain in the configured
site path. This worker is distinct from a service worker or offline application
cache. The common runtime has no remote search-service endpoint and does not
write query history to preference storage. This statement does not cover
additional consumer scripts or browser/hosting diagnostics.

Material can produce a `q` search-sharing URL or `h` highlight URL. When such a
URL is requested or shared, its terms may reach the site recipient, browser
history or referrer processing. Local worker execution does not make those URL
terms private. Diagnostic exports should omit terms, full query strings and
identifiers unless a reviewed troubleshooting need requires them.

## Optional repository metadata

Repository navigation remains available by default. The shared source partial
adds Material's facts component only for the literal Boolean
`extra.bijux.repository_facts: true`; absent, false or malformed values do not
activate it. The configuration validator rejects malformed values. See the
[configuration contract](../CONTRACT.md#configuration-and-consumer-extension-points).

With explicit opt-in, Material can fetch public repository counts and release
metadata from `api.github.com`, or the configured GitLab provider's API, and
cache facts in path-scoped `__source` sessionStorage. A cold cache and no
configured consent component can trigger that request without clicking the
repository link. The admitted native component consults its consent setting
when that component is configured; opting into statistics is not evidence that
a consumer has configured or qualified consent behavior. Session caching does
not constrain provider request logs or retention.

A consumer enabling facts must record its purpose, actual provider/trigger,
compatible response policy and visitor disclosure decision. Preserve the
repository destination when facts are disabled. Do not widen an unrelated
network policy or suppress diagnostics to conceal an undeclared request.

## Shared assets and external links

The baseline disables remote theme fonts and selects local shell assets. The
owned diagram initializer lazily loads the packaged Mermaid vendor asset from
the site. These defaults do not establish the request behavior of authored
scripts, plugin output, social cards, embeds or a host's injected resources.
Review the effective configuration and rendered requests for each consumer.

The external-link producer preserves authored destinations, target, download
and referrer intent. It adds `noopener` to explicit `_blank` links while keeping
other relationship tokens and removing contradictory `opener`. It does not
open a window or issue requests to resolve destinations. Following a link
activates its recipient through the browser. `noopener` protects the opener;
it does not select a referrer policy or make the destination private.

## Scientific maps and external resources

An authored scientific map is executable content with its own producer and
public-data authority. A same-origin iframe does not isolate it from other
scripts on the same origin. Review the exact report, parent routes, local
resources, executable source and provider origins before admitting publication.
A source hash alone is not an accepted producer or input checkpoint.

Existing Pollenomics map sources select OpenStreetMap street tiles by default
and offer OpenTopoMap terrain tiles or no basemap. Their failure handler can
select another provider automatically after repeated tile errors. Tile requests
expose the viewed coordinates to the recipient. Disclosure and capability
policy must account for initial requests and automatic fallback; describing all
tile requests as separately activated by the visitor would be inaccurate.
Retain provider attribution and a working no-basemap choice. Map image needs do
not justify allowing those providers on every documentation page.

## Ownership and change review

Std owns common storage schemas, local search/runtime behavior and diagnostic
minimization conventions. Consumers own authored embeds, optional metadata
activation, public-content classification, contact details and accurate
disclosures. Hosting owners establish actual provider logging, retention,
access and response policy. Repository administration does not establish DNS
or hosting capability, and source review does not establish live settings.

Reassess these flows when introducing telemetry, remote search, cookies, forms,
authentication, uploads, payments, APIs, service workers or less-trusted
interactive content. Review their actual recipients, triggers, retained values,
controls and ownership before making visitor-facing claims. This technical
document does not certify a consumer's legal compliance or require an
unimplemented consent interface.
