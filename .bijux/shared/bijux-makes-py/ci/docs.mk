DOCS_PUBLICATION_FRAMEWORK ?= 0
# Selection is exported data; only the canonical producer validates ownership.
DOCS_INTERACTIVE_REPORT_OWNER ?=
export DOCS_INTERACTIVE_REPORT_OWNER
DOCS_PUBLICATION_RENDERER ?= $(BIJUX_DOCS_SHARED_DIR)/security/render_publication.py
DOCS_PYTHON                  ?= $(if $(wildcard $(VENV_PYTHON)),$(VENV_PYTHON),python3.11)
DOCS_SITE_DIR                ?= $(PROJECT_ARTIFACTS_DIR)/docs/site
DOCS_BUILD_SITE_DIR          ?= $(DOCS_SITE_DIR)
DOCS_CHECK_SITE_DIR          ?= $(DOCS_SITE_DIR)
DOCS_SERVE_SITE_DIR          ?= $(DOCS_SITE_DIR)
DOCS_CACHE_DIR               ?= $(PROJECT_ARTIFACTS_DIR)/docs/.cache
DOCS_SOURCE_DIR              ?= $(PROJECT_ARTIFACTS_DIR)/docs/source
DOCS_EFFECTIVE_CONFIG        ?= $(PROJECT_ARTIFACTS_DIR)/docs/mkdocs.generated.yml
DOCS_BUILD_CONFIG_FILE       ?= $(DOCS_EFFECTIVE_CONFIG)
DOCS_CHECK_CONFIG_FILE       ?= $(DOCS_EFFECTIVE_CONFIG)
DOCS_SERVE_CONFIG_FILE       ?= $(DOCS_EFFECTIVE_CONFIG)
DOCS_SHARED_ASSETS_DIR       ?= $(PROJECT_DIR)/docs/assets
DOCS_DEV_ADDR                ?= 127.0.0.1:8001
DOCS_SITE_URL                ?= $(SITE_URL)
DOCS_BUILD_SITE_URL          ?= $(DOCS_SITE_URL)
DOCS_CHECK_SITE_URL          ?= $(DOCS_SITE_URL)
DOCS_SERVE_SITE_URL          ?= $(DOCS_SITE_URL)
DOCS_BUILD_FLAGS             ?= --strict
DOCS_SERVE_FLAGS             ?=
DOCS_DEPLOY_FLAGS            ?= --force
DOCS_ENABLE_SOCIAL_CARDS     ?= false
DOCS_EXTRA_CLEAN_PATHS       ?=
DOCS_HYGIENE_FORBID_ROOT     ?= site .cache
DOCS_BUILD_BOOTSTRAP_TARGETS ?=
DOCS_CHECK_BOOTSTRAP_TARGETS ?=
DOCS_SERVE_BOOTSTRAP_TARGETS ?=
DOCS_BUILD_PREPARE_TARGETS   ?= docs-prepare-source
DOCS_CHECK_PREPARE_TARGETS   ?= docs-prepare-source
DOCS_SERVE_PREPARE_TARGETS   ?= docs-prepare-source
DOCS_BUILD_GUARD_TARGETS     ?=
DOCS_CHECK_GUARD_TARGETS     ?=
DOCS_SERVE_GUARD_TARGETS     ?=
DOCS_BUILD_PRE_CLEAN_PATHS   ?=
DOCS_CHECK_PRE_CLEAN_PATHS   ?=
DOCS_SERVE_PRE_CLEAN_PATHS   ?=
DOCS_BUILD_ENV               ?=
DOCS_CHECK_ENV               ?=
DOCS_SERVE_ENV               ?=
DOCS_SERVE_REUSE_MATCH       ?= $(if $(filter 1,$(DOCS_RENDER_SERVE_CONFIG)),$(DOCS_SERVE_CONFIG_FILE),$(DOCS_BASE_CONFIG_FILE))
DOCS_SERVE_STATUS_FILE       ?= $(DOCS_CACHE_DIR)/.serve-state
DOCS_SERVE_LOCK_DIR          ?= $(DOCS_CACHE_DIR)/.serve-lock
DOCS_RENDER_SERVE_CONFIG     ?= 0
DOCS_BASE_CONFIG_FILE        ?= $(MKDOCS_CFG)
DOCS_SHARED_CONFIG_FILE      ?=
DOCS_RENDERED_DOCS_DIR       ?= $(PROJECT_DIR)/docs
DOCS_CONFIG_CLI              ?=
DOCS_MATERIAL_COMPILER       ?= $(PROJECT_DIR)/.bijux/shared/bijux-docs/tooling/material/build_runtime.py

