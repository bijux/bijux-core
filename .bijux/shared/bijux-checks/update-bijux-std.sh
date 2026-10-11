#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
bijux_std_artifact_root="${repo_root}/artifacts/bijux-std"
mkdir -p "${bijux_std_artifact_root}"
default_config_path="${repo_root}/.bijux/shared/bijux-checks/bijux-std-checks.yml"
if [[ ! -f "${default_config_path}" ]]; then
  default_config_path="${repo_root}/shared/bijux-checks/bijux-std-checks.yml"
fi
config_path="${BIJUX_STD_CONFIG:-${default_config_path}}"

if [[ ! -f "${config_path}" ]]; then
  echo "ERROR: missing config ${config_path}" >&2
  exit 1
fi

directory_resolver="${script_dir}/scripts/resolve-shared-directories.sh"
if [[ ! -x "${directory_resolver}" ]]; then
  echo "ERROR: shared directory resolver is unavailable: ${directory_resolver}" >&2
  exit 1
fi

read_scalar() {
  local key="$1"
  awk -F': ' -v key="${key}" '$1 == key {print $2; exit}' "${config_path}" | tr -d '"'
}

read_directories() {
  "${directory_resolver}" --all "${config_path}"
}

read_selected_directories() {
  "${directory_resolver}" --select "${config_path}" "${BIJUX_STD_CAPABILITIES:-}"
}

