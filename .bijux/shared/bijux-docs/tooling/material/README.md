# Admitted Material runtime boundaries

Runtime emission requires the admitted Node.js 24.21.0 classic-script parser.
The complete generated script is syntax checked after all owned transformations
and before any output or provenance is written. Parsing does not execute the
script or approve runtime behavior. Exact verification of already qualified
shared output uses source-derived byte comparison and does not introduce a Node
requirement into consumers' Python-only admission check.

Material 9.7.7 subscribes to its search index from both worker setup and document
highlighting. Its synchronous search-component catch does not handle asynchronous
index errors. This boundary preserves the admitted native worker, ranking,
results, keyboard observables and highlighting while owning index availability
and retry before either subscriber. Its native worker transport also lacks an
error listener, setup deadline and restart lifecycle. A separate owned worker
transport supplies those contracts around the unchanged native protocol.

`search-index-adapter.js` is the maintained, readable controller. It creates an
Observable through the native bundle's own constructor and sharing operator.
It owns only the index XHR: actual search intent starts same-origin HTTP transport,
direct cancellation, a nonrenewable 45-second total bound, an independent
eight-second no-byte-progress bound, response admission and current-attempt checks. Material's
original index request is never subscribed because its `shareReplay(1)` retains
the underlying transport after downstream unsubscribe.

The shared outer Observable stays alive after index failure. Both native
subscribers receive the same admitted data after ordinary retry. The error path
announces availability without emitting fabricated empty data or terminating
native consumers. The worker subscriber retains the shared stream across
ordinary document mounts; behavioral browser tests require ten document/history
journeys to share one request. Final subscriber disposal and pagehide cancel
incomplete transport; persisted pageshow resumes an interrupted intended attempt.
Ordinary reading without search intent starts no index download. Native `?q` and
nonempty `?h` links establish intent; the latter needs the admitted index for
Material highlighting. Document mounts/history changes report location intent
without renewing an active operation. Cancellation
requires explicit Retry; healthy admitted data is reused without another request.

## Interface

`window.bijuxSearchIndex.state` is an immutable snapshot. Stages are `index-idle`,
`index-loading`, `index-unavailable`, and `index-ready`; it includes the current
attempt and a bounded failure reason when applicable. State changes dispatch
`bijux:search-index-status` with the snapshot in `event.detail`. An ordinary
`bijux:search-index-retry` event begins a fresh attempt. The DOM recovery bridge
owns announcement, preserved query, Cancel/Retry buttons and focus. An ordinary
`bijux:search-index-cancel` event aborts the active transfer. Progress resets only
the independent stalled-transfer bound; no input/progress can renew total age. `index-ready` means
fetched and admitted data, not native worker readiness.

`search-worker-adapter.js` receives the native Subject constructor at the exact
worker-transport boundary. It forwards admitted native SETUP, QUERY, READY and
RESULT messages without changing corpus data, worker options or ranking. It owns
one same-origin worker per document, direct termination, generation checks and
eight-second actual setup/query operation deadlines. Initialization errors,
message-deserialization errors and silent transports become typed availability
failures. Only this worker's error event is handled; global errors are untouched.

`window.bijuxSearchWorker.state` exposes `worker-idle`, `worker-loading`,
`worker-unavailable`, `worker-searching`, and `worker-ready`, with attempt, operation phase and a
bounded failure reason. Changes dispatch `bijux:search-worker-status`;
`bijux:search-worker-retry` replaces a failed worker using the cached native SETUP
and latest QUERY. Only an actual native READY permits query replay and result
restoration. Index readiness cannot hide a worker failure. The DOM recovery
bridge combines both states, hides stale results during failure, preserves the
visible query, and activates every failed dependency with one ordinary Retry.
A healthy corpus is reused rather than fetched again for worker recovery.

Queued or in-flight queries announce `worker-searching` with query phase.
Native READY still reaches native observers, but a recovered worker with a
cached query remains searching until the real latest RESULT reaches native
rendering. Only then does it announce `worker-ready`, provided reentrant
subscribers did not enqueue newer work or retire that generation. This lets the
DOM bridge exclude previously rendered results while showing a truthful
search-in-progress status, without fabricating an empty corpus or results.

Native QUERY messages settle for 150 milliseconds after the latest edit. At most
one native query is in flight and one replaceable latest query is pending.
An obsolete in-flight RESULT is discarded before native subscribers when newer
input is pending; the latest settled query starts immediately after completion.
Native query text, worker options and ranking are unchanged, including empty
queries. The independent settle timer never renews an actual operation's
eight-second deadline. Timeout retires the worker and Retry replays only the
latest query against the cached native setup. Slow settled native algorithms
can still hit that deadline; coalescing is not proof of a bounded native query
algorithm. Both timers are canceled on suspension, failure and disposal.

Ordinary document mounts reuse the same worker. Persisted pagehide terminates
the transport and pageshow reconstructs it from the cached native messages;
final pagehide or explicit disposal removes owned listeners and timers,
terminates the worker and completes the Subject.

Current candidate limits are 50,000 records, 40Mi UTF-16 response/source
characters and 80MiB transport-progress bytes. Response length is checked before
JSON parsing even when progress information is absent. These are explicit
candidate bounds, not evidence that the largest consumer corpus or slow mobile
CPU is qualified. The worker's eight-second limits likewise require measurement
against the largest actual corpus and admitted slow-device budget. File-protocol search
falls outside the admitted HTTP website and reports unavailable scope.

## Reproduction and admission

