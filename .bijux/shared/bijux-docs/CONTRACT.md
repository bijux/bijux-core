# Bijux documentation shell contract

Bijux extends the admitted MkDocs Material theme. MkDocs renders product content,
navigation, plugin output, and templates; Material retains its search worker,
ranking, content enhancements, and document stream. Bijux owns the shared
navigation shell, palette persistence, diagram renderer, and bounded integration
adapters. Product repositories own identity and authored content.

`config/mkdocs-baseline.json` defines the required effective theme, plugins,
extensions, ordered assets, and implementation exclusions. The configuration
validator checks the inherited result; lists in a root configuration replace
inherited lists. Required entries must therefore survive every root override.
The configuration projector preserves authored additions and their ordering,
and rejects unsupported shapes before writing either configuration file.

## Configuration and consumer extension points

| Field or extension | Type and default | Allowed values and ownership | Lifecycle and compatibility |
| --- | --- | --- | --- |
| `extra.bijux.repository` | Required nonempty string in `mkdocs.yml` | Identifier containing letters, digits, dots, underscores, or hyphens; first character is a letter or digit. Product identity need not be a current registry member. | Read at rendering and navigation binding. Never infer repository identity from a display label. |
| `extra.bijux.nav_mode` | Inherited string `default` | Only `default`; shared shell owns navigation policy. | Validated before rendering; another mode requires an explicit shared contract change. |
| `extra.bijux.theme_key` | Inherited string `bijux:theme` | Only `bijux:theme`; shared palette controller owns the storage record. | Shared across products; private storage signatures and Material indices may change together with the admitted renderer. |
| `extra.bijux.hub_links` | Inherited nonempty ordered list | Each entry has nonempty string `key`, `label`, and an absolute HTTP(S) `url` without credentials or whitespace. Keys are unique; values and order equal `config/hub-links.json`. | Registry changes originate upstream. The root configuration must not duplicate this field. |
| `extra.bijux.repository_facts` | Optional Boolean, default `false` | Explicit `true` enables Material's external repository-facts component. Product chooses the provider use deliberately. Strings and numbers are invalid configuration. | Plain repository navigation and its accessible name remain present when disabled. The template also fails safe for invalid values when rendered outside the validator. |
| `hooks` | Optional list of nonempty authored path strings | Product owns hook files and their behavior; MkDocs owns hook loading and existence checks. | Configuration validation checks shape without executing hooks. Existing authored hooks are retained, never silently replaced. |
| Root identity, `nav`, pages, plugin options | MkDocs types and defaults | Product-owned. Required shared capabilities remain present in the effective result. | Normal MkDocs validation and strict production build apply. This shell schema does not invent types for every third-party plugin. |
| `extra_css`, `extra_javascript` | MkDocs ordered lists | Product entries are preserved around the canonical ordered assets. Author script descriptors may retain their module/defer attributes. Canonical script dependencies may not be reordered or made asynchronous. | Projector and effective-assets validator share the ordering contract. Authored CSS is the extension mechanism for authored components. |
| `docs/overrides/partials/site-head.html` | Optional consumer-owned Jinja partial; absent adds nothing | Adds authored head content through the shared root template's `extrahead` block, after `super()`. | Rendered for root and deep pages. Consumer owns syntax and assets; an invalid partial fails the real build. Never replace the shared `scripts` block to add head links. |
| Authored Markdown components | Native Markdown, admitted extensions, and product-owned class names | Content, admonitions, tabs, tables, code, and authored component markup remain product-owned. | Use normal document content and authored styles/scripts; do not copy shared header/navigation runtime to create a product variant. |

Other product fields under `extra` or `extra.bijux` are preserved. An unknown
field does not acquire shared support merely by existing. Unsupported owned
modes, scalar namespaces, duplicate YAML keys, duplicate registry identifiers,
missing registry destinations, and malformed hooks fail with source and field
diagnostics. A `!ENV` value in a shell-owned field must resolve to its declared
type before it is supported; this validator does not execute an arbitrary
environment resolver. Product-owned tagged plugin values remain product-owned.

