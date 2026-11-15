#!/usr/bin/env bash
# Classify authored checkouts by identity and layout; revision acceptance is separate.
is_standard_source_checkout() {
  local root="$1" remote
  local -a remotes=()
  [[ -f "${root}/shared/shared-dir-sha256.txt" && -d "${root}/shared/bijux-checks" ]] || return 1
  # Runner authentication rewrites affect transport, not the configured identity.
  while IFS= read -r -d '' remote; do
    remotes+=("${remote}")
  done < <(git -C "${root}" config --null --get-all remote.origin.url 2>/dev/null)
  [[ "${#remotes[@]}" -eq 1 ]] || return 1
  remote="${remotes[0]}"
  case "${remote}" in
    https://gitlab.com/bijux-oss/bijux-std|https://gitlab.com/bijux-oss/bijux-std.git) return 0 ;;
    git@gitlab.com:bijux-oss/bijux-std|git@gitlab.com:bijux-oss/bijux-std.git) return 0 ;;
    ssh://git@gitlab.com/bijux-oss/bijux-std.git|ssh://git@gitlab.com:22/bijux-oss/bijux-std.git) return 0 ;;
    https://github.com/bijux/bijux-std|https://github.com/bijux/bijux-std.git|git@github.com:bijux/bijux-std|git@github.com:bijux/bijux-std.git) return 0 ;;
    *) return 1 ;;
  esac
}