```bash
artifacts/bijux-docs/python/bin/python shared/bijux-docs/tooling/material/build_runtime.py
artifacts/bijux-docs/python/bin/python shared/bijux-docs/tooling/material/build_runtime.py --check
```

`admission.json` pins the installed version and exact upstream bundle, native
worker, base layout, source map and license hashes. The compiler accepts exactly
one index-observable boundary, one worker-transport boundary and each declared
native integration boundary, adding their readable owned controllers. It emits a content-addressed
asset, truthful provenance and the root
`main.html` scripts override. The override inherits layout/configuration and
includes configured extra JavaScript exactly once. Projection must place it at
`docs/overrides/main.html`.

This controlled distribution transformation avoids reconstructing Material's
entire build/dependency graph. The corresponding source-level boundary is
`const index$ = document.forms.namedItem("search") ? fetchSearchIndex() : NEVER`
in admitted `bundle.ts`; the worker boundary is `watchWorker(url)` in
`setupSearchWorker`. The original native worker asset remains byte-identical.
Upstream drift, ambiguous context or changed inputs
fail before output. A supported upstream fix should replace this compatibility
boundary after the same generated qualification.

The original map applies to original upstream offsets. The modified asset does
not advertise that map. Provenance records its admitted upstream map digest and
owned controller digest. The upstream MIT license and distributed third-party
notices are retained. Previous private runtime assets are preserved and rejected;
retire a verified generated asset explicitly during reviewed regeneration.

The release gate includes actual RxJS controller tests, exact-distribution
mutation checks, and generated three-engine ordinary-input search/retry cases.
The worker corpus includes missing transport, initialization exception, silent
setup, combined index/worker outage and failure after native readiness. Keyboard
Retry must return actual native known-answer results with the query preserved.
No global fetch/XHR proxy, broad error suppression, second ranking engine or
complete Material restart is used.

## Native fragment restoration

`fragment-restoration.js` restores only the fragment of the current history entry.
It replaces the uniquely admitted native hash helper through the canonical compiler.
Scrolling an already-current fragment must not queue another anchor navigation,
which could finish after Back and resurrect the fragment the reader just left.

Restoration resolves decoded IDs and legacy named anchors, reveals until-found
ancestors through `beforematch`, opens ancestor disclosures and preserves native
content-tab selection. The target owns sequential focus: a nonfocusable target
receives a negative tabindex while focused, and blur restores that owned attribute
without erasing a later authored value. Provenance binds this source and its exact
native boundary; the complete generated classic script is parsed before emission.

## Native viewport history

`viewport-history.js` owns the admitted instant-navigation viewport subscription's
native lifecycle. Its native 100ms debounce remains unchanged while the document
is active. Cross-document native departure and trusted pagehide unsubscribe the
pending work, preventing a delayed `replaceState` from committing after the realm
has entered the browser cache. Trusted persisted pageshow creates a fresh native
subscription; canceled or aborted departures resume only their own generation.
An older navigation cancellation cannot reactivate a newer or cached departure.

Same-document instant and fragment navigation keep their native subscription.
The current viewport x/y update preserves other object history state keys, including
authored reader entry context. Foreign non-object state remains untouched. Engines
without the Navigation API cancel explicit native same-window links and pagehide
without intercepting navigation or replacing the History API. The canonical compiler
admits exactly one upstream viewport writer and binds the owned source in provenance.

## Consumer-owned head additions

The generated root `main.html` inherits Material's admitted `base.html`. Its `scripts`
block replaces only the admitted runtime and retains native `script_tag` rendering
for every `config.extra_javascript` entry. Its `extrahead` block calls `super()` and
optionally includes `partials/site-head.html`. The optional include has no shared
managed default. A consumer may own `docs/overrides/partials/site-head.html` for
existing favicon, touch-icon or other authored head markup, with the normal `url`
filter retaining deep-page and product-base resolution.

An absent or empty include adds no content. Invalid consumer template syntax must
fail the real build; `ignore missing` handles absence rather than swallowing errors.
The compiler generates and verifies the root template and records the extension's
consumer ownership. Introducing an optional include does not authorize replacing
an existing authored root template: projection preflight still protects it even
when its current bytes happen to equal the canonical root.

First extract existing head additions into the consumer-owned include and make the
existing authored root include it, keeping `super()`. Verify that complete rendered
head/body content remains the same while native scripts remain in place. After the
shared runtime/template is accepted, review an explicit root-template ownership
adoption using that exact source. Preserve the authored include and compare the
composed production render. Root replacement, verified projection ownership and
its required generated dependencies must form one coherent adoption change when
separating them would lose head assets or leave source verification failing.

Do not commit a root deletion alone, invent a broad overwrite option, classify
unknown templates as legacy generated files, or edit a source record to claim
arbitrary authored bytes. Normal source projection and its pending/staged/untracked
protections remain unchanged. Review-worktree checksum/authority/browser gates
still apply to the final adopted source.

The native header receives the same input/composition/reset bridge even when
custom controls are absent. While recovery is visible, scoped Tab traversal
reaches Cancel/Retry instead of triggering native search dismissal; healthy
native search keeps its ordinary focused keyboard behavior. The exact admitted
global character-only `/`, `f` and `s` subscription is removed by a unique
source boundary; the owned header does not recreate those global actions.
Characters remain literal text in a focused query or authored editable field.
Named Search controls retain ordinary Tab/Space activation, and native query
and result keyboard subscriptions, Escape and browser modifier defaults are
unchanged. Missing or duplicate upstream shortcut boundaries fail before output.