```yaml
extra:
  bijux:
    repository: bijux-core # authored root identity
    repository_facts: false
```

Navigation mode, theme key, and hub links are inherited from `mkdocs.shared.yml`.
The registry array is the presentation order in the header and complete sidebar.
Parent overview links are destinations; native `details`/`summary` controls only
disclose descendants. Neither control substitutes for the other.

## Public observations and private integration

| Surface | Contract | Ownership and lifetime |
| --- | --- | --- |
| `data-bijux-viewport` on `html` and `body` | Read-only string: `phone`, `normal`, `desktop`, or `wide`. Initial value is computed from viewport width. | Window-owned profile classifier; names describe CSS viewports, not physical devices. CSS remains authoritative for layout. |
| `bijux:viewport-change` on `window` | `CustomEvent.detail`: `{profile, previousProfile, width}`. Profiles use the enum above; initial `previousProfile` is `null`; width is a CSS-pixel number. | Fires when classification changes, including initial classification. Consumers may listen but must not write classifier state; remove consumer listeners on their own document disposal. |
| `bijux:theme-change` on `window` | `detail.mode` is `auto`, `light`, or `dark`; `detail.scheme` is the selected palette option's scheme, defaulting to `default`. | May repeat on mount. In auto mode the selected scheme is not an effective-darkness guarantee; read the resolved `body[data-md-color-scheme]` for painting. Consumer listeners must tolerate repeated notifications and dispose themselves. |
| `--bijux-*` variables declared in `styles/00-tokens.css` | Unregistered CSS token strings; literal base defaults live in `00-tokens.css`, with palette overrides in `01-theme.css`. Valid values must satisfy the consuming CSS property's grammar. | Consumer component styles may consume the token inventory. These are not registered typed properties; invalid overrides follow native CSS fallback and do not receive a contrast guarantee. Meaning changes/removal require consumer analysis and compatibility review. |

Theme event `scroll` metadata, `data-bijux-viewport-source/revision`,
`window.bijuxShell`, `window.bijuxViewportProfile` diagnostic methods, script
functions, `.bijux-*` shell selectors, and control/state `data-bijux-*` attributes
are private integration details. The two read-only observations above do not
make every prefixed attribute a supported product extension hook.

`window.bijuxSearchIndex`, `window.bijuxSearchWorker`, and their status, retry,
cancel, and location events are a private protocol between the admitted Material
adapter and `search-recovery.js`. Index readiness does not imply worker readiness.
Consumers use the named native search control and ordinary result destinations;
they must not write state, inject a second worker, or fabricate an empty corpus.

Material's `document$`, `__md_scope`, `__config`, palette helpers, component IDs,
search protocol, and `data-md-*` selectors are admitted upstream integration
points, not public Bijux APIs. Their source bytes and template boundary are
verified by `tooling/material/build_runtime.py`. An unsupported installed Material version fails when the exact compiler runs;
there is no guessed adapter. The admitted Python Make profile calls that
compiler through its renderer interpreter before destructive cleanup. Schema
validation and source-ownership preflight do not supply that interpreter check:
the standard-library projector does not run the compiler, and other authored
or generic Make entrypoints require their own explicit admission boundary.
Do not infer that every consumer runner is admitted from copied shared files.
See [Material adapter admission](tooling/material/README.md).

## Shared ownership and verification

Every row has one behavior producer. Product configuration/content and Material
base templates are inputs to that producer, not competing controllers.

