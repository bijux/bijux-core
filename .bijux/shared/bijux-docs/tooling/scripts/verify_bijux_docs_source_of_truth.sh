#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

repo_root="$(git rev-parse --show-toplevel)"
if [[ -d "${repo_root}/shared/bijux-docs" ]]; then
  shared_prefix="shared"
elif [[ -d "${repo_root}/.bijux/shared/bijux-docs" ]]; then
  shared_prefix=".bijux/shared"
else
  echo "ERROR: missing shared bijux docs directory (expected shared/bijux-docs or .bijux/shared/bijux-docs)" >&2
  exit 1
fi

shared_root="${repo_root}/${shared_prefix}/bijux-docs"
# shellcheck source=shared/bijux-docs/tooling/scripts/docs_source_authority.sh
source "${shared_root}/tooling/scripts/docs_source_authority.sh"
verify_docs_authority "${repo_root}" "${shared_root}"
python3 "${shared_root}/tooling/scripts/project_bijux_docs.py" "${repo_root}" "${shared_root}" --check
python3 "${shared_root}/tooling/scripts/sync_mkdocs_hub.py" "${repo_root}" "${shared_root}" --check

if [[ -d "${repo_root}/overrides" ]]; then
  echo "ERROR: root overrides/ must not exist; use ${shared_prefix}/bijux-docs as docs source of truth" >&2
  exit 1
fi

compare_required() {
  local source_rel="$1"
  local generated_rel="$2"

  local source_path="${repo_root}/${source_rel}"
  local generated_path="${repo_root}/${generated_rel}"

  if [[ ! -f "${source_path}" ]]; then
    echo "ERROR: missing source file ${source_rel}" >&2
    exit 1
  fi

  if [[ ! -f "${generated_path}" ]]; then
    echo "ERROR: missing generated file ${generated_rel}" >&2
    echo "Run: make bijux-docs-sync" >&2
    exit 1
  fi

  if ! cmp -s "${source_path}" "${generated_path}"; then
    echo "ERROR: ${generated_rel} drifted from ${source_rel}" >&2
    echo "Run: make bijux-docs-sync" >&2
    exit 1
  fi
}

directory_tree_sha256() {
  local target_dir="$1"
  local digest_script="${repo_root}/${shared_prefix}/bijux-checks/scripts/directory-tree-sha256.sh"
  if [[ ! -x "${digest_script}" ]]; then
    echo "ERROR: missing shared directory digest tool ${digest_script}" >&2
    exit 1
  fi
  "${digest_script}" "${target_dir}"
}

manifest_sha_for_dir() {
  local manifest_path="$1"
  local dir_rel="$2"
  awk -v dir_rel="${dir_rel}" '$2 == dir_rel { print $1 }' "${manifest_path}"
}

verify_shared_manifest_entry() {
  local manifest_path="$1"
  local dir_rel="$2"
  local repo_label="$3"
  local manifest_dir_rel="${4:-$2}"

  local expected_sha
  expected_sha="$(manifest_sha_for_dir "${manifest_path}" "${manifest_dir_rel}")"
  if [[ -z "${expected_sha}" ]]; then
    echo "ERROR: ${manifest_path} missing entry for ${manifest_dir_rel} (${repo_label})" >&2
    exit 1
  fi

  local computed_sha
  computed_sha="$(directory_tree_sha256 "${repo_root}/${dir_rel}")"
  if [[ "${computed_sha}" != "${expected_sha}" ]]; then
    echo "ERROR: ${dir_rel} SHA mismatch for ${repo_label}" >&2
    echo "Expected: ${expected_sha}" >&2
    echo "Actual:   ${computed_sha}" >&2
    exit 1
  fi
}

assert_absent() {
  local rel_path="$1"
  if [[ -e "${repo_root}/${rel_path}" ]]; then
    echo "ERROR: generated root path must not exist: ${rel_path}" >&2
    echo "Source-only root policy keeps generated site output out of main branch." >&2
    exit 1
  fi
}

# shared -> docs (authoritative docs source)
compare_required "${shared_prefix}/bijux-docs/partials/header.html" "docs/overrides/partials/header.html"
compare_required "${shared_prefix}/bijux-docs/partials/footer.html" "docs/overrides/partials/footer.html"
compare_required "${shared_prefix}/bijux-docs/partials/footer-profile-links.html" "docs/overrides/partials/footer-profile-links.html"
compare_required "${shared_prefix}/bijux-docs/partials/nav.html" "docs/overrides/partials/nav.html"
compare_required "${shared_prefix}/bijux-docs/partials/nav-item.html" "docs/overrides/partials/nav-item.html"
compare_required "${shared_prefix}/bijux-docs/partials/bijux-nav.html" "docs/overrides/partials/bijux-nav.html"

for style in 00-tokens.css 01-theme.css 02-layout.css 03-header.css 04-nav.css 05-content.css 06-components.css 07-utilities.css 08-responsive.css extra.css; do
  compare_required "${shared_prefix}/bijux-docs/styles/${style}" "docs/assets/styles/${style}"
done

