#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
repo_root="$(git rev-parse --show-toplevel)"
if [[ -d "${repo_root}/shared/bijux-docs" ]]; then
  shared_root="${repo_root}/shared/bijux-docs"
elif [[ -d "${repo_root}/.bijux/shared/bijux-docs" ]]; then
  shared_root="${repo_root}/.bijux/shared/bijux-docs"
else
  echo 'ERROR: missing canonical shared docs directory' >&2; exit 1
fi
# shellcheck source=shared/bijux-docs/tooling/scripts/docs_source_authority.sh
source "${shared_root}/tooling/scripts/docs_source_authority.sh"
verify_docs_authority "${repo_root}" "${shared_root}"
# Resolve all copy inputs before the first generated document is modified.
python3 "${shared_root}/tooling/scripts/project_bijux_docs.py" "${repo_root}" "${shared_root}" --preflight --include-config
python3 "${shared_root}/tooling/scripts/sync_mkdocs_hub.py" "${repo_root}" "${shared_root}"
python3 "${shared_root}/tooling/scripts/project_bijux_docs.py" "${repo_root}" "${shared_root}"
verify_docs_authority "${repo_root}" "${shared_root}"
echo 'Bijux docs and applicable Python Make profiles synchronized from verified source'