DOCS_SOURCE_VERIFIER ?= $(PROJECT_DIR)/.bijux/shared/bijux-docs/tooling/scripts/verify_bijux_docs_site.sh

define assert_docs_interactive_report_dispatch
	@if [ -n "$$DOCS_INTERACTIVE_REPORT_OWNER" ]; then \
	  test "$(1)" != "serve" || { echo "ERROR: interactive reports require source-owned docs or docs-check" >&2; exit 1; }; \
	  test "$(DOCS_PUBLICATION_FRAMEWORK)" = "1" || { echo "ERROR: interactive report selection requires DOCS_PUBLICATION_FRAMEWORK=1" >&2; exit 1; }; \
	fi
endef

# Refuse source selection before consumer cleanup or preparation can erase an
# existing site. The actual producer independently repeats this source check.
define assert_docs_report_source
	@if [ "$(DOCS_PUBLICATION_FRAMEWORK)" = "1" ]; then \
	  set --; \
	  if [ -n "$$DOCS_INTERACTIVE_REPORT_OWNER" ]; then set -- --interactive-report-owner "$$DOCS_INTERACTIVE_REPORT_OWNER"; fi; \
	  $(DOCS_ENV) $(1) ENABLE_SOCIAL_CARDS="$(DOCS_ENABLE_SOCIAL_CARDS)" env -u SITE_URL $(if $(strip $(2)),SITE_URL="$(2)") "$(DOCS_PYTHON)" "$(DOCS_PUBLICATION_RENDERER)" --preflight --config "$(patsubst $(PROJECT_DIR)/%,%,$(3))" --site-dir "$(patsubst $(PROJECT_DIR)/%,%,$(4))" --site-url "$(2)" "$$@"; \
	fi
endef

define assert_docs_source_authority
	@test -f "$(DOCS_SOURCE_VERIFIER)" || { echo "ERROR: missing accepted documentation source verifier" >&2; exit 1; }
	@DOCS_PYTHON="$(DOCS_PYTHON)" bash "$(DOCS_SOURCE_VERIFIER)" --source-only
endef

# The same interpreter that renders CSS/templates/worker must admit the owned runtime.
define assert_docs_material_runtime
	@test -f "$(DOCS_MATERIAL_COMPILER)" || { echo "ERROR: missing accepted Material runtime compiler: $(DOCS_MATERIAL_COMPILER)" >&2; exit 1; }
	@PYTHONDONTWRITEBYTECODE=1 $(DOCS_ENV) $(1) "$(DOCS_PYTHON)" "$(DOCS_MATERIAL_COMPILER)" --check
endef

ifeq ($(shell uname -s),Darwin)
  DOCS_BREW_PREFIX   := $(shell command -v brew >/dev/null 2>&1 && brew --prefix)
  DOCS_LIBFFI_PREFIX := $(shell test -n "$(DOCS_BREW_PREFIX)" && brew --prefix libffi)
  DOCS_ENV           := DYLD_FALLBACK_LIBRARY_PATH="$(DOCS_BREW_PREFIX)/lib:$(DOCS_LIBFFI_PREFIX)/lib:$$DYLD_FALLBACK_LIBRARY_PATH"
else
  DOCS_ENV           :=
endif

DOCS_GOALS := $(filter docs docs-serve docs-deploy docs-check,$(MAKECMDGOALS))
ifneq ($(strip $(DOCS_GOALS)),)
  ifeq ($(wildcard $(MKDOCS_CFG)),)
    $(error mkdocs config '$(MKDOCS_CFG)' not found)
  endif
