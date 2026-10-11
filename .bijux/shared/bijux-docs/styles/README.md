# Bijux shell CSS ownership

| Source | Presentation boundary |
| --- | --- |
| `00-tokens.css` | Global `--bijux-*` tokens and defaults. |
| `01-theme.css` | Palette variables and scheme-bound overrides. |
| `02-layout.css` | Page/shell layout and baseline typography. |
| `03-header.css` | Header controls, brand, and hub strip. |
| `04-nav.css` | Site/detail tabs and complete sidebar navigation. |
| `05-content.css` | Native prose, headings, tables, code, and blockquotes. |
| `06-components.css` | Shared hero, panel, card, callout, and media presentation. |
| `07-utilities.css` | Semantic hidden behavior, visible focus, and helper utilities. |
| `08-responsive.css` | Breakpoint overrides for those shared domains. |
| `extra.css` | Ordered import manifest only; no competing component rules. |

Palette rules precede component rules; responsive overrides remain in the final
domain. Semantic `hidden` is behavior, not a decorative class: a responsive
display rule must not paint or expose an inactive control. Focus, inertness,
disclosure and accessible names are coordinated with templates/runtime rather
than inferred from viewport geometry alone.

Products extend authored content through their own component classes and authored
`extra_css` entries, preserving required shared imports and cascade order. They
may consume token defaults listed in `00-tokens.css`. These unregistered CSS
strings are validated by the consuming property's grammar, not by a typed
custom-property registry. Shared `.bijux-*`, Material `.md-*`, and private control selectors
are integration details, not promised override APIs. Replacing shared navigation
CSS or copying runtime controllers creates a competing owner and needs an
explicit shared design decision.

The [shell contract](../CONTRACT.md) maps these domains to producers, consumers,
fixtures and compatibility expectations. Source inspection does not establish
contrast, keyboard reachability, physical touch usability or assistive support;
those require the applicable rendered and manual checks.
