# Bijux Shared Standards

This directory owns shared-directory synchronization, checksum validation, and
standards check execution.

The canonical managed workflow is `.github/workflows/bijux-std.yml`.
`scripts/validate-shared-contracts.sh` validates synchronized shell, Python, and
JSON assets in both this repository and downstream consumer layouts.

## Capability Selection

Repositories may select managed shared libraries with
`BIJUX_STD_CAPABILITIES`. The `common` capability is always included.

```bash
BIJUX_STD_CAPABILITIES="docs rust" make bijux-std-update
BIJUX_STD_CAPABILITIES="docs rust" make bijux-std-checks
```

Available capabilities are declared in `bijux-std-checks.yml`:

- `common`: shared checks, GitHub governance, and language-neutral Make modules.
- `docs`: shared documentation shell and assets.
- `python`: Python Make modules.
- `rust`: Rust Make modules.

When capabilities are explicitly selected, the updater removes unselected
managed directories and writes a manifest containing only selected directories.
Without `BIJUX_STD_CAPABILITIES`, synchronization retains the complete shared
set for existing consumers.

An additive refresh can preserve installed, independently accepted components while
advancing common governance. Set `BIJUX_STD_UPDATE_PRESERVE_UNSELECTED=1` together
with an explicit capability selection, and run the updater from the exact accepted
source checkout. For example, select `BIJUX_STD_CAPABILITIES=common` to retain the
documentation, Python and Rust components. This mode preserves their manifest rows
and refuses modified, untracked, aliased or unaccepted inputs. Unselected runtime
components must also match the new source; otherwise select their capability.
The default replacement behaviour above remains unchanged.

The governance writer exposes `write_std_pin(..., preserve_docs=True)` to retain
the tracked `.github/standards/bijux-docs.sha` while advancing the standard pin.
Use it only after qualifying the selected shared components and canonical workflow
projection. Full consumer checks verify retained documentation against its own
exact accepted source and other components against the standard source. Refresh
and validate both checksum manifests before committing the composed result.
A preserved source is not permission to reuse an artifact from a different commit.

Consumers with installed documentation use
`scripts/verify-documentation-components.sh` for their source-of-truth check.
`BIJUX_STD_ROOT` and `BIJUX_STD_REF` continue to select the declared documentation
source; the separate standard pin selects common governance. The check covers
the actual installed capability profile, both accepted sources, the retained
documentation projection and optional `DOCS_SITE_DIR` verification. Unknown
retained source-of-truth contracts are refused. Repositories without installed
documentation continue to use their applicable shared standards checks.

Masterclass uses its canonical `promote_masterclass(..., keep_documentation=True)`
composition instead of the common updater. It preserves its accepted programme
baseline and independently admitted documentation while advancing governance.

## Source Pinning

`BIJUX_STD_REF` accepts an exact commit SHA, branch, or tag. Downstream
repositories should use an accepted exact commit SHA. The updater fetches and
checks out that object in detached mode before copying managed content.

## Artifact Placement

Checkout, staging, rendered validation input, and Python cache output belong
under the consumer repository's `artifacts/` directory.
