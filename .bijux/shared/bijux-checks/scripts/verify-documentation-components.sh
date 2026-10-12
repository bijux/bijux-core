#!/usr/bin/env bash
# Compose independently accepted reader and common standards without weakening local checks.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
[[ "$#" == 0 ]] || { echo 'ERROR: documentation component verification takes no arguments' >&2; exit 2; }

repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"
shared_root="${repo_root}/.bijux/shared"
docs_root="${shared_root}/bijux-docs"
old_guard="${docs_root}/tooling/scripts/verify_bijux_docs_source_of_truth.sh"
if [[ "${BIJUX_STD_LOCAL_VERIFY:-0}" == 1 ]]; then
  bash "${old_guard}"
  echo 'Documentation components local candidate checks passed; accepted sources were not verified'
  exit 0
fi
[[ "${BIJUX_STD_LOCAL_VERIFY:-0}" == 0 && "${BIJUX_STD_ALLOW_LOCAL_SOURCE:-0}" == 0 ]] || {
  echo 'ERROR: accepted documentation components forbid local-source bypass flags' >&2; exit 1;
}

read_pin() {
  local relative="$1" path="${repo_root}/$1"
  [[ -f "${path}" && ! -L "${path}" && ! -L "${repo_root}/.github" && ! -L "${repo_root}/.github/standards" ]] || { echo 'ERROR: documentation components require regular tracked pins' >&2; exit 1; }
  git ls-files --error-unmatch "${relative}" >/dev/null
  local value
  value="$(cat "${path}")"
  [[ "${value}" =~ ^[0-9a-f]{40}$ ]] || { echo 'ERROR: documentation components require full lowercase source SHAs' >&2; exit 1; }
  printf '%s\n' "${value}"
}
standard_sha="$(read_pin .github/standards/bijux-std.sha)"
documentation_sha="$(read_pin .github/standards/bijux-docs.sha)"
[[ -z "${BIJUX_STD_REF:-}" || "${BIJUX_STD_REF}" == "${documentation_sha}" ]] || {
  echo 'ERROR: documentation source override differs from the declared docs pin' >&2; exit 1;
}

fetch_source() {
  local sha="$1" role="$2" directory="${repo_root}/artifacts/documentation-components/$2/$1"
  local current="${repo_root}" part
  for part in artifacts documentation-components "${role}" "${sha}"; do
    current="${current}/${part}"
    [[ ! -L "${current}" ]] || { echo 'ERROR: documentation component cache cannot contain path aliases' >&2; exit 1; }
  done
  if [[ ! -e "${directory}" ]]; then
    mkdir -p "${directory}"
    git -C "${directory}" init --quiet
    git -C "${directory}" remote add origin https://github.com/bijux/bijux-std.git
    git -C "${directory}" fetch --quiet --depth 1 origin "${sha}"
    git -C "${directory}" checkout --quiet --detach FETCH_HEAD
  fi
  printf '%s\n' "${directory}"
}
standard_source="$(fetch_source "${standard_sha}" standard)"
documentation_source="${BIJUX_STD_ROOT:-}"
if [[ -z "${documentation_source}" ]]; then
  documentation_source="$(fetch_source "${documentation_sha}" documentation)"
fi

admit_source() {
  local source="$1" sha="$2" origin
  [[ -d "${source}/.git" && ! -L "${source}" && ! -L "${source}/.git" ]] || {
    echo 'ERROR: documentation component source requires a regular independent Git checkout' >&2; exit 1;
  }
  [[ "$(git -C "${source}" rev-parse --show-toplevel)" == "${source}" && "$(git -C "${source}" rev-parse HEAD)" == "${sha}" ]] || {
    echo 'ERROR: documentation component source identity differs from its declared pin' >&2; exit 1;
  }
  origin="$(git -C "${source}" remote get-url origin)"
  case "${origin}" in
    https://github.com/bijux/bijux-std.git|git@github.com:bijux/bijux-std.git) ;;
    *) echo 'ERROR: documentation components require official accepted GitHub sources' >&2; exit 1 ;;
  esac
  [[ -z "$(git -C "${source}" status --porcelain --untracked-files=all)" ]] || {
    echo 'ERROR: documentation component source has modified or untracked inputs' >&2; exit 1;
  }
  BIJUX_STD_GIT_URL="${origin}" bash "${standard_source}/shared/bijux-checks/scripts/verify-accepted-source.sh" "${source}" "${sha}"
}

verify_pins() {
  [[ "$(read_pin .github/standards/bijux-std.sha)" == "${standard_sha}" && "$(read_pin .github/standards/bijux-docs.sha)" == "${documentation_sha}" ]] || {
    echo 'ERROR: documentation component source pins changed during verification' >&2; exit 1;
  }
}

