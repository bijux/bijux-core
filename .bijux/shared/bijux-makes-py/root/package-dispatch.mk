ROOT_SHARED_CHECK_OVERRIDES := \
	VENV="$(abspath $(ROOT_CHECK_VENV))" \
	VENV_PYTHON="$(abspath $(ROOT_CHECK_PYTHON))" \
	PYTHON="$(abspath $(ROOT_CHECK_PYTHON))" \
	ACT="$(abspath $(ROOT_CHECK_VENV))/bin"

define ROOT_PACKAGE_CONTEXT_OVERRIDES
MONOREPO_ROOT="$(abspath $(MONOREPO_ROOT))" \
ROOT_MAKE_DIR="$(abspath $(ROOT_MAKE_DIR))" \
CONFIG_DIR="$(abspath $(CONFIG_DIR))" \
PROJECT_DIR="$(abspath $(MONOREPO_ROOT))/packages/$(1)" \
PROJECT_ARTIFACTS_DIR="$(abspath $(MONOREPO_ROOT))/artifacts/$(1)" \
PYTHONPYCACHEPREFIX="$(abspath $(MONOREPO_ROOT))/artifacts/$(1)/pycache" \
XDG_CACHE_HOME="$(abspath $(MONOREPO_ROOT))/artifacts/$(1)/xdg_cache" \
HYPOTHESIS_STORAGE_DIRECTORY="$(abspath $(MONOREPO_ROOT))/artifacts/$(1)/hypothesis" \
COVERAGE_FILE="$(abspath $(MONOREPO_ROOT))/artifacts/$(1)/test/.coverage" \
UV_CACHE_DIR="$(abspath $(MONOREPO_ROOT))/artifacts/$(1)/uv_cache" \
PIP_CACHE_DIR="$(abspath $(MONOREPO_ROOT))/artifacts/$(1)/pip_cache" \
NPM_CONFIG_CACHE="$(abspath $(MONOREPO_ROOT))/artifacts/$(1)/npm_cache" \
TMPDIR="$(abspath $(MONOREPO_ROOT))/artifacts/$(1)/process" \
API_DIR="$(abspath $(MONOREPO_ROOT))/apis/$(1)"
endef

define run_root_package_target
	@set -eu; \
	resolved_package="$(call resolve_package,$(PACKAGE))"; \
	if [ -n "$$resolved_package" ]; then \
	  package_list="$$resolved_package"; \
	else \
	  package_list="$(2)"; \
	fi; \
	mkdir -p "$(ROOT_ARTIFACTS_DIR)"; \
	cleanup() { $(MAKE) clean-root-artifacts >/dev/null; }; \
	trap cleanup EXIT; \
	if [ "$(3)" = "1" ]; then \
	  $(MAKE) root-check-env >/dev/null; \
	fi; \
	failures=""; \
	for package in $$package_list; do \
	  profile_path="$$(printf '%s\n' $(PACKAGE_PROFILE_MAPPINGS) | awk -F= -v pkg="$$package" '$$1 == pkg { print $$2 }')"; \
	  if [ -z "$$profile_path" ]; then \
	    profile_path="$(PACKAGE_MAKE_DIR)/$$package.mk"; \
	  fi; \
	  if [ ! -f "$$profile_path" ]; then \
	    echo "Missing package profile: $$profile_path"; \
	    failures="$$failures $$package"; \
	    continue; \
	  fi; \
	  echo "==> $$package: $(1)"; \
	  if [ "$(3)" = "1" ]; then \
	    if ! $(MAKE) -C "packages/$$package" -f "$$profile_path" \
	      PROJECT_SLUG="$$package" \
	      $(call ROOT_PACKAGE_CONTEXT_OVERRIDES,$$package) \
	      $(ROOT_SHARED_CHECK_OVERRIDES) \
	      $(1); then \
	      failures="$$failures $$package"; \
	    fi; \
	  elif ! $(MAKE) -C "packages/$$package" -f "$$profile_path" \
	    PROJECT_SLUG="$$package" \
	    $(call ROOT_PACKAGE_CONTEXT_OVERRIDES,$$package) \
	    $(1); then \
	    failures="$$failures $$package"; \
	  fi; \
	done; \
	if [ -n "$$failures" ]; then \
	  echo; \
	  echo "Packages with $(1) failures:$$failures"; \
	  exit 2; \
	fi
endef

define define_root_package_target
$(1):
	$$(call assert_package)
	$$(call run_root_package_target,$(1),$$(ROOT_TARGET_PACKAGES_$(1)),$$(ROOT_TARGET_SHARED_ENV_$(1)))
	$$(ROOT_TARGET_POST_$(1))
endef

$(foreach target,$(ROOT_PACKAGE_TARGETS),$(eval $(call define_root_package_target,$(target))))

##@ Orchestration
test: ## Run primary package tests package by package
lint: ## Run repository lint checks package by package with the shared check environment
quality: ## Run repository quality checks package by package with the shared check environment
security: ## Run repository security checks package by package with the shared check environment
api: ## Run primary package API checks package by package
build: ## Build primary package artifacts package by package
sbom: ## Generate primary package SBOMs package by package
clean: ## Clean package artifacts across the repository
