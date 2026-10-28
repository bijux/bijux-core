#!/usr/bin/env bash
set -euo pipefail

command_name="${1:-}"
case "${command_name}" in
  audit | coverage | fmt | format | lint | rustdoc | test | test-all | test-slow) ;;
  *)
    echo "usage: rust_gate.sh <audit|coverage|fmt|format|lint|rustdoc|test|test-all|test-slow>" >&2
    exit 2
    ;;
esac

require_tool() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "required tool is unavailable: $1" >&2
    exit 1
  fi
}

require_file() {
  if [[ ! -f "$1" ]]; then
    echo "required file is unavailable: $1" >&2
    exit 1
  fi
}

workspace_root="${PROJECT_ROOT:-$(git rev-parse --show-toplevel)}"
workspace_root="$(cd "${workspace_root}" && pwd -P)"
cd "${workspace_root}"

artifact_root_input="${ARTIFACT_ROOT:-${workspace_root}/artifacts}"
if [[ "${artifact_root_input}" != /* ]]; then
  artifact_root_input="${workspace_root}/${artifact_root_input}"
fi
mkdir -p "${artifact_root_input}"
artifact_boundary="$(cd "${artifact_root_input}" && pwd -P)"

artifact_input="${RS_ARTIFACT_ROOT:-${artifact_boundary}/rust}"
if [[ "${artifact_input}" != /* ]]; then
  artifact_input="${workspace_root}/${artifact_input}"
fi
mkdir -p "${artifact_input}"
rs_artifact_root="$(cd "${artifact_input}" && pwd -P)"
case "${rs_artifact_root}" in
  "${artifact_boundary}" | "${artifact_boundary}"/*) ;;
  *)
    echo "Rust artifacts must stay under ${artifact_boundary}: ${rs_artifact_root}" >&2
    exit 1
    ;;
esac

rs_run_id="${RS_RUN_ID:-${RUN_ID:-local}}"
if [[ ! "${rs_run_id}" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
  echo "RS_RUN_ID contains unsupported characters: ${rs_run_id}" >&2
  exit 2
fi

resolve_artifact_dir() {
  local configured_path="$1"
  local candidate="${configured_path}"
  if [[ "${candidate}" != /* ]]; then
    candidate="${workspace_root}/${candidate}"
  fi
  mkdir -p "${candidate}"
  candidate="$(cd "${candidate}" && pwd -P)"
  case "${candidate}" in
    "${artifact_boundary}" | "${artifact_boundary}"/*)
      printf '%s\n' "${candidate}"
      ;;
    *)
      echo "Rust gate path must stay under ${artifact_boundary}: ${candidate}" >&2
      exit 1
      ;;
  esac
}

rs_target_dir="$(resolve_artifact_dir "${RS_TARGET_DIR:-${rs_artifact_root}/target}")"
rs_cargo_home="$(resolve_artifact_dir "${RS_CARGO_HOME:-${rs_artifact_root}/cargo/home}")"
rs_tmp_dir="$(resolve_artifact_dir "${RS_TMP_DIR:-${rs_artifact_root}/tmp}")"
rs_nextest_cache_dir="$(resolve_artifact_dir "${RS_NEXTEST_CACHE_DIR:-${rs_target_dir}/nextest}")"
rs_nextest_config_home="$(resolve_artifact_dir "${RS_NEXTEST_CONFIG_HOME:-${rs_artifact_root}/nextest/config}")"
rs_profraw_dir="${rs_artifact_root}/coverage/profraw"
rs_coverage_dir="${rs_artifact_root}/coverage/${rs_run_id}"
rs_coverage_target_dir="$(resolve_artifact_dir "${rs_coverage_dir}/target")"

fmt_report="${rs_artifact_root}/fmt/${rs_run_id}/report.txt"
lint_report="${rs_artifact_root}/lint/${rs_run_id}/report.txt"
test_report="${rs_artifact_root}/test/${rs_run_id}/nextest.log"
test_slow_report="${rs_artifact_root}/test/${rs_run_id}/nextest-slow.log"
test_all_report="${rs_artifact_root}/test/${rs_run_id}/nextest-all.log"
audit_report="${rs_artifact_root}/audit/${rs_run_id}/report.txt"
coverage_test_report="${rs_coverage_dir}/nextest.log"
coverage_summary_report="${rs_coverage_dir}/summary.txt"
coverage_lcov_file="${rs_coverage_dir}/lcov.info"

mkdir -p \
  "${rs_target_dir}" \
  "${rs_cargo_home}" \
  "${rs_tmp_dir}" \
  "${rs_nextest_cache_dir}" \
  "${rs_nextest_config_home}" \
  "${rs_profraw_dir}" \
  "${rs_coverage_dir}"

export CARGO_HOME="${rs_cargo_home}"
export TMPDIR="${rs_tmp_dir}"
export TMP="${rs_tmp_dir}"
export TEMP="${rs_tmp_dir}"
export CARGO_TERM_COLOR="${CARGO_TERM_COLOR:-always}"
export CARGO_TERM_PROGRESS_WHEN="${CARGO_TERM_PROGRESS_WHEN:-always}"
export CARGO_TERM_PROGRESS_WIDTH="${CARGO_TERM_PROGRESS_WIDTH:-120}"
export CARGO_TERM_VERBOSE="${CARGO_TERM_VERBOSE:-false}"

require_tool cargo

locked_args=()
if [[ "${RUST_CARGO_LOCKED:-1}" == "1" ]]; then
  locked_args+=(--locked)
fi

run_logged() {
  local report_path="$1"
  shift
  mkdir -p "$(dirname "${report_path}")"
  set +e
  set -o pipefail
  "$@" 2>&1 | tee "${report_path}"
  local pipeline_status=("${PIPESTATUS[@]}")
  set -e
  if [[ "${pipeline_status[0]}" -ne 0 ]]; then
    return "${pipeline_status[0]}"
  fi
  return "${pipeline_status[1]}"
}

run_logged_append() {
  local report_path="$1"
  shift
  set +e
  set -o pipefail
  "$@" 2>&1 | tee -a "${report_path}"
  local pipeline_status=("${PIPESTATUS[@]}")
  set -e
  if [[ "${pipeline_status[0]}" -ne 0 ]]; then
    return "${pipeline_status[0]}"
  fi
  return "${pipeline_status[1]}"
}

nextest_expression() {
  local mode="$1"
  local configured="$2"
  if [[ -n "${configured}" ]]; then
    printf '%s\n' "${configured}"
  else
    "${NEXTEST_EXPR_BIN}" "${mode}"
  fi
}

run_nextest() {
  local mode="$1"
  local report_path="$2"
  local profile="$3"
  local target_dir="$4"
  local expression="$5"
  local ignored_mode="$6"
  local threads="$7"

  require_tool cargo-nextest
  require_file "${NEXTEST_CONFIG_FILE}"
  if [[ "${threads}" == "auto" ]]; then
    threads="num-cpus"
  fi

  args=(
    cargo nextest run
    --workspace
    --all-features
    "${locked_args[@]}"
    --config-file "${NEXTEST_CONFIG_FILE}"
    --profile "${profile}"
    --status-level "${NEXTEST_STATUS_LEVEL:-all}"
    --final-status-level "${NEXTEST_FINAL_STATUS_LEVEL:-all}"
    --target-dir "${target_dir}"
  )
  if [[ -n "${expression}" ]]; then
    args+=(-E "${expression}")
  fi
  if [[ "${ignored_mode}" == "all" ]]; then
    args+=(--run-ignored all --retries 0)
  fi
  if [[ -n "${threads}" ]]; then
    args+=(-j "${threads}")
  fi

  printf 'run: %s\n' "${args[*]}"
  local status=0
  if run_logged "${report_path}" env \
    CARGO_TARGET_DIR="${target_dir}" \
    NEXTEST_CACHE_DIR="${rs_nextest_cache_dir}" \
    XDG_CONFIG_HOME="${rs_nextest_config_home}" \
    LLVM_PROFILE_FILE="${rs_profraw_dir}/default_%m_%p.profraw" \
    "${args[@]}"; then
    status=0
  else
    status=$?
  fi

  local summary
  summary="$(perl -pe 's/\e\[[0-9;]*[[:alpha:]]//g' "${report_path}" | grep 'Summary \[' | tail -n 1 || true)"
  printf '\033[1;36m%s\033[0m %s\n' "nextest-summary:" "${summary:-unavailable}"
  printf 'nextest-mode: %s\n' "${mode}"
  return "${status}"
}

case "${command_name}" in
  format | fmt)
    args=(cargo fmt --all)
    if [[ "${command_name}" == "fmt" ]]; then
      args+=(-- --check)
    fi
    if [[ -n "${RUSTFMT_CONFIG:-}" ]]; then
      if [[ "${command_name}" == "format" ]]; then
        args+=(-- --config-path "${RUSTFMT_CONFIG}")
      else
        args+=(--config-path "${RUSTFMT_CONFIG}")
      fi
    fi
    printf 'run: %s\n' "${args[*]}"
    run_logged "${fmt_report}" env CARGO_TARGET_DIR="${rs_target_dir}" "${args[@]}"
    ;;
  lint)
    args=(cargo clippy --workspace --all-targets --all-features "${locked_args[@]}")
    if [[ -n "${RUST_CLIPPY_EXCLUDES:-}" ]]; then
      read -r -a excludes <<<"${RUST_CLIPPY_EXCLUDES}"
      for excluded_crate in "${excludes[@]}"; do
        args+=(--exclude "${excluded_crate}")
      done
    fi
    args+=(-- -D warnings)
    printf 'run: %s\n' "${args[*]}"
    run_logged "${lint_report}" env \
      CLIPPY_CONF_DIR="${RUST_CLIPPY_CONFIG_DIR:-${workspace_root}/configs/rust}" \
      CARGO_TARGET_DIR="${rs_target_dir}" \
      "${args[@]}"
    ;;
  test)
    expression="$(nextest_expression fast "${NEXTEST_FAST_EXPR:-}")"
    run_nextest \
      fast \
      "${test_report}" \
      "${NEXTEST_PROFILE_FAST:-default}" \
      "${rs_target_dir}" \
      "${expression}" \
      default \
      "${NEXTEST_THREADS:-}"
    ;;
  test-slow)
    expression="$(nextest_expression slow "${NEXTEST_SLOW_EXPR:-}")"
    run_nextest \
      slow \
      "${test_slow_report}" \
      "${NEXTEST_PROFILE_SLOW:-default}" \
      "${rs_target_dir}" \
      "${expression}" \
      default \
      "${NEXTEST_THREADS:-}"
    ;;
  test-all)
    run_nextest \
      all \
      "${test_all_report}" \
      "${NEXTEST_PROFILE_ALL:-default}" \
      "${rs_target_dir}" \
      "" \
      all \
      "${NEXTEST_THREADS_ALL:-8}"
    ;;
  audit)
    require_tool cargo-deny
    require_tool cargo-audit
    require_file "${RUST_DENY_CONFIG}"
    mkdir -p "$(dirname "${audit_report}")"
    : >"${audit_report}"
    deny_status=0
    audit_status=0
    if run_logged_append "${audit_report}" env CARGO_TARGET_DIR="${rs_target_dir}" \
      cargo deny check bans licenses sources --config "${RUST_DENY_CONFIG}"; then
      deny_status=0
    else
      deny_status=$?
    fi
    audit_args=(cargo audit)
    if [[ -n "${RUST_AUDIT_IGNORE_ARGS:-}" ]]; then
      read -r -a configured_audit_args <<<"${RUST_AUDIT_IGNORE_ARGS}"
      audit_args+=("${configured_audit_args[@]}")
    fi
    if run_logged_append "${audit_report}" env CARGO_TARGET_DIR="${rs_target_dir}" "${audit_args[@]}"; then
      audit_status=0
    else
      audit_status=$?
    fi
    if [[ "${deny_status}" -ne 0 || "${audit_status}" -ne 0 ]]; then
      echo "Rust audit failed: cargo-deny=${deny_status} cargo-audit=${audit_status}" >&2
      if [[ "${deny_status}" -ne 0 ]]; then
        exit "${deny_status}"
      fi
      exit "${audit_status}"
    fi
    ;;
  coverage)
    require_tool cargo-nextest
    require_tool cargo-llvm-cov
    require_file "${NEXTEST_CONFIG_FILE}"
    args=(
      cargo llvm-cov nextest
      --workspace
      --all-features
      "${locked_args[@]}"
      --run-ignored all
      --retries 0
      --config-file "${NEXTEST_CONFIG_FILE}"
      --profile "${NEXTEST_PROFILE_ALL:-default}"
      --status-level "${NEXTEST_STATUS_LEVEL:-all}"
      --final-status-level "${NEXTEST_FINAL_STATUS_LEVEL:-all}"
      --lcov
      --output-path "${coverage_lcov_file}"
    )
    if [[ -n "${NEXTEST_THREADS_ALL:-}" ]]; then
      args+=(-j "${NEXTEST_THREADS_ALL}")
    fi
    printf 'run: %s\n' "${args[*]}"
    run_logged "${coverage_test_report}" env \
      CARGO_TARGET_DIR="${rs_coverage_target_dir}" \
      CARGO_LLVM_COV_TARGET_DIR="${rs_coverage_target_dir}" \
      NEXTEST_CACHE_DIR="${rs_nextest_cache_dir}" \
      XDG_CONFIG_HOME="${rs_nextest_config_home}" \
      LLVM_PROFILE_FILE="${rs_profraw_dir}/default_%m_%p.profraw" \
      "${args[@]}"
    run_logged "${coverage_summary_report}" env \
      CARGO_TARGET_DIR="${rs_coverage_target_dir}" \
      CARGO_LLVM_COV_TARGET_DIR="${rs_coverage_target_dir}" \
      cargo llvm-cov report --summary-only
    printf 'coverage-lcov: %s\n' "${coverage_lcov_file}"
    printf 'coverage-report: %s\n' "${coverage_summary_report}"
    ;;
  rustdoc)
    rustdoc_flags="${RUSTDOCFLAGS:-}"
    if [[ "${RUSTDOC_DENY_WARNINGS:-1}" == "1" ]]; then
      rustdoc_flags="${rustdoc_flags} -D warnings"
    fi
    args=(cargo doc --workspace --no-deps "${locked_args[@]}")
    printf 'run: %s\n' "${args[*]}"
    run_logged "${rs_artifact_root}/rustdoc/${rs_run_id}/report.txt" env \
      CARGO_TARGET_DIR="${rs_target_dir}" \
      RUSTDOCFLAGS="${rustdoc_flags# }" \
      "${args[@]}"
    ;;
esac