for script in bootstrap.js detail-tabs.js nav-reveal.js nav-state.js theme-persistence.js viewport-profile.js; do
  compare_required "${shared_prefix}/bijux-docs/scripts/${script}" "docs/assets/javascripts/shell/${script}"
done
compare_required "${shared_prefix}/bijux-docs/scripts/nav-sync.js" "docs/assets/javascripts/navigation-sync.js"
compare_required "${shared_prefix}/bijux-docs/scripts/mermaid-init.js" "docs/assets/javascripts/mermaid-init.js"
compare_required "${shared_prefix}/bijux-docs/assets/bijux_icon.png" "docs/assets/bijux_icon.png"
compare_required "${shared_prefix}/bijux-docs/assets/bijux_logo_hq.png" "docs/assets/bijux_logo_hq.png"
compare_required "${shared_prefix}/bijux-docs/assets/site-icons/favicon.ico" "docs/assets/site-icons/favicon.ico"
compare_required "${shared_prefix}/bijux-docs/assets/site-icons/apple-touch-icon.png" "docs/assets/site-icons/apple-touch-icon.png"
compare_required "${shared_prefix}/bijux-docs/assets/site-icons/apple-touch-icon-precomposed.png" "docs/assets/site-icons/apple-touch-icon-precomposed.png"

# root must stay source-only
assert_absent "assets"
assert_absent "404.html"
assert_absent "index.html"
assert_absent "learning"
assert_absent "platform"
assert_absent "projects"
assert_absent "reading-paths"
assert_absent "search"
assert_absent "sitemap.xml"
assert_absent "sitemap.xml.gz"

# shared directory SHA contract
local_manifest="${repo_root}/${shared_prefix}/shared-dir-sha256.txt"
if [[ ! -f "${local_manifest}" ]]; then
  echo "ERROR: missing local shared SHA manifest ${shared_prefix}/shared-dir-sha256.txt" >&2
  exit 1
fi

manifest_entry_count=0
local_dirs=()
while read -r _ manifest_dir_rel; do
  [[ -n "${manifest_dir_rel}" ]] || continue
  case "${manifest_dir_rel}" in
    shared/*)
      dir_rel="${shared_prefix}/${manifest_dir_rel#shared/}"
      ;;
    *)
      echo "ERROR: unsupported shared manifest path: ${manifest_dir_rel}" >&2
      exit 1
      ;;
  esac
  local_dirs+=("${dir_rel}")
  verify_shared_manifest_entry "${local_manifest}" "${dir_rel}" "local repository" "${manifest_dir_rel}"
  manifest_entry_count=$((manifest_entry_count + 1))
done < <(awk 'NF' "${local_manifest}")

if [[ "${manifest_entry_count}" -eq 0 ]]; then
  echo "ERROR: shared SHA manifest is empty: ${local_manifest}" >&2
  exit 1
fi

if [[ "${BIJUX_STD_LOCAL_VERIFY:-0}" == "1" ]]; then
  if [[ -n "${DOCS_SITE_DIR:-}" ]]; then
    bash "${shared_root}/tooling/scripts/verify_bijux_docs_site.sh"
  fi
  echo "Bijux docs local candidate source-of-truth checks passed; accepted rollout was not verified"
  exit 0
fi
std_root="${BIJUX_STD_ROOT}"
std_manifest="${std_root}/shared/shared-dir-sha256.txt"

if [[ -f "${std_manifest}" ]]; then
  for dir_rel in "${local_dirs[@]}"; do
    std_dir_rel="${dir_rel#.bijux/}"
    local_manifest_sha="$(manifest_sha_for_dir "${local_manifest}" "${std_dir_rel}")"
    std_manifest_sha="$(manifest_sha_for_dir "${std_manifest}" "${std_dir_rel}")"
    if [[ -z "${std_manifest_sha}" ]]; then
      echo "ERROR: bijux-std manifest missing ${std_dir_rel}" >&2
      exit 1
    fi
    if [[ "${local_manifest_sha}" != "${std_manifest_sha}" ]]; then
      echo "ERROR: manifest entry drift for ${dir_rel}" >&2
      echo "Local manifest SHA: ${local_manifest_sha}" >&2
      echo "Std manifest SHA:   ${std_manifest_sha}" >&2
      exit 1
    fi

    local_sha="$(directory_tree_sha256 "${repo_root}/${dir_rel}")"
    std_sha="$(directory_tree_sha256 "${std_root}/${std_dir_rel}")"
    if [[ "${local_sha}" != "${std_sha}" ]]; then
      echo "ERROR: ${dir_rel} drift vs bijux-std" >&2
      echo "Local SHA: ${local_sha}" >&2
      echo "Std SHA:   ${std_sha}" >&2
      exit 1
    fi
  done
else
  echo "ERROR: accepted standard manifest is unavailable: ${std_manifest}" >&2
  exit 1
fi

verify_docs_authority "${repo_root}" "${shared_root}"
if [[ -n "${DOCS_SITE_DIR:-}" ]]; then
  bash "${shared_root}/tooling/scripts/verify_bijux_docs_site.sh"
fi
echo "Bijux docs source-of-truth checks passed against exact accepted source"