resolve_local_rel() {
  local rel="$1"
  if [[ "${rel}" == shared/* && -d "${repo_root}/.bijux/shared" && "$(basename "${repo_root}")" != "bijux-std" ]]; then
    printf '.bijux/%s\n' "${rel}"
    return
  fi
  printf '%s\n' "${rel}"
}

manifest_rel="$(read_scalar manifest)"
git_url_default="$(read_scalar '  git_url')"
default_ref="$(read_scalar '  default_ref')"
tag_pattern_default="$(read_scalar '  tag_pattern')"

std_git_url="${BIJUX_STD_GIT_URL:-${git_url_default}}"
update_channel="${BIJUX_STD_UPDATE_CHANNEL:-branch}"
std_ref="${BIJUX_STD_REF:-${default_ref}}"
tag_pattern="${BIJUX_STD_TAG_PATTERN:-${tag_pattern_default}}"
allow_missing_dirs="${BIJUX_STD_UPDATE_ALLOW_MISSING_DIRS:-0}"
self_repo_mode="${BIJUX_STD_SELF_REPO_MODE:-auto}"
all_directories="$(read_directories)"
selected_directories="$(read_selected_directories)"

resolve_ref() {
  if [[ "${update_channel}" == "tag" ]]; then
    local latest_tag
    latest_tag="$(git ls-remote --tags --refs "${std_git_url}" "${tag_pattern}" | awk '{print $2}' | sed 's#refs/tags/##' | sort -V | tail -n 1)"
    if [[ -z "${latest_tag}" ]]; then
      echo "ERROR: no tags found matching pattern '${tag_pattern}' in ${std_git_url}" >&2
      exit 1
    fi
    echo "${latest_tag}"
    return
  fi

  echo "${std_ref}"
}

resolved_ref="$(resolve_ref)"
tmp_dir="$(mktemp -d "${bijux_std_artifact_root}/update-source.XXXXXX")"
staging_dir="$(mktemp -d "${bijux_std_artifact_root}/update-stage.XXXXXX")"
cleanup() {
  rm -rf "${tmp_dir}"
  rm -rf "${staging_dir}"
}
trap cleanup EXIT

clone_from_ref() {
  local ref_name="$1"
  local destination="${tmp_dir}/bijux-std"
  git init --quiet "${destination}"
  git -C "${destination}" remote add origin "${std_git_url}"
  git -C "${destination}" fetch --quiet --depth 1 origin "${ref_name}"
  git -C "${destination}" checkout --quiet --detach FETCH_HEAD
}

directory_tree_sha256() {
  local target_dir="$1"
  "${script_dir}/scripts/directory-tree-sha256.sh" "${target_dir}"
}

set_manifest_sha_for_dir() {
  local manifest_path="$1"
  local dir_rel="$2"
  local sha="$3"
  local tmp_manifest="${manifest_path}.tmp"

  awk -v dir_rel="${dir_rel}" -v sha="${sha}" '
    BEGIN {updated=0}
    $2 == dir_rel {print sha " " dir_rel; updated=1; next}
    {print}
    END {
      if (!updated) {
        print sha " " dir_rel
      }
    }
  ' "${manifest_path}" > "${tmp_manifest}"
  mv "${tmp_manifest}" "${manifest_path}"
}

rewrite_manifest_for_directories() {
  local manifest_path="$1"
  local directories="$2"
  local ordered_manifest="${manifest_path}.ordered"
  : >"${ordered_manifest}"

  while IFS= read -r dir_rel; do
    entry="$(awk -v dir_rel="${dir_rel}" '$2 == dir_rel {print; exit}' "${manifest_path}")"
    if [[ -z "${entry}" ]]; then
      echo "ERROR: shared manifest entry is unavailable after refresh: ${dir_rel}" >&2
      exit 1
    fi
    printf '%s\n' "${entry}" >>"${ordered_manifest}"
  done <<<"${directories}"

  mv "${ordered_manifest}" "${manifest_path}"
}

manifest_local_rel="$(resolve_local_rel "${manifest_rel}")"
manifest_path="${repo_root}/${manifest_local_rel}"
if [[ ! -f "${manifest_path}" ]]; then
  echo "ERROR: missing local manifest ${manifest_path}" >&2
  exit 1
fi

declare -a missing_dirs=()
declare -a update_dirs=()
declare -a skipped_dirs=()

in_bijux_std_repo=0
if [[ "$(basename "${repo_root}")" == "bijux-std" ]]; then
  in_bijux_std_repo=1
fi

should_use_self_repo_mode=0
if [[ "${self_repo_mode}" == "on" ]]; then
  should_use_self_repo_mode=1
elif [[ "${self_repo_mode}" == "auto" && "${in_bijux_std_repo}" == "1" ]]; then
  should_use_self_repo_mode=1
fi

if [[ "${should_use_self_repo_mode}" == "1" ]]; then
  while IFS= read -r remote_dir_rel; do
    local_dir_rel="$(resolve_local_rel "${remote_dir_rel}")"
    local_dir="${repo_root}/${local_dir_rel}"
    if [[ ! -d "${local_dir}" ]]; then
      if [[ "${allow_missing_dirs}" == "1" ]]; then
        skipped_dirs+=("${remote_dir_rel}")
        echo "⚠ missing local directory in bijux-std: ${local_dir_rel}; skipping because BIJUX_STD_UPDATE_ALLOW_MISSING_DIRS=1"
        continue
      fi
      missing_dirs+=("${local_dir_rel}")
      continue
    fi
    update_dirs+=("${remote_dir_rel}")
  done <<<"${all_directories}"

  if (( ${#missing_dirs[@]} > 0 )); then
    echo "ERROR: local refresh aborted; required directory missing in bijux-std:" >&2
    for dir_rel in "${missing_dirs[@]}"; do
      echo "  - ${dir_rel}" >&2
    done
    echo "Hint: rerun with BIJUX_STD_UPDATE_ALLOW_MISSING_DIRS=1 to skip missing directories." >&2
    exit 1
  fi

  for remote_dir_rel in "${update_dirs[@]}"; do
    local_dir_rel="$(resolve_local_rel "${remote_dir_rel}")"
    dir_sha="$(directory_tree_sha256 "${repo_root}/${local_dir_rel}")"
    set_manifest_sha_for_dir "${manifest_path}" "${remote_dir_rel}" "${dir_sha}"
    echo "→ refreshed manifest hash for ${local_dir_rel}"
  done
  rewrite_manifest_for_directories "${manifest_path}" "${all_directories}"

  if (( ${#skipped_dirs[@]} > 0 )); then
    for dir_rel in "${skipped_dirs[@]}"; do
      echo "→ kept local ${dir_rel}"
    done
  fi

  echo "→ refreshed ${manifest_rel}"
  echo "✔ bijux-std local shared manifest refresh complete"
  exit 0
fi

if [[ "${BIJUX_STD_ALLOW_LOCAL_SOURCE:-0}" != "1" ]]; then
  case "${std_git_url}" in
    https://github.com/bijux/bijux-std.git|git@github.com:bijux/bijux-std.git) ;;
    *) echo "ERROR: accepted rollout requires bijux-std GitHub source; local verification must be explicit" >&2; exit 1 ;;
  esac
fi
expected_sha=""
if [[ "${resolved_ref}" =~ ^[a-f0-9]{40}$ ]]; then
  expected_sha="${resolved_ref}"
else
  if [[ "${resolved_ref}" == refs/* ]]; then
    remote_matches="$(git ls-remote "${std_git_url}" "${resolved_ref}" "${resolved_ref}^{}")"
  else
    remote_matches="$(git ls-remote "${std_git_url}" "refs/heads/${resolved_ref}" "refs/tags/${resolved_ref}" "refs/tags/${resolved_ref}^{}")"
  fi
  [[ -n "${remote_matches}" ]] || { echo "ERROR: requested standard ref is unavailable: ${resolved_ref}" >&2; exit 1; }
  if [[ "$(printf '%s\n' "${remote_matches}" | awk '$2 !~ /\^\{\}$/ {n++} END {print n}')" != "1" ]]; then
    echo "ERROR: ambiguous standard ref; use a full commit SHA" >&2; exit 1
  fi
  expected_sha="$(printf '%s\n' "${remote_matches}" | awk 'END {print $1}')"
fi
if ! clone_from_ref "${resolved_ref}"; then
  echo "ERROR: unable to fetch exact requested standard ref ${resolved_ref}; no fallback is permitted" >&2
  exit 1
fi
fetched_sha="$(git -C "${tmp_dir}/bijux-std" rev-parse HEAD)"
[[ "${fetched_sha}" == "${expected_sha}" ]] || { echo "ERROR: requested and fetched standard SHA differ" >&2; exit 1; }
BIJUX_STD_GIT_URL="${std_git_url}" bash "${script_dir}/scripts/verify-accepted-source.sh" "${tmp_dir}/bijux-std" "${fetched_sha}"

while IFS= read -r remote_dir_rel; do
  src="${tmp_dir}/bijux-std/${remote_dir_rel}"
  if [[ ! -d "${src}" ]]; then
    if [[ "${allow_missing_dirs}" == "1" ]]; then
      skipped_dirs+=("${remote_dir_rel}")
      echo "⚠ missing source directory in bijux-std: ${remote_dir_rel}; skipping because BIJUX_STD_UPDATE_ALLOW_MISSING_DIRS=1"
      continue
    fi
    missing_dirs+=("${remote_dir_rel}")
    continue
  fi
  update_dirs+=("${remote_dir_rel}")
done <<<"${selected_directories}"

if (( ${#missing_dirs[@]} > 0 )); then
  echo "ERROR: update aborted before applying changes; source directory missing in bijux-std:" >&2
  for dir_rel in "${missing_dirs[@]}"; do
    echo "  - ${dir_rel}" >&2
  done
  echo "Hint: rerun with BIJUX_STD_UPDATE_ALLOW_MISSING_DIRS=1 to skip missing directories." >&2
  exit 1
fi

for remote_dir_rel in "${update_dirs[@]}"; do
  src="${tmp_dir}/bijux-std/${remote_dir_rel}"
  local_dir_rel="$(resolve_local_rel "${remote_dir_rel}")"
  stage="${staging_dir}/${local_dir_rel}"
  mkdir -p "$(dirname "${stage}")"
  cp -R "${src}" "${stage}"
done

BIJUX_STD_GIT_URL="${std_git_url}" bash "${script_dir}/scripts/verify-accepted-source.sh" "${tmp_dir}/bijux-std" "${fetched_sha}"

# Both installed and legacy managed trees may contain user work.
assert_managed_pristine() {
  local managed_rel="$1"
  if git -C "${repo_root}" rev-parse --verify HEAD >/dev/null 2>&1 && [[ -n "$(git -C "${repo_root}" ls-files --others --exclude-standard -- "${managed_rel}")" ]]; then
    echo "ERROR: preserve untracked managed input before refresh: ${managed_rel}" >&2; exit 1
  fi
  if ! git -C "${repo_root}" diff --quiet -- "${managed_rel}" || ! git -C "${repo_root}" diff --cached --quiet -- "${managed_rel}"; then
    echo "ERROR: preserve local managed changes before refresh: ${managed_rel}" >&2; exit 1
  fi
}
while IFS= read -r remote_dir_rel; do
  local_dir_rel="$(resolve_local_rel "${remote_dir_rel}")"
  assert_managed_pristine "${local_dir_rel}"
  if [[ "${local_dir_rel}" != "${remote_dir_rel}" ]]; then
    assert_managed_pristine "${remote_dir_rel}"
  fi
done <<<"${all_directories}"
if ! git -C "${repo_root}" diff --quiet -- "${manifest_local_rel}" || ! git -C "${repo_root}" diff --cached --quiet -- "${manifest_local_rel}"; then
  echo "ERROR: preserve local manifest changes before refresh" >&2; exit 1
fi
python3 - "${bijux_std_artifact_root}/source-provenance.json" "${std_git_url}" "${resolved_ref}" "${fetched_sha}" "${BIJUX_STD_ALLOW_LOCAL_SOURCE:-0}" "${BIJUX_STD_UPDATE_DRY_RUN:-0}" <<'PY_RECEIPT'
import json,sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps(dict(result="planned",origin=sys.argv[2],requested_ref=sys.argv[3],resolved_sha=sys.argv[4],verification_only=sys.argv[5]=='1',dry_run=sys.argv[6]=='1'),indent=2)+'\n')
PY_RECEIPT
if [[ "${BIJUX_STD_UPDATE_DRY_RUN:-0}" == "1" ]]; then
  for remote_dir_rel in "${update_dirs[@]}"; do
    local_dir_rel="$(resolve_local_rel "${remote_dir_rel}")"
    if [[ -d "${repo_root}/${local_dir_rel}" ]]; then
      diff -ru "${repo_root}/${local_dir_rel}" "${staging_dir}/${local_dir_rel}" || [[ "$?" == "1" ]]
    else
      printf 'Add managed directory %s\n' "${local_dir_rel}"
    fi
  done
  while IFS= read -r remote_dir_rel; do
    local_dir_rel="$(resolve_local_rel "${remote_dir_rel}")"
    if [[ -n "${BIJUX_STD_CAPABILITIES:-}" && "${in_bijux_std_repo}" == "0" ]] && ! grep -Fxq "${remote_dir_rel}" <<<"${selected_directories}" && [[ -d "${repo_root}/${local_dir_rel}" ]]; then
      printf 'Remove unselected managed directory %s\n' "${local_dir_rel}"
    fi
    if [[ "${local_dir_rel}" != "${remote_dir_rel}" && -d "${repo_root}/${remote_dir_rel}" ]] && grep -Fxq "${remote_dir_rel}" <<<"${selected_directories}"; then
      printf 'Remove legacy managed directory %s\n' "${remote_dir_rel}"
    fi
  done <<<"${all_directories}"
  echo "Verified standard refresh plan; managed consumer paths were not changed"
  exit 0
fi
recovery_dir="$(mktemp -d "${bijux_std_artifact_root}/recovery-source.XXXXXX")"
cp "${manifest_path}" "${recovery_dir}/shared-dir-sha256.txt"
while IFS= read -r remote_dir_rel; do
  local_dir_rel="$(resolve_local_rel "${remote_dir_rel}")"
  if [[ -d "${repo_root}/${local_dir_rel}" ]]; then
    mkdir -p "${recovery_dir}/$(dirname "${local_dir_rel}")"
    cp -R "${repo_root}/${local_dir_rel}" "${recovery_dir}/${local_dir_rel}"
  fi
  if [[ "${local_dir_rel}" != "${remote_dir_rel}" && -d "${repo_root}/${remote_dir_rel}" ]]; then
    mkdir -p "${recovery_dir}/$(dirname "${remote_dir_rel}")"
    cp -R "${repo_root}/${remote_dir_rel}" "${recovery_dir}/${remote_dir_rel}"
  fi
done <<<"${all_directories}"
python3 - "${bijux_std_artifact_root}/source-provenance.json" "${recovery_dir}" "${repo_root}/.github/standards/bijux-std.sha" <<'PY_RECOVERY'
import json,sys
from pathlib import Path
path=Path(sys.argv[1]);record=json.loads(path.read_text());pin=Path(sys.argv[3])
record.update(recovery_directory=sys.argv[2],previous_standard_sha=pin.read_text().strip() if pin.is_file() else None)
path.write_text(json.dumps(record,indent=2)+'\n')
PY_RECOVERY
for remote_dir_rel in "${update_dirs[@]}"; do
  local_dir_rel="$(resolve_local_rel "${remote_dir_rel}")"
  stage="${staging_dir}/${local_dir_rel}"
  dst="${repo_root}/${local_dir_rel}"

  preserve_children=0
  if (( ${#skipped_dirs[@]} > 0 )); then
    for skipped_dir in "${skipped_dirs[@]}"; do
      if [[ "${skipped_dir}" == "${remote_dir_rel}/"* ]]; then
        preserve_children=1
        break
      fi
    done
  fi

  if [[ "${preserve_children}" == "1" ]]; then
    mkdir -p "${dst}"
    cp -R "${stage}/." "${dst}/"
    echo "→ updated ${local_dir_rel} (preserved skipped nested directories)"
  else
    rm -rf "${dst}"
    mkdir -p "$(dirname "${dst}")"
    cp -R "${stage}" "${dst}"
    echo "→ updated ${local_dir_rel}"
  fi

  dir_sha="$(directory_tree_sha256 "${dst}")"
  set_manifest_sha_for_dir "${manifest_path}" "${remote_dir_rel}" "${dir_sha}"

  if [[ "${local_dir_rel}" != "${remote_dir_rel}" && -d "${repo_root}/${remote_dir_rel}" ]]; then
    rm -rf "${repo_root:?}/${remote_dir_rel}"
    echo "→ removed legacy ${remote_dir_rel}"
  fi
done

if [[ -n "${BIJUX_STD_CAPABILITIES:-}" && "${in_bijux_std_repo}" == "0" ]]; then
  while IFS= read -r remote_dir_rel; do
    if grep -Fxq "${remote_dir_rel}" <<<"${selected_directories}"; then
      continue
    fi
    local_dir_rel="$(resolve_local_rel "${remote_dir_rel}")"
    local_dir="${repo_root}/${local_dir_rel}"
    if [[ -d "${local_dir}" ]]; then
      rm -rf "${local_dir}"
      echo "→ removed unselected ${local_dir_rel}"
    fi
  done <<<"${all_directories}"
fi
rewrite_manifest_for_directories "${manifest_path}" "${selected_directories}"

if [[ -d "${repo_root}/.bijux/shared" && "$(basename "${repo_root}")" != "bijux-std" ]]; then
  if [[ -d "${repo_root}/shared" ]]; then
    if [[ -z "$(find "${repo_root}/shared" -mindepth 1 -print -quit 2>/dev/null)" ]]; then
      rmdir "${repo_root}/shared"
      echo "→ removed legacy shared/"
    fi
  fi
fi

if (( ${#skipped_dirs[@]} > 0 )); then
  for dir_rel in "${skipped_dirs[@]}"; do
    echo "→ kept local ${dir_rel}"
  done
fi

python3 - "${bijux_std_artifact_root}/source-provenance.json" <<'PY_FINISH'
import json,sys
from pathlib import Path
path=Path(sys.argv[1]);record=json.loads(path.read_text());record['result']='refreshed'
path.write_text(json.dumps(record,indent=2)+'\n')
PY_FINISH
echo "→ refreshed ${manifest_rel}"
echo "✔ bijux-std shared directories updated from ${std_git_url}@${resolved_ref}"
