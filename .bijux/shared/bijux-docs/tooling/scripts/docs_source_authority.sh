#!/usr/bin/env bash
# Verify an explicit consumer and canonical shared docs tree.
verify_docs_authority() {
  local repo_root="${1:?consumer repository root is required}"
  local shared_root="${2:?canonical shared docs root is required}"
  if [[ "${BIJUX_STD_LOCAL_VERIFY:-0}" == '1' ]]; then
    export BIJUX_DOCS_SOURCE_MODE='local-verification'
    unset BIJUX_DOCS_SOURCE_SHA BIJUX_DOCS_SOURCE_ORIGIN
    echo 'Local candidate verification only; this is not accepted consumer rollout provenance'
    return
  fi
  if [[ -z "${BIJUX_STD_ROOT:-}" ]]; then
    echo 'ERROR: BIJUX_STD_ROOT must explicitly identify the fetched accepted standard checkout; no sibling fallback' >&2
    exit 1
  fi
  local pin="${BIJUX_STD_REF:-}"
  if [[ -z "${pin}" && -f "${repo_root}/.github/standards/bijux-std.sha" ]]; then
    pin="$(tr -d '[:space:]' < "${repo_root}/.github/standards/bijux-std.sha")"
  fi
  local authority_guard="${shared_root}/../bijux-checks/scripts/verify-accepted-source.sh"
  if [[ ! -f "${authority_guard}" ]]; then
    echo 'ERROR: accepted source guard is unavailable; refresh the admitted standard tooling first' >&2
    exit 1
  fi
  bash "${authority_guard}" "${BIJUX_STD_ROOT}" "${pin}"
  local digest_tool="${shared_root}/../bijux-checks/scripts/directory-tree-sha256.sh"
  [[ "$(bash "${digest_tool}" "${shared_root}")" == "$(bash "${digest_tool}" "${BIJUX_STD_ROOT}/shared/bijux-docs")" ]] || {
    echo 'ERROR: local shared docs differ from the exact fetched accepted standard source' >&2
    exit 1
  }
  if [[ -e "${repo_root}/makes/bijux-py/root/docs.mk" || -e "${repo_root}/makes/bijux-py/ci/docs.mk" ]]; then
    local local_makes="${shared_root}/../bijux-makes-py"
    local accepted_makes="${BIJUX_STD_ROOT}/shared/bijux-makes-py"
    if [[ ! -d "${local_makes}" || ! -d "${accepted_makes}" ]]; then
      echo 'ERROR: applicable Python docs profiles require the exact fetched shared Make source' >&2
      exit 1
    fi
    [[ "$(bash "${digest_tool}" "${local_makes}")" == "$(bash "${digest_tool}" "${accepted_makes}")" ]] || {
      echo 'ERROR: local shared Python Make profiles differ from the exact fetched accepted standard source' >&2
      exit 1
    }
  fi
  local actual_origin
  actual_origin="$(git -C "${BIJUX_STD_ROOT}" remote get-url origin)"
  case "${actual_origin}" in
    https://github.com/bijux/bijux-std.git|git@github.com:bijux/bijux-std.git)
      export BIJUX_DOCS_SOURCE_MODE='accepted-github'
      export BIJUX_DOCS_SOURCE_SHA="${pin}"
      export BIJUX_DOCS_SOURCE_ORIGIN="${actual_origin}"
      ;;
    *)
      export BIJUX_DOCS_SOURCE_MODE='local-verification'
      unset BIJUX_DOCS_SOURCE_SHA BIJUX_DOCS_SOURCE_ORIGIN
      ;;
  esac
}
