# Required configuration lists

`ordered_assets.py` owns the narrow projection of common CSS, scripts, and
plugin names from `config/mkdocs-baseline.json`. Product navigation, metadata,
hooks, extension options, plugin options, and custom assets remain authored.
The updater's verified source and pristine-destination checks still apply.

## Execution and cascade order

Required entries occur once in baseline order. Missing entries are inserted
before the next existing required peer, or directly after the preceding peer.
When no required peer exists, the common entries precede authored additions.
This provides the normal shared-CSS-before-author-CSS cascade. Existing authored
entries retain their bytes and relative order; the tool never sorts them.

A conflicting shared script order can be adopted only when the entire plain
`extra_javascript` block matches the baseline at the consumer’s committed
`.github/standards/bijux-std.sha`. The current source must be a clean checkout
of the exact official GitHub reference, and the copied current baseline must
match its Git blob. The projector retrieves the previous baseline from that
official origin only when an execution-order conflict actually needs it. The
explicit predecessors `44e9153959f98bfc27444d6b740144146ed17a77` and
`10f073dba1d3a9617c8847d72d2bf62bdf7e996d` predate that file and instead use `config/legacy-mkdocs-baselines.json` from the accepted
current tree. This reviewed migration binds every recorded predecessor source
digest. It separately declares the historical plain-list order, including the
authored external-link predecessor; it does not claim the old contract specified
that complete ordering. Other missing baselines fail closed. The projector
accepts no predecessor override or untracked ownership receipt.

This narrow recognition changes only the exact old default block. Custom
entries, reordered entries, comments, quoted entries, script mappings, and
attribute-bearing mappings continue requiring explicit author review. Root
configuration overrides do not use this recognition. Local verification cannot
claim accepted-source ownership. Both configuration plans still complete before
any destination write.

Other conflicting required order or attribute-bearing required script mappings
need an explicit reviewed migration. The tool does not silently strip `async`,
`defer`, `type`, or other authored script attributes. Authored module scripts
and plugin options retain their original representations.

## Supported configuration boundary

Both `mkdocs.shared.yml` and `mkdocs.yml` are planned before either is written.
The root must inherit `mkdocs.shared.yml`. Shared required lists are materialized;
root lists are merged only when an explicit overriding list exists. An absent
root list continues to inherit the shared list.

The admitted representation is an ordinary YAML block sequence, including
indentless sequences, quoted strings, and block mappings. A script mapping
starts with `path`; a plugin mapping starts with its name. An empty `[]` is
accepted. Scalar, nonempty flow, alias, tagged list, duplicate, top-level merge,
and explicit-key representations fail with a path and review instruction.
These forms are not rewritten speculatively. Tags nested inside preserved
author plugin settings, including `!ENV`, remain byte-for-byte unchanged.

Only exact paths in `retired_extra_javascript` are removed from the script
list. This does not claim physical ownership of a historical asset or delete
its file. A different vendor version is never matched by a wildcard retirement.
New required scripts appear only when the actual accepted baseline requires
them; the projection does not acquire undeclared optional features.

## Validation

`sync_mkdocs_hub.py REPOSITORY SHARED_ROOT --check` is read-only and rejects
configuration drift. Source-of-truth verification invokes this check after
the existing source authority and generated-file checks. Effective asset
validation requires each owned asset once, in order, and rejects retired paths.
Existing effective plugin and Markdown extension checks remain in place.

The implementation uses Python's standard library. The normal contract test
discovery includes `tests/test_docs_config_projection.py`; no extra YAML package
is required for synchronization. MkDocs remains the authority for actual
configuration resolution and final builds. Native worker/result journeys and
full artifact validation are required for each applicable adopted consumer;
source-list projection alone does not prove delivery or browser behavior.

## Shared branding references

`branding.py` migrates only literal `theme.logo` references named exactly in
`retired_theme_logos` to the baseline's current logo. It preserves scalar quote
style, comments, line endings, authored custom logos, icon settings, and other
theme options. Missing theme/logo fields remain absent and continue inheriting.
Dynamic custom logo values remain authored. Duplicate relevant keys, merge
keys, and ambiguous theme representations require review before any writes.

Retirement changes the configuration reference only. The historical HQ PNG
remains a physical compatibility asset; the compact common PNG is supplied by
the separately governed shared asset projection. Supported root configuration
identity and inherited publication exclusion rules remain unchanged.

## Interactive report ownership

An authored product may declare `extra.bijux.interactive_report_owner` as a
canonical relative JSON source path, bounded to 1024 characters. It selects no
behavior by itself: the canonical renderer requires the same explicit
`--interactive-report-owner`. Shared configuration cannot supply this product
authority. Passive and interactive renderer modes remain separate. The field is
preserved by configuration projection and validated by `shell_contract.py`;
MkDocs resolves the actual configuration before the independent producer derives
the source-owned selection. See the [security contract](../../security/SECURITY.md)
for the finite descriptor, provider decisions and publication profile boundary.
