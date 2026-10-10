#!/usr/bin/env bash
set -euo pipefail

source_root="${1:?explicit fetched standard checkout is required}"
expected_sha="${2:?expected full standard SHA is required}"
expected_origin="${BIJUX_STD_GIT_URL:-https://github.com/bijux/bijux-std.git}"
[[ "${expected_sha}" =~ ^[a-f0-9]{40}$ ]] || { echo 'ERROR: expected standard SHA must contain 40 lowercase hexadecimal characters' >&2; exit 1; }
source_root="$(cd "${source_root}" && pwd -P)"
actual_root="$(git -C "${source_root}" rev-parse --show-toplevel)"
[[ "${actual_root}" == "${source_root}" ]] || { echo 'ERROR: standard authority must be an explicit repository root' >&2; exit 1; }
actual_origin="$(git -C "${source_root}" remote get-url origin)"
[[ "${actual_origin}" == "${expected_origin}" ]] || { echo 'ERROR: standard authority origin differs from requested source' >&2; exit 1; }
if [[ "${BIJUX_STD_ALLOW_LOCAL_SOURCE:-0}" != '1' ]]; then
  case "${actual_origin}" in
    https://github.com/bijux/bijux-std.git|git@github.com:bijux/bijux-std.git) ;;
    *) echo 'ERROR: accepted rollout requires the bijux-std GitHub source; local verification requires BIJUX_STD_ALLOW_LOCAL_SOURCE=1' >&2; exit 1 ;;
  esac
fi
[[ "$(git -C "${source_root}" rev-parse HEAD)" == "${expected_sha}" ]] || { echo 'ERROR: standard authority HEAD differs from requested SHA' >&2; exit 1; }
[[ -z "$(git -C "${source_root}" status --porcelain --untracked-files=all)" ]] || { echo 'ERROR: standard authority has modified or untracked inputs' >&2; exit 1; }
# Fetch the exact object independently; a matching incidental sibling HEAD is insufficient.
git -C "${source_root}" fetch --quiet --depth 1 origin "${expected_sha}"
[[ "$(git -C "${source_root}" rev-parse 'FETCH_HEAD^{commit}')" == "${expected_sha}" ]] || { echo 'ERROR: fetched standard source differs from requested SHA' >&2; exit 1; }
git -C "${source_root}" diff --quiet "${expected_sha}" --
[[ -z "$(git -C "${source_root}" status --porcelain --untracked-files=all)" ]] || { echo 'ERROR: standard authority changed during verification' >&2; exit 1; }
printf 'Verified %s source %s from %s\n' "$( [[ "${BIJUX_STD_ALLOW_LOCAL_SOURCE:-0}" == '1' ]] && printf 'local-verification-only' || printf 'GitHub' )" "${expected_sha}" "${actual_origin}"