| Shared surface | Producer and consumer boundary | Executable verifier |
| --- | --- | --- |
| `partials/main.html` | Compiler owns the admitted runtime script replacement; Material owns `base.html` layout; consumer optionally owns `partials/site-head.html`. | `generated/test_material_runtime.py`, `generated/test_template_extensions.py`, source projection tests |
| `partials/header.html` | Shared header/control markup consumes product identity and the canonical registry. Material supplies icons/palette markup. | Generated shell journeys; navigation projection fixtures |
| `partials/nav.html`, `partials/nav-item.html` | Shared complete recursive native tree consumes MkDocs `nav` and page state. | Generated overview/disclosure/current-page/all-registry journeys |
| `partials/bijux-nav.html` | Shared template macros normalize paths and derive labels from authored navigation. | Navigation projection fixtures and generated deep-document journeys |
| `partials/source.html` | Shared privacy gate wraps Material's repository navigation; product owns repository identity and explicit facts choice. | `generated/test_repository_facts.py`, repository browser gate |
| `partials/logo.html` | Shared brand renderer consumes baseline-owned asset; product supplies site name. | Branding and generated phone shell journeys |
| `partials/footer.html`, `partials/footer-profile-links.html` | Shared footer renders MkDocs previous/next destinations and shared profile links. | Rendered template fixtures and full artifact link validation; visual/assistive review remains separate |
| `partials/javascripts/base.html`, `partials/javascripts/palette.html` | Shared bounded-storage compatibility for admitted Material helpers and early palette application. | Palette unit tests and preferences browser gate |
| `theme-persistence.js` | Shared palette persistence consumes authored native palette options; Material retains visual theme semantics. | Palette units and preferences browser gate |
| `viewport-profile.js` | Shared window profile classifier emits read-only observations. | Viewport source tests and generated responsive-boundary journeys |
| `nav-state.js`, `detail-tabs.js` | Shared active-path and header-detail state consumes server-rendered destinations. | Navigation projection and deep-page/history journeys |
| `nav-reveal.js` | Shared container scroll reveal consumes the active navigation state. | Generated resize/navigation journeys; compatibility aliases retained |
| `content-reflow.js` | Shared progressive annotation of measured code/table overflow; authored source, line anchors, cells, labels and controls remain owned by their authors. | `unit/content-reflow.test.cjs`; `ui/generated-specs/reader-reflow.spec.js` via `ui-test-reader` |
| `external-links.js` | Shared progressive warnings and explicit `_blank` opener isolation; products own href, target, download and referrer intent. The coordinator owns mount/disposal. | `ui/generated-specs/external-links.spec.js` via `ui-test-link-policy`; `tests/test_docs_external_link_projection.py` |
| `bootstrap.js` | Shared document-lifetime coordinator owns control upgrade, compact drawer/search interaction, binding and disposal. | Search focus/input units; generated shell/drawer/search journeys |
| `search-recovery.js`, `tooling/material/search-*-adapter.js` | Shared failure UI and admitted index/worker transport; Material worker retains tokenization, ranking, options, and result protocol. | Index/worker/recovery units; search outage/retry/latest-query browser gate |
| `mermaid-init.js` | Shared sole renderer; lazy admitted vendor renders strictly from preserved authored source. Material must not intercept source fences. | Renderer/dependency units and diagrams browser gate |
| `nav-sync.js` | Shared compatibility entrypoint delegates to the coordinator; it is not another navigation owner. | Generated baseline asset admission and shell journeys |
| `00-tokens.css`, `01-theme.css` | Shared design tokens and palette variables. | Preferences and rendered contrast probes; manual visual review |
| `02-layout.css`, `03-header.css`, `04-nav.css` | Shared page, header, and complete navigation presentation. | Responsive shell/header/drawer journeys |
| `05-content.css`, `06-components.css` | Shared native document and component presentation; product content remains authored. | Rich-content/reflow fixtures and rendered content probes |
| `07-utilities.css`, `08-responsive.css` | Shared hidden/focus semantics and breakpoint overrides. | Hidden-strip, keyboard, resize, and occluded-target journeys |
| `styles/extra.css` | Shared ordered CSS import manifest; no independent component rules. | Artifact CSS import validation and style source contracts |
| `config/`, `tooling/configuration/`, projection and quality tooling | Shared registry, baseline, source admission, owned asset ordering, generated ownership and validation. | Configuration, source projection, compiler, and schema tests |