component_capabilities_before=""
verify_components() {
  admit_source "${standard_source}" "${standard_sha}"
  admit_source "${documentation_source}" "${documentation_sha}"
  # The finite source-owned configuration covers every installed manifest row.
  local component_capabilities
  component_capabilities="$(python3 - "${shared_root}" "${standard_source}/shared/bijux-checks/bijux-std-checks.yml" <<'PY'
from pathlib import Path
import re
import sys
shared, config = map(Path, sys.argv[1:])
if shared.is_symlink() or shared.parent.is_symlink():
    raise SystemExit('ERROR: documentation component paths cannot contain aliases')
allowed = set()
active = False
for line in config.read_text().splitlines():
    if line == 'directories:': active = True; continue
    if active and not line.startswith(' '): active = False
    if active and line.startswith('  - '): allowed.add(line[4:])
manifest = shared / 'shared-dir-sha256.txt'
if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_nlink != 1:
    raise SystemExit('ERROR: documentation component manifest must be a regular unaliased file')
rows = [line.split() for line in manifest.read_text().splitlines() if line.strip()]
if not rows or any(len(row) != 2 or not re.fullmatch(r'[0-9a-f]{64}', row[0]) or row[1] not in allowed for row in rows):
    raise SystemExit('ERROR: documentation component manifest requires finite canonical rows')
if len({row[1] for row in rows}) != len(rows):
    raise SystemExit('ERROR: documentation component manifest contains duplicate rows')
installed = {'shared/' + path.name for path in shared.iterdir() if path.is_dir() or path.is_symlink()}
mandatory = {'shared/bijux-docs', 'shared/bijux-makes', 'shared/bijux-checks', 'shared/bijux-gh'}
if not mandatory <= installed or not installed <= allowed or {row[1] for row in rows} != installed:
    raise SystemExit('ERROR: documentation component manifest does not cover its complete installed capability closure')
capabilities = ['common', 'docs']
for name, capability in [('shared/bijux-makes-py', 'python'), ('shared/bijux-makes-rs', 'rust')]:
    if name in installed: capabilities.append(capability)
for relative in installed:
    directory = shared / relative.removeprefix('shared/')
    if directory.is_symlink() or not directory.is_dir():
        raise SystemExit('ERROR: documentation components require regular installed directories')
    for path in directory.rglob('*'):
        if path.is_symlink() or not (path.is_dir() or path.is_file()) or (path.is_file() and path.stat().st_nlink != 1):
            raise SystemExit('ERROR: documentation components cannot contain aliases or special files')
print(' '.join(capabilities))
PY
)"
  if [[ -n "${component_capabilities_before}" && "${component_capabilities}" != "${component_capabilities_before}" ]]; then
    echo 'ERROR: installed documentation component closure changed during verification' >&2; exit 1;
  fi
  component_capabilities_before="${component_capabilities}"
  BIJUX_STD_CONFIG="${standard_source}/shared/bijux-checks/bijux-std-checks.yml" \
    BIJUX_STD_CAPABILITIES="${component_capabilities}" BIJUX_STD_REF="${standard_sha}" \
    BIJUX_STD_GIT_URL=https://github.com/bijux/bijux-std.git \
    BIJUX_STD_ROOT="${standard_source}" BIJUX_STD_STRICT_REMOTE=1 \
    BIJUX_STD_REQUIRE_REMOTE_MATCH=1 \
    bash "${standard_source}/shared/bijux-checks/check-bijux-std.sh"
  (
    export BIJUX_STD_ROOT="${documentation_source}" BIJUX_STD_REF="${documentation_sha}"
    source "${documentation_source}/shared/bijux-docs/tooling/scripts/docs_source_authority.sh"
    verify_docs_authority "${repo_root}" "${docs_root}"
  )
  verify_pins
}

verify_components
# Only the known single-source comparison is replaced. Accepted projection
# provenance and every original physical/local-manifest/site control remain.
control_directory="$(mktemp -d "${repo_root}/artifacts/documentation-components/controls.XXXXXX")"
trap 'rm -rf "${control_directory}"' EXIT
python3 - "${old_guard}" "${standard_source}/shared/bijux-docs/tooling/scripts/verify_bijux_docs_source_of_truth.sh" "${control_directory}/retained-source-controls.sh" <<'PY'
from pathlib import Path
import sys
retained, canonical, output = map(Path, sys.argv[1:])
body = retained.read_bytes()
if body != canonical.read_bytes():
    raise SystemExit('ERROR: unsupported retained documentation source-of-truth contract')
start = b'std_root="${BIJUX_STD_ROOT}"\n'
end = b'verify_docs_authority "${repo_root}" "${shared_root}"\n'
message = b'echo "Bijux docs source-of-truth checks passed against exact accepted source"\n'
if body.count(start) != 1 or body.count(end) != 2 or body.count(message) != 1:
    raise SystemExit('ERROR: documentation source-of-truth composition boundaries are ambiguous')
prefix, remainder = body.split(start)
comparison, tail = remainder.rsplit(end, 1)
if not comparison.startswith(b'std_manifest="${std_root}/shared/shared-dir-sha256.txt"\n') or b'for dir_rel in "${local_dirs[@]}"; do\n' not in comparison:
    raise SystemExit('ERROR: documentation source-of-truth comparison contract is unknown')
tail = tail.replace(message, b'echo "Retained documentation source controls passed; component post-verification pending"\n')
output.write_bytes(prefix + end + tail)
PY
BIJUX_STD_ROOT="${documentation_source}" BIJUX_STD_REF="${documentation_sha}" \
  bash "${control_directory}/retained-source-controls.sh"
verify_components
echo 'Documentation source-of-truth checks passed against both exact accepted component sources'
