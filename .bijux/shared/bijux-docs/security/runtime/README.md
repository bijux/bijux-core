# Documentation publication runtimes

Publication uses an isolated documentation environment rather than a consumer's
application, scientific or developer environment. Normal local builds retain their
owned toolchains. The publication installer selects a finite source-owned recipe,
installs exact hashed wheels without pip or ambient packages, checks dependency
closure and requires the actual renderer to match `renderer-producer-admission.json`.
Installing dependencies never generates a profile or approves publication.

The reviewed base runtime is CPython 3.11.17 on Linux x86_64 with the official
Actions Ubuntu 24.04 interpreter build. Its executable and complete physical
standard-library fingerprints are fixed in the profile table. The official archive
SHA-256 is `ae713815fe406a06f1691856f697a0b1e58b3e986f44e62f0cd0bca2424f1aac`.
The shared workflow pins Ubuntu 24.04, Python 3.11.17 and uv 0.11.17. An overridden
runtime must qualify its own source-owned profile; a version label alone cannot
substitute for actual interpreter, native, package, startup and callback bytes.

| Recipe | Dependency owner | Revision-date plugin |
| --- | --- | --- |
| `history` | `requirements.lock` | 1.6.0 |
| `history-legacy` | `requirements-legacy.lock` | 1.5.1 |
| `history-media` | `requirements-media.lock` | 1.6.0 |

Both base recipes retain MkDocs 1.6.1, Material 9.7.7 and the same 36-package closure.
The legacy recipe preserves a consumer's independently frozen revision-history
contract. The media recipe adds the six exact minification/lightbox dependencies;
two source-only minifiers are built by a separately frozen three-package builder.
The admitted archive and independently reproduced pure-wheel hashes are source owned,
and ordinary dependency installation remains binary-only. For these two local wheels,
uv records an installation timestamp in non-executable `uv_cache.json`. The installer
validates its exact clock-only schema and RECORD hash, then removes only that
bookkeeping input and its RECORD row. Package source bytes remain unchanged, and
all remaining physical inputs must match the approved profile. Candidate observations
cannot approve a wheel; the production builder requires the checked-in wheel hashes.
A consumer must qualify its actual configuration, authored hooks,
committed source history, routes and output against the selected publication recipe.
A successful baseline profile selection does not establish those consumer facts.

From a consumer with accepted synchronized shared documentation:

```sh
python3 .bijux/shared/bijux-docs/tooling/security/install_publication_renderer.py \
  --recipe history --python "$(command -v python3)"
```

The result is `artifacts/docs/publication/python/bin/python`, and its physical
admission receipt stays outside the site. Existing environments are preserved;
choose an explicit fresh `--directory` for another local qualification. Directory
traversal, symlink parents, floating interpreter patches, another installer,
unknown profiles and changed installed bytes fail closed.

Use `tooling/security/publication_builder.py` with that actual interpreter to
`capture`, `render`, `admit` and `verify`. Capture needs the independently fetched
accepted `BIJUX_STD_ROOT`, the tracked `.github/standards/bijux-docs.sha` publication
pointer, the actual tracked configuration, production site identity
and reviewed build/verification command strings. Rendering independently reconstructs
the producer and applies CSP. A consumer's own useful verifier runs before admission.
Final verification always requires the reconstructed qualified manifest; bytes-only
recovery does not authorize a publisher.

The interpreter and package inventories include native extensions. The managed
Ubuntu runner and its operating-system dynamic libraries remain a platform trust
boundary; these profiles do not make a container-isolation or fully hermetic build
claim. Normal source and runner maintenance requires actual renewed qualification
when the observed profile or supported configuration changes.