endif

include $(abspath $(dir $(lastword $(MAKEFILE_LIST))))/util.mk

.PHONY: docs docs-serve docs-serve-run docs-deploy docs-check docs-clean docs-hygiene docs-prepare-source docs-assert-serve-port docs-render-serve-config docs-assert-public-url

docs:
	$(call assert_docs_interactive_report_dispatch,build)
	@if [ "$(DOCS_PUBLICATION_FRAMEWORK)" = "1" ]; then test "$(strip $(DOCS_BUILD_FLAGS))" = "--strict" || { echo "ERROR: publication producer requires exact --strict render flags" >&2; exit 1; }; fi
	@$(MAKE) docs-assert-public-url
	$(call run_make_targets,$(DOCS_BUILD_BOOTSTRAP_TARGETS),$(MAKE))
	$(call run_make_targets,$(DOCS_BUILD_GUARD_TARGETS),$(MAKE))
	$(call assert_docs_source_authority)
	$(call assert_docs_material_runtime,$(DOCS_BUILD_ENV))
	$(call assert_docs_report_source,$(DOCS_BUILD_ENV),$(DOCS_BUILD_SITE_URL),$(DOCS_BUILD_CONFIG_FILE),$(DOCS_BUILD_SITE_DIR))
	$(call clean_paths,$(DOCS_BUILD_PRE_CLEAN_PATHS))
	$(call run_make_targets,$(DOCS_BUILD_PREPARE_TARGETS),$(MAKE))
	@echo "→ Building documentation"
	@mkdir -p "$(DOCS_CACHE_DIR)"
	@if [ "$(DOCS_PUBLICATION_FRAMEWORK)" = "1" ]; then \
	    set --; \
	    if [ -n "$$DOCS_INTERACTIVE_REPORT_OWNER" ]; then set -- --interactive-report-owner "$$DOCS_INTERACTIVE_REPORT_OWNER"; fi; \
	    XDG_CACHE_HOME="$(DOCS_CACHE_DIR)" $(DOCS_ENV) $(DOCS_BUILD_ENV) ENABLE_SOCIAL_CARDS="$(DOCS_ENABLE_SOCIAL_CARDS)" env -u SITE_URL $(if $(strip $(DOCS_BUILD_SITE_URL)),SITE_URL="$(DOCS_BUILD_SITE_URL)") "$(DOCS_PYTHON)" "$(DOCS_PUBLICATION_RENDERER)" --config "$(patsubst $(PROJECT_DIR)/%,%,$(DOCS_BUILD_CONFIG_FILE))" --site-dir "$(patsubst $(PROJECT_DIR)/%,%,$(DOCS_BUILD_SITE_DIR))" --site-url "$(DOCS_BUILD_SITE_URL)" "$$@"; \
	  else XDG_CACHE_HOME="$(DOCS_CACHE_DIR)" $(DOCS_ENV) $(DOCS_BUILD_ENV) ENABLE_SOCIAL_CARDS="$(DOCS_ENABLE_SOCIAL_CARDS)" env -u SITE_URL $(if $(strip $(DOCS_BUILD_SITE_URL)),SITE_URL="$(DOCS_BUILD_SITE_URL)") "$(DOCS_PYTHON)" -m mkdocs build $(DOCS_BUILD_FLAGS) --config-file "$(DOCS_BUILD_CONFIG_FILE)" --site-dir "$(DOCS_BUILD_SITE_DIR)"; fi
	@$(MAKE) docs-hygiene
	@echo "✔ Docs built → $(DOCS_BUILD_SITE_DIR)"

