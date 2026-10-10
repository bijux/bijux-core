#!/usr/bin/env bash
# Qualify the exact production artifact with independently verified shared source.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
repo_root="$(git rev-parse --show-toplevel)"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
shared_root="$(cd "${script_dir}/../.." && pwd)"
python_bin="${DOCS_PYTHON:-python3}"
# shellcheck source=shared/bijux-docs/tooling/scripts/docs_source_authority.sh
source "${script_dir}/docs_source_authority.sh"
if [[ "${1:-}" == '--source-only' ]]; then
  verify_docs_authority "${repo_root}" "${shared_root}"
  exit 0
fi
[[ "$#" == '0' ]] || { echo 'ERROR: configure DOCS_SITE_DIR and SITE_URL; unexpected verifier arguments' >&2; exit 1; }
[[ -n "${DOCS_SITE_DIR:-}" ]] || { echo 'ERROR: DOCS_SITE_DIR must select one exact production artifact; no discovery fallback' >&2; exit 1; }
report="${BIJUX_DOCS_SITE_REPORT:-artifacts/website-security/site-verification.json}"
"${python_bin}" - "${repo_root}" "${DOCS_SITE_DIR}" "${report}" <<'PY_START'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve();site=(root/sys.argv[2]).resolve();report=(root/sys.argv[3]).resolve()
if not site.is_relative_to(root/'artifacts') or not report.is_relative_to(root/'artifacts') or report.is_relative_to(site):
    raise SystemExit('ERROR: select root artifacts/ output and a report outside the published bundle')
report.parent.mkdir(parents=True,exist_ok=True)
report.write_text(json.dumps(dict(schema=1,passed=False,result='fail',verification_only=True,
    scope=['PUBLIC-ROUTES','SEARCH-DELIVERY','PRODUCTION-URLS'],checks=[],
    errors=['Source and artifact verification have not completed']))+'\n')
PY_START
phase='source_before'
record_failure() {
  local status="$?"
  if [[ "${status}" != '0' ]]; then
    "${python_bin}" - "${repo_root}" "${report}" "${phase}" <<'PY_FAILURE'
import json,sys
from pathlib import Path
path=Path(sys.argv[1])/sys.argv[2];record=json.loads(path.read_text())
record.update(passed=False,result='fail',failure_stage=sys.argv[3])
path.write_text(json.dumps(record,indent=2)+'\n')
PY_FAILURE
  fi
}
trap record_failure EXIT
verify_docs_authority "${repo_root}" "${shared_root}"
phase='source_projection'
"${python_bin}" "${script_dir}/project_bijux_docs.py" "${repo_root}" "${shared_root}" --check
phase='artifact_routes_search'
site_url="${DOCS_BUILD_SITE_URL:-${SITE_URL:-}}"
if [[ -z "${site_url}" ]]; then
  site_url="$("${python_bin}" - "${DOCS_CONFIG_FILE:-${repo_root}/mkdocs.yml}" <<'PY_URL'
import sys
from mkdocs.config import load_config
print(load_config(config_file=sys.argv[1]).site_url or '')
PY_URL
)"
fi
args=(--repo-root "${repo_root}" --site-dir "${DOCS_SITE_DIR}" --site-url "${site_url}" --output "${report}")
if [[ -n "${BIJUX_DOCS_DEVELOPMENT_LINK_POLICY:-}" ]]; then
  args+=(--development-link-policy "${BIJUX_DOCS_DEVELOPMENT_LINK_POLICY}")
fi
if [[ -n "${BIJUX_DOCS_READER_OWNER:-}" ]]; then
  [[ -n "${BIJUX_DOCS_READER_SOURCE_SHA:-}" ]] || { echo 'ERROR: reader verifier requires exact committed source SHA' >&2; exit 1; }
  args+=(--embedded-csp-report artifacts/website-security/csp.json
         --completed-build-receipt artifacts/website-security/build-identity.json
         --source-sha "${BIJUX_DOCS_READER_SOURCE_SHA}" --reader-owner "${BIJUX_DOCS_READER_OWNER}")
  if [[ -n "${DOCS_SOURCE_IDENTITY:-}" ]]; then args+=(--source-identity "${DOCS_SOURCE_IDENTITY}"); fi
fi
"${python_bin}" "${shared_root}/tooling/quality/validate_site_routes.py" "${args[@]}"
phase='source_after'
verify_docs_authority "${repo_root}" "${shared_root}"
"${python_bin}" - "${repo_root}" "${report}" <<'PY_SOURCE'
import json,os,subprocess,sys
from pathlib import Path
root=Path(sys.argv[1]);path=root/sys.argv[2];report=json.loads(path.read_text())
source=os.environ.get('BIJUX_STD_ROOT')
candidate=os.environ.get('BIJUX_STD_LOCAL_VERIFY')=='1' or os.environ.get('BIJUX_STD_ALLOW_LOCAL_SOURCE')=='1'
report['verification_only'] = report['verification_only'] or candidate or not bool(os.environ.get('DOCS_SOURCE_IDENTITY'))
report['source_checks']={'before':True,'after':True,'mode':'local_candidate' if candidate else 'exact_fetched',
    'standard_sha':subprocess.check_output(['git','-C',source,'rev-parse','HEAD'],text=True).strip() if source and not candidate else None,
    'origin':subprocess.check_output(['git','-C',source,'remote','get-url','origin'],text=True).strip() if source and not candidate else None}
path.write_text(json.dumps(report,indent=2)+'\n')
PY_SOURCE