Test paths in this table are relative to `tests/bijux-docs/` unless prefixed by
`tests/` in the executable trace. `config/shell-contract-trace.json` lists exact
source and executable test references for public behavior and boundary guards.
It records applicability, not a universal pass or full accessibility claim.

The shared external-link producer supplies the required
`assets/javascripts/external-links.js` asset. It is projected at that exact path
and executes before the coordinator. Native `href`, `target`, `download`,
`referrerpolicy` and relationship intent remain authored inputs; offsite origin
alone does not select a new window. Explicit `_blank` adds `noopener`, retaining
other relationship/privacy tokens and removing contradictory `opener`.

The projector does not claim existing authored external-link files as legacy
managed content. Each consumer must review its current file and authored link
intent, then explicitly migrate that authored boundary in the same coherent
candidate that adopts the generated producer. There is no force-adoption alias
or silent ownership rewrite. Authored target/content decisions are separate
from generated synchronization where separable. An existing consumer's blanket
new-tab script must not execute alongside this producer.

Native anchors keep modified clicks, browser menus and Back/Forward. The shared
script has no click listener, window-opening call, router or history owner. Its
private document annotations and observer are disposed by the existing signal.
Plain actions have warning text; icon actions have visible/accessible indication.
Consumers retain authored source warnings/security for no-script use, and review
named-window/opener integrations rather than imposing `_blank` on them.
Cross-origin download delivery remains dependent on browser/server policy;
authored filename preservation is not proof of that external capability.

## Lifetimes and compatibility

The coordinator creates an `AbortController` per document mount and aborts the
previous lifetime before rebinding. Compact drawer modality owns temporary
background inertness, focus containment, Escape/restoration, and close-on-resize;
dispose restores previous values. Desktop navigation uses ordinary destination
anchors. Material instant navigation and ordinary full loads both remain valid.
Bindings apply to their declared component owner. The shared drawer applies
to the Bijux header and navigation markup; it does not require an unrelated
Material-native header to expose Bijux readiness attributes or replace its
native control. Owned enhancement readiness is a private mount result, not
Material's window-level JavaScript class. Failed or aborted enhancement must
restore temporary state so the native authored fallback remains operable.
Native search fields and result destinations retain Material semantics even
when an owned recovery bridge is present. Global character-only `/`, `f` and `s`
search shortcuts are disabled in both headers. Readers open search through its
named button or native inline field; focused query input, native Arrow/Enter
result navigation, Escape restoration and browser modifier defaults remain available.

Global profile/storage listeners bind once per window. Index and worker owners
retain their bounded window transport; pagehide cancels owned work and bfcache
restoration reestablishes the appropriate binding. No generic global error
suppression or global network API replacement belongs to this shell.

Authored anchors and the complete native disclosure tree are rendered without
JavaScript. Enhanced controls must retain a usable fallback when enhancement is
unavailable. This architecture statement does not certify every no-script
keyboard interaction; the generated fallback gate and browser-specific input
protocol remain acceptance requirements.

Compatibility names `runPhoneNavigationSync`, `bindMobileDrawerReveal`,
`nav-sync.js`, the `validate_shell_contract.py` wrapper, and course-strip selectors
remain until exact consumer source/configuration analysis proves retirement is
safe. They do not justify adding a second scoped navigation tree. New public
hooks are additive only after typed fixtures and compatibility review; changing
or removing a hook requires producer and consumer qualification against the
same accepted source reference.

## Architecture decision: retain MkDocs and Material