docs-serve:
	$(call assert_docs_interactive_report_dispatch,serve)
	@mkdir -p "$(DOCS_CACHE_DIR)"; \
	status_file="$(DOCS_SERVE_STATUS_FILE)"; \
	lock_dir="$(DOCS_SERVE_LOCK_DIR)"; \
	set -eu; \
	acquire_lock() { \
	  mkdir "$$lock_dir" 2>/dev/null; \
	}; \
	if ! acquire_lock; then \
	  echo "→ Documentation serve is already starting or running"; \
	  exit 0; \
	fi; \
	trap 'rm -f "$$status_file"; rm -rf "$$lock_dir"' EXIT INT TERM; \
	rm -f "$$status_file"; \
	if [ -n "$(strip $(DOCS_SERVE_GUARD_TARGETS))" ]; then \
	  $(MAKE) $(DOCS_SERVE_GUARD_TARGETS); \
	  if [ "$$(cat "$(DOCS_SERVE_STATUS_FILE)" 2>/dev/null || true)" = "reuse" ]; then \
	    exit 0; \
	  fi; \
	fi; \
	$(MAKE) docs-serve-run

docs-serve-run:
	$(call assert_docs_interactive_report_dispatch,serve)
	$(call run_make_targets,$(DOCS_SERVE_BOOTSTRAP_TARGETS),$(MAKE))
	$(call assert_docs_source_authority)
	$(call assert_docs_material_runtime,$(DOCS_SERVE_ENV))
	$(call clean_paths,$(DOCS_SERVE_PRE_CLEAN_PATHS))
	$(call run_make_targets,$(DOCS_SERVE_PREPARE_TARGETS),$(MAKE))
	@echo "→ Serving documentation on http://$(DOCS_DEV_ADDR)/"
	@config_file="$(DOCS_SERVE_CONFIG_FILE)"; \
	if [ "$(DOCS_RENDER_SERVE_CONFIG)" != "1" ]; then \
	  config_file="$(DOCS_BASE_CONFIG_FILE)"; \
	fi; \
	exec env XDG_CACHE_HOME="$(DOCS_CACHE_DIR)" $(DOCS_ENV) $(DOCS_SERVE_ENV) SITE_URL="$(DOCS_SERVE_SITE_URL)" \
	  "$(DOCS_PYTHON)" -m mkdocs serve $(DOCS_SERVE_FLAGS) --config-file "$$config_file" --dev-addr "$(DOCS_DEV_ADDR)"

docs-deploy:
	@echo "ERROR: publish the exact qualified artifact through the reviewed GitHub Pages workflow; see PRODUCTION-VERIFICATION.md" >&2
	@exit 1

docs-check:
	$(call assert_docs_interactive_report_dispatch,check)
	@if [ "$(DOCS_PUBLICATION_FRAMEWORK)" = "1" ]; then test "$(strip $(DOCS_BUILD_FLAGS))" = "--strict" || { echo "ERROR: publication producer requires exact --strict render flags" >&2; exit 1; }; fi
	@$(MAKE) docs-assert-public-url
	$(call run_make_targets,$(DOCS_CHECK_BOOTSTRAP_TARGETS),$(MAKE))
	$(call run_make_targets,$(DOCS_CHECK_GUARD_TARGETS),$(MAKE))
	$(call assert_docs_source_authority)
	$(call assert_docs_material_runtime,$(DOCS_CHECK_ENV))
	$(call assert_docs_report_source,$(DOCS_CHECK_ENV),$(DOCS_CHECK_SITE_URL),$(DOCS_CHECK_CONFIG_FILE),$(DOCS_CHECK_SITE_DIR))
	$(call clean_paths,$(DOCS_CHECK_PRE_CLEAN_PATHS))
	$(call run_make_targets,$(DOCS_CHECK_PREPARE_TARGETS),$(MAKE))
	@echo "→ Checking documentation build integrity"
	@mkdir -p "$(DOCS_CACHE_DIR)"
	@if [ "$(DOCS_PUBLICATION_FRAMEWORK)" = "1" ]; then \
	    set --; \
	    if [ -n "$$DOCS_INTERACTIVE_REPORT_OWNER" ]; then set -- --interactive-report-owner "$$DOCS_INTERACTIVE_REPORT_OWNER"; fi; \
	    XDG_CACHE_HOME="$(DOCS_CACHE_DIR)" $(DOCS_ENV) $(DOCS_CHECK_ENV) ENABLE_SOCIAL_CARDS="$(DOCS_ENABLE_SOCIAL_CARDS)" env -u SITE_URL $(if $(strip $(DOCS_CHECK_SITE_URL)),SITE_URL="$(DOCS_CHECK_SITE_URL)") "$(DOCS_PYTHON)" "$(DOCS_PUBLICATION_RENDERER)" --config "$(patsubst $(PROJECT_DIR)/%,%,$(DOCS_CHECK_CONFIG_FILE))" --site-dir "$(patsubst $(PROJECT_DIR)/%,%,$(DOCS_CHECK_SITE_DIR))" --site-url "$(DOCS_CHECK_SITE_URL)" "$$@"; \
	  else XDG_CACHE_HOME="$(DOCS_CACHE_DIR)" $(DOCS_ENV) $(DOCS_CHECK_ENV) ENABLE_SOCIAL_CARDS="$(DOCS_ENABLE_SOCIAL_CARDS)" env -u SITE_URL $(if $(strip $(DOCS_CHECK_SITE_URL)),SITE_URL="$(DOCS_CHECK_SITE_URL)") "$(DOCS_PYTHON)" -m mkdocs build $(DOCS_BUILD_FLAGS) --quiet --config-file "$(DOCS_CHECK_CONFIG_FILE)" --site-dir "$(DOCS_CHECK_SITE_DIR)"; fi
	@$(MAKE) docs-hygiene
	@echo "✔ Docs check passed"

