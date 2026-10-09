# Static documentation delivery and recovery

Operate complete reader journeys, with a reproducible local candidate and honest
provider/manual boundaries. Std owns common shell/parser/dependency/build controls;
consumers own content, routes and exact output. Actual repository/domain administrators
own Pages, environment protections, DNS and certificate access. Identify real primary
and backup maintainers before scheduling unattended alerts; no 24/7 response is assumed.

## Local qualification and observation

Build with the actual production identity/basepath, run the consumer verifier, then
admit and reverify the same bytes with [publication.py](publication.py). Keep source,
exact standard/config/toolchain, per-file manifest, public digest and recovery material
under `artifacts/website-security/`. Never choose an incidental preview directory,
rebuild after qualification or mark an uploaded artifact as verified live without
observing the intended public identity and journeys.

A framework-enabled caller must capture clean source and the fetched tracked
standard pin before building. Automatic framework activation is pending actual
hosted profile/caller qualification. The actual renderer records `build-identity.json` around build/CSP,
then the mechanical verifier writes `site-verification.json`; `csp.json` records
admitted executable policy inputs. Final admission requires all four receipts to
identify the same bytes and rejects candidate-only verification. A setup action's
configured Python version is not evidence of the interpreter that built the site.
The build job retains its 30-minute budget; deploy has a separate 10-minute budget.

The repository's read-only delivery observations must cover root/deep identity,
actual search corpus, a known query, a declared critical asset and true missing
route behavior. Retain scoped response classifications, elapsed time and counts;
do not retain search text, query strings, response bodies or visitor storage.
HTTP observation complements ordinary-input browser qualification and cannot
certify the rendered menu, every route, global uptime or visitor Web Vitals.
The HTTP component below supplies local observation. Scheduled integration and
actual consumer live qualification require their own current evidence; the
publication admission library does not supply those operating receipts.

### Bounded HTTP observation

Run `security/monitor.py` from the actual repository root with its real production
canonical root, a declared deep route, critical asset and known public search term:

```sh
python3 .bijux/shared/bijux-docs/security/monitor.py \
  --root "http://127.0.0.1:$fixture_port/bijux-core/" \
  --canonical-root https://bijux.io/bijux-core/ \
  --deep-path guide/ --asset-path assets/stylesheets/actual-critical-asset.css \
  --query "$known_public_term" --timeout 10 \
  --output artifacts/website-observation/http.json
```

Replace those declared routes/assets with actual site paths. Std uses
`shared/bijux-docs/security/monitor.py`; consumer copies remain managed. Public
observation requires `--live` and the identical HTTPS `bijux.io` product root.
The result covers document title/canonical/link presence, typed search data, a
fetched known result and its anchor, a nonempty/non-HTML asset and truthful 404.
It records actual module/URL-validator digests and owned local Git identity where
available, without claiming that this checkout identifies an accepted deployment.

Optional `--manifest artifacts/website-security/site.manifest.json` first verifies
the retained publication artifact, then compares each successful sampled response
with its declared file digest. Schema 1 retains mechanical HTML/CSP admission;
schema 2 performs only a physical inventory/policy/budget comparison without
opening source receipts or reconstructing the producer. Independently trust the
selected historical manifest. Both modes report no publication or source authority;
sampled expected bytes do not observe every deployed file or requalify source.
Missing, changed or wrong-identity retained artifacts fail before observation.

Requests connect directly, without inherited proxy settings, cookies or browser
storage. Redirects stay inside the declared product and consume the same payload
budget, including intermediate bodies. The report declares at most four HTTP
requests per selected target and an 8 MiB payload ceiling per redirect chain.
Each transport phase/read uses the remaining deadline; underlying OS DNS/TLS/connect
interruption is not an absolute wall-clock guarantee. Identity content encoding is
requested; an unexpected encoding fails without unlimited decompression. Header
values are retained as presence/digests, not raw policy text. Bodies, title/search
text and the input term are not retained. Keep reports under the repository's
`artifacts/` and apply the selected retention policy.