The admitted architecture keeps server-rendered Markdown and native links,
Material content/search features, and bounded progressive enhancement. This
serves existing Python and Rust documentation producers without introducing a
second route, content, or search framework. Reimplementing the site as an app
framework would add a parallel owner for these working capabilities; it requires
an explicit decision with measured user benefit and a migration/rollback plan.

The compatibility cost is deliberate: Material 9.7.7 distribution, base template,
source map, and worker are admitted by exact digests; owned transformations fail
on drift. The index and worker adapters own transport/lifecycle, while the native
worker algorithm remains unchanged. Mermaid source fences use the custom class
`bijux-diagram` and the baseline-owned lazy vendor; eager legacy vendor loading
or `pre.mermaid` source fences would create competing renderers and are rejected.
Theme storage uses the fixed cross-project key and admitted native palette index.

Unsupported combinations include an unadmitted Material bundle, a replaced
shared scripts block, duplicated shared navigation runtime, asynchronous owned
dependency scripts, and treating a clean authored root template as generated
without explicit adoption. Consumer-specific plugin configuration and authored
head/component assets are retained through their named extension points.

Adopt upstream schema/template/runtime changes as a coherent accepted source
unit, then refresh managed shared files and projected destinations. An authored
root template first extracts its head additions to `partials/site-head.html`
while its old root template includes that partial, preserving the rendered head.
Replacing the root with the shared template requires explicit reviewed adoption
and all admitted assets/configuration together; the projector never silently
claims authored ownership. Roll back using the previous complete accepted
source, ownership record, configuration, and asset set. Preserve the authored
head/content and verify the resulting native capabilities; do not mix a new
template with a retired runtime asset.

Projection provenance, protected destinations, exact-source verification, and
implementation exclusions are specified in [consumer projection](README.md).
The shared asset inventory and versions are authoritative in the baseline and
compiler provenance, rather than repeated vendor URLs in this document.


## Reader history and optional scroll tracking

The shared baseline preserves native authored fragment destinations and browser
Back/Forward. It retains Material instant navigation, active table-of-contents
indication and `toc.follow`. It does not enable `navigation.tracking` by default:
that feature replaces the current URL fragment from scroll position and can
restore a fragment after browser Back while the document is still settling.

A product may explicitly add `navigation.tracking` to its authored feature list.
The projector preserves authored feature additions; synchronization does not
silently strip this opt-in. Such a product owns compatibility qualification for
ordinary fragment Back/Forward, instant reader return, and URL stability during
scroll restoration in every admitted browser. Automatic tracking must not be
presented as qualified by the shared default history receipt. When reviewing an
existing consumer override, distinguish an intentional opt-in from a feature
copied from the previous standard before changing that authored list.

When an inherited `mkdocs.shared.yml` still contains a previous standard's
`navigation.tracking`, changing the accepted standard pin alone does not remove
that feature: the projector preserves configured theme feature lists. Select the
product's reader policy explicitly in its authored `mkdocs.yml`. A root
`theme.features` list replaces the inherited list under MkDocs configuration
inheritance; it does not append to it. To select stable native reader URLs, list
all current `theme.required_features` from `mkdocs-baseline.json` without
`navigation.tracking`, retaining any other deliberately authored optional
features. Keep `theme.custom_dir` and other product theme settings intact. Review
the resulting effective feature list after every accepted standard change, and
run the shared contract validator to catch missing required features.

This is an authored configuration choice, not a managed-file exception. Do not
infer feature ownership from a matching old default or silently strip a
product's deliberate tracking opt-in. Qualification must check the exact URL at
the trusted link activation, then browser Back/Forward and its settling window;
retained visible reading context alone cannot certify URL preservation. See
[MkDocs configuration inheritance](https://www.mkdocs.org/user-guide/configuration/#configuration-inheritance)
and [Material anchor tracking](https://squidfunk.github.io/mkdocs-material/setup/setting-up-navigation/#anchor-tracking)
for the supported configuration semantics.