docs-prepare-source:
	@echo "→ Preparing documentation source tree"
	@mkdir -p "$(DOCS_SOURCE_DIR)" "$(dir $(DOCS_EFFECTIVE_CONFIG))"
	@rm -rf "$(DOCS_SOURCE_DIR)"
	@mkdir -p "$(DOCS_SOURCE_DIR)"
	@rsync -a --delete "$(PROJECT_DIR)/docs/" "$(DOCS_SOURCE_DIR)/"
	@if [ -d "$(DOCS_SHARED_ASSETS_DIR)" ] && [ "$(abspath $(DOCS_SHARED_ASSETS_DIR))" != "$(abspath $(DOCS_SOURCE_DIR)/assets)" ]; then \
	  mkdir -p "$(DOCS_SOURCE_DIR)/assets"; \
	  rsync -a --delete "$(DOCS_SHARED_ASSETS_DIR)/" "$(DOCS_SOURCE_DIR)/assets/"; \
	fi
	@if [ -n "$(strip $(DOCS_CONFIG_CLI))" ]; then \
	  "$(DOCS_PYTHON)" $(DOCS_CONFIG_CLI) prepare-source \
	    --source-config "$(MKDOCS_CFG)" \
	    --output-config "$(DOCS_EFFECTIVE_CONFIG)" \
	    --docs-source-dir "$(DOCS_SOURCE_DIR)"; \
	else \
	  cp "$(MKDOCS_CFG)" "$(DOCS_EFFECTIVE_CONFIG)"; \
	fi

docs-clean:
	@echo "→ Cleaning documentation artifacts"
	@rm -rf \
	  "$(DOCS_SITE_DIR)" \
	  "$(DOCS_BUILD_SITE_DIR)" \
	  "$(DOCS_CHECK_SITE_DIR)" \
	  "$(DOCS_SERVE_SITE_DIR)" \
	  "$(DOCS_CACHE_DIR)" \
	  "$(DOCS_SOURCE_DIR)" \
	  "$(DOCS_EFFECTIVE_CONFIG)" \
	  $(DOCS_EXTRA_CLEAN_PATHS)

docs-hygiene:
	@set -e; \
	for path in $(DOCS_HYGIENE_FORBID_ROOT); do \
	  test ! -e "$$path" || { echo "ERROR: root '$$path' is forbidden"; exit 1; }; \
	done
	@echo "Docs hygiene OK"