This HTTP component cannot detect CSS-hidden menus, qualify ordinary keyboard
input or certify all-user availability. Pair it with the existing actual browser
journeys. Consumer owner/cadence/region configuration, approved scheduling,
deduplication/notification and live deployment identity remain separately pending;
no facility is created or activated by this command.

## Capability and privacy decisions

Inventory actual headers/compression/cache/redirect/purge/log/TLS controls. Sampled
Pages behavior must be interpreted as provider evidence, not a guarantee of arbitrary
control. Early HTML CSP has limitations; response HSTS/nosniff/framing require supported
serving configuration. Missing sampled headers are gaps, not discovered compromise.
Keep bounded residual-risk decisions and owner/retest condition; do not silently claim
an ignored `_headers` file or nonexistent purge API works.

Record every actual storage/network recipient's purpose, data, trigger, retention and
owner. Existing theme preference is benign local state, and browser search need not
send terms externally. Redact tokens/queries/search text from diagnostics. New analytics,
error trackers or alert integrations need a real approved facility, minimal data and
responsible operator. No automatic consent banner or generic legal compliance claim
follows from this technical inventory.

## Proposed measurement and response

Start with a 14-day baseline, then owner-review proposed rolling 28-day objectives:
99.9% successful document-availability samples and 99% navigation/search samples.
State numerator, denominator, missing samples, region/device coverage and retries;
synthetic sampling is not all-user availability. Field p75 performance has its own
valid population and data-quality/privacy decision.

Proposed cadence is HTTP critical routes every 15 minutes, rotating browser journeys
hourly/full consumer coverage daily, and DNS/certificate checks daily. Two fresh
independent consecutive failures trigger a deduplicated owned incident when an actual
approved notification facility exists. Certificate expiry warnings at 21/7 days and
artifact/deploy growth warnings at 70% of verified limits are reviewable defaults.
`policy.json` sets local admission ceilings; actual host limits and workload sizes
require current evidence. No live stress test or new infrastructure is assumed.

## Retained identity and restore rehearsal

1. Retain a qualified previous-good source/std/config/toolchain plus public manifest
   and artifact. Verify actual retention/access; propose 30 days for ordinary diagnostic
   evidence and 90 days for recovery evidence, subject to provider/account limits.
2. Rebuild or copy the previous-good artifact into the declared output location.
   `publication.py verify --bytes-only --manifest ...` must identify identical intended
   physical bytes and policy against an independently trusted historical manifest. Missing/expired artifacts require a tested source rebuild, not a guessed SHA.
   This offline check grants no source, runtime, CSP or publication authority. Republishing through
   `--require-qualified` needs the retained source/config/actual toolchain and receipts
   or a fresh qualified rebuild; do not replace their digests with guessed current data.
3. Run root/deep/phone navigation/search/canonical/diagram checks on the restored
   candidate. Test old HTML with new assets and new HTML with old cached assets using
   the actual stable/hashed path strategy; Pages replacement is not atomic across sites.
4. Measure preparation/restore/verification separately. A proposed 60-minute restore
   target starts at authorized recovery and becomes a commitment only after an actual
   drill/capability/coverage review. Recovery loss target is one qualified publication.
5. Publish/rollback only through already authorized supported operations, then observe
   actual identity and reader journeys. Expect provider caches and verify convergence;
   do not assume immediate purge or mutate DNS blindly during a host outage.
6. Preserve the failed release and redacted evidence. Record symptom, owner, cause,
   containment/restoration, elapsed timings, corrective regression and revisit condition.

Local adversarial tests prove rejected private/incorrect bundles, changed-byte admission,
stale-output rejection and an exact previous-byte restore. They do not certify actual
Pages deployment permission, remote artifact retention, timed provider recovery,
physical-device/manual review or live rollout. Exercise broken-shell and publication/
security incidents locally/tabletop before making operational claims.
