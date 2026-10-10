## Release Change Checklist

Use this template for release workflow, package publication, or artifact pipeline updates.

## Summary
- What release surface changed and why.

## Release Surface
- [ ] `release.env` keys added/changed are documented.
- [ ] Workflow templates and active workflows stay aligned.
- [ ] Allowed package/crate lists are explicitly scoped.

## Validation
- [ ] Workflow YAML parsed successfully.
- [ ] Hash parity against canonical `bijux-std` templates is verified.
- [ ] A dry-run or equivalent validation evidence is attached.

## Risk
- [ ] Duplicate publication risk checked.
- [ ] On/off gates and fallback behavior verified.

## Changelog

- [ ] Record this PR’s meaningful changes directly in `CHANGELOG.md`, with its actual PR link and a concise summary.
- [ ] Keep the newest PR first and distinguish pending review from verified merge history.