docs-assert-serve-port:
	@set -eu; \
	status_file="$(DOCS_SERVE_STATUS_FILE)"; \
	rm -f "$$status_file"; \
	addr="$(DOCS_DEV_ADDR)"; \
	port="$${addr##*:}"; \
	if lsof_output="$$(lsof -nP -iTCP:$$port -sTCP:LISTEN 2>/dev/null)"; then \
	  pid="$$(printf '%s\n' "$$lsof_output" | awk 'NR==2 {print $$2}')"; \
	  command_line="$$(ps -p "$$pid" -o command= 2>/dev/null || true)"; \
	  if [ -n "$(DOCS_SERVE_REUSE_MATCH)" ] && printf '%s\n' "$$command_line" | grep -Fq -- "$(DOCS_SERVE_REUSE_MATCH)"; then \
	    echo "→ Documentation already serving on http://$$addr (pid $$pid)"; \
	    echo reuse > "$$status_file"; \
	    exit 0; \
	  fi; \
	  echo "Port $$addr is already in use by pid $$pid."; \
	  if [ -n "$$command_line" ]; then \
	    echo "$$command_line"; \
	  fi; \
	  echo "Stop that process or set DOCS_DEV_ADDR to a free port."; \
	  exit 2; \
	fi

docs-render-serve-config:
	@if [ "$(DOCS_RENDER_SERVE_CONFIG)" != "1" ]; then \
	  echo "→ Serve config rendering is not enabled for this docs profile"; \
	else \
	  if [ -z "$(strip $(DOCS_CONFIG_CLI))" ]; then \
	    echo "✘ DOCS_CONFIG_CLI is required when DOCS_RENDER_SERVE_CONFIG=1"; \
	    exit 2; \
	  fi; \
	  mkdir -p "$(dir $(DOCS_SERVE_CONFIG_FILE))"; \
	  "$(DOCS_PYTHON)" $(DOCS_CONFIG_CLI) render-serve-config \
	    --source-config "$(DOCS_BASE_CONFIG_FILE)" \
	    --output-config "$(DOCS_SERVE_CONFIG_FILE)" \
	    --docs-dir "$(DOCS_RENDERED_DOCS_DIR)" \
	    --site-dir "$(DOCS_SERVE_SITE_DIR)" \
	    --site-url "$(DOCS_SERVE_SITE_URL)" \
	    $(if $(strip $(DOCS_SHARED_CONFIG_FILE)),--inherit-config "$(DOCS_SHARED_CONFIG_FILE)"); \
	fi

##@ Docs
docs:         ## Build the documentation site
docs-serve:   ## Serve docs locally from DOCS_DEV_ADDR
docs-deploy:  ## Explain the reviewed artifact publication boundary
docs-check:   ## Validate docs build without persisting root pollution
docs-clean:   ## Remove generated docs artifacts
docs-hygiene: ## Fail if forbidden root docs outputs exist

ifeq ($(strip $(DOCS_PUBLICATION_FRAMEWORK)),1)
  ifeq ($(strip $(BIJUX_DOCS_SHARED_DIR)),)
    $(error BIJUX_DOCS_SHARED_DIR must identify the accepted shared documentation source for publication qualification)
  endif
endif

# An empty override leaves the canonical default with the authored MkDocs config.
DOCS_PUBLIC_URL_VALIDATOR ?= $(firstword $(wildcard $(PROJECT_DIR)/.bijux/shared/bijux-docs/tooling/quality/validate_production_url.py $(PROJECT_DIR)/shared/bijux-docs/tooling/quality/validate_production_url.py))
docs-assert-public-url:
	@test -n "$(DOCS_PUBLIC_URL_VALIDATOR)" -a -f "$(DOCS_PUBLIC_URL_VALIDATOR)" || { echo "ERROR: canonical production URL validator is unavailable" >&2; exit 1; }
	@PYTHONDONTWRITEBYTECODE=1 "$(DOCS_PYTHON)" "$(DOCS_PUBLIC_URL_VALIDATOR)" --allow-empty "$(DOCS_BUILD_SITE_URL)" "$(DOCS_CHECK_SITE_URL)"
