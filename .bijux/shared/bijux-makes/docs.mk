# A generated ownership record identifies a managed Bijux shell. Generic docs
# callers choose their native capability explicitly instead of bypassing admission.
DOCS_CONFIG ?= mkdocs.yml
override DOCS_PROJECTION_RECORD := $(PROJECT_ROOT)/.bijux/docs-projection.json
override DOCS_CONFIG_PROJECTION_RECORD := $(abspath $(dir $(DOCS_CONFIG)))/.bijux/docs-projection.json
DOCS_RENDERER_PROFILE ?= $(if $(wildcard $(DOCS_PROJECTION_RECORD) $(DOCS_CONFIG_PROJECTION_RECORD)),bijux-material,unconfigured)
DOCS_PYTHON_RUN ?= python3
DOCS_MATERIAL_COMPILER ?= $(BIJUX_MAKES_SHARED_ROOT)/bijux-docs/tooling/material/build_runtime.py
ifeq ($(DOCS_RENDERER_PROFILE),bijux-material)
DOCS_RUN ?= $(DOCS_PYTHON_RUN) -m mkdocs
else
DOCS_RUN ?= mkdocs
endif
DOCS_SITE_DIR ?= $(ARTIFACT_ROOT_ABS)/docs/site
DOCS_CHECK_SITE_DIR ?= $(ARTIFACT_ROOT_ABS)/docs/check-site
DOCS_CACHE_DIR ?= $(ARTIFACT_ROOT_ABS)/docs/cache
DOCS_PYCACHE_DIR ?= $(ARTIFACT_ROOT_ABS)/docs/pycache
DOCS_DEV_ADDR ?= 127.0.0.1:8000
DOCS_SITE_URL ?=
DOCS_BUILD_FLAGS ?= --strict
DOCS_CHECK_FLAGS ?= --strict --quiet
DOCS_SERVE_FLAGS ?=
DOCS_PREPARE_TARGETS ?=
DOCS_SOURCE_CHECK_TARGETS ?=
DOCS_HYGIENE_FORBIDDEN_PATHS ?= site .cache

BIJUX_CI_PR_TARGETS += docs-check
BIJUX_CI_DOCS_TARGETS += docs-check
BIJUX_HELP_TARGETS += docs docs-check docs-clean docs-hygiene docs-require docs-serve
BIJUX_HELP_docs := Build strict documentation under artifacts
BIJUX_HELP_docs-check := Validate a strict documentation build
BIJUX_HELP_docs-clean := Remove documentation artifacts
BIJUX_HELP_docs-hygiene := Reject documentation output outside artifacts
BIJUX_HELP_docs-require := Verify documentation inputs and tools
BIJUX_HELP_docs-serve := Serve documentation in the foreground

.PHONY: docs docs-check docs-clean docs-hygiene docs-require docs-serve

docs-require: ## Verify documentation inputs and the actual renderer before preparation
	@case "$(DOCS_RENDERER_PROFILE)" in native|bijux-material) ;; *) echo "$(BIJUX_MAKES_DIR)/docs.mk: DOCS_RENDERER_PROFILE must explicitly select native or bijux-material (received $(DOCS_RENDERER_PROFILE))" >&2; exit 1 ;; esac
	@if [ "$(DOCS_RENDERER_PROFILE)" = native ]; then \
		for record in "$(DOCS_PROJECTION_RECORD)" "$(DOCS_CONFIG_PROJECTION_RECORD)"; do \
			if [ -e "$$record" ] || [ -L "$$record" ]; then \
				echo "$(BIJUX_MAKES_DIR)/docs.mk: native renderer cannot bypass managed Bijux shell ownership: $$record" >&2; exit 1; \
			fi; \
		done; \
	fi
	@$(call require_file,$(DOCS_CONFIG))
	@$(call require_tool,$(firstword $(DOCS_RUN)))
ifeq ($(DOCS_RENDERER_PROFILE),bijux-material)
ifneq ($(strip $(DOCS_RUN)),$(strip $(DOCS_PYTHON_RUN) -m mkdocs))
	@echo "$(BIJUX_MAKES_DIR)/docs.mk: bijux-material DOCS_RUN must equal DOCS_PYTHON_RUN followed by -m mkdocs; configure the same Python launcher for admission and rendering" >&2; exit 1
endif
	@test -f "$(DOCS_MATERIAL_COMPILER)" || { echo "missing accepted Material runtime compiler: $(DOCS_MATERIAL_COMPILER)" >&2; exit 1; }
	@XDG_CACHE_HOME="$(DOCS_CACHE_DIR)" PYTHONDONTWRITEBYTECODE=1 \
		PYTHONPYCACHEPREFIX="$(DOCS_PYCACHE_DIR)" SITE_URL="$(DOCS_SITE_URL)" \
		$(DOCS_PYTHON_RUN) "$(DOCS_MATERIAL_COMPILER)" --check
endif

docs: docs-require ## Build strict documentation under artifacts
	@$(if $(strip $(DOCS_PREPARE_TARGETS)),$(BIJUX_MAKE) $(DOCS_PREPARE_TARGETS),:)
	@$(if $(strip $(DOCS_PREPARE_TARGETS)),$(BIJUX_MAKE) docs-require,:)
	@$(call safe_remove,$(DOCS_SITE_DIR))
	@mkdir -p "$(DOCS_SITE_DIR)" "$(DOCS_CACHE_DIR)" "$(DOCS_PYCACHE_DIR)"
	@XDG_CACHE_HOME="$(DOCS_CACHE_DIR)" \
		PYTHONPYCACHEPREFIX="$(DOCS_PYCACHE_DIR)" \
		SITE_URL="$(DOCS_SITE_URL)" \
		$(DOCS_RUN) build $(DOCS_BUILD_FLAGS) \
			--config-file "$(DOCS_CONFIG)" \
			--site-dir "$(DOCS_SITE_DIR)"
	@$(BIJUX_MAKE) docs-hygiene

docs-check: docs-require ## Validate a strict documentation build
	@$(if $(strip $(DOCS_PREPARE_TARGETS)),$(BIJUX_MAKE) $(DOCS_PREPARE_TARGETS),:)
	@$(if $(strip $(DOCS_SOURCE_CHECK_TARGETS)),$(BIJUX_MAKE) $(DOCS_SOURCE_CHECK_TARGETS),:)
	@$(if $(strip $(DOCS_PREPARE_TARGETS) $(DOCS_SOURCE_CHECK_TARGETS)),$(BIJUX_MAKE) docs-require,:)
	@$(call safe_remove,$(DOCS_CHECK_SITE_DIR))
	@mkdir -p "$(DOCS_CHECK_SITE_DIR)" "$(DOCS_CACHE_DIR)" "$(DOCS_PYCACHE_DIR)"
	@XDG_CACHE_HOME="$(DOCS_CACHE_DIR)" \
		PYTHONPYCACHEPREFIX="$(DOCS_PYCACHE_DIR)" \
		SITE_URL="$(DOCS_SITE_URL)" \
		$(DOCS_RUN) build $(DOCS_CHECK_FLAGS) \
			--config-file "$(DOCS_CONFIG)" \
			--site-dir "$(DOCS_CHECK_SITE_DIR)"
	@$(BIJUX_MAKE) docs-hygiene

docs-serve: docs-require ## Serve documentation in the foreground
	@$(if $(strip $(DOCS_PREPARE_TARGETS)),$(BIJUX_MAKE) $(DOCS_PREPARE_TARGETS),:)
	@$(if $(strip $(DOCS_PREPARE_TARGETS)),$(BIJUX_MAKE) docs-require,:)
	@mkdir -p "$(DOCS_CACHE_DIR)" "$(DOCS_PYCACHE_DIR)"
	@XDG_CACHE_HOME="$(DOCS_CACHE_DIR)" \
		PYTHONPYCACHEPREFIX="$(DOCS_PYCACHE_DIR)" \
		SITE_URL="http://$(DOCS_DEV_ADDR)/" \
		$(DOCS_RUN) serve $(DOCS_SERVE_FLAGS) \
			--config-file "$(DOCS_CONFIG)" \
			--dev-addr "$(DOCS_DEV_ADDR)"

docs-clean: ## Remove documentation artifacts
	@$(call safe_remove,$(ARTIFACT_ROOT_ABS)/docs)

docs-hygiene: ## Reject documentation output outside artifacts
	@for path in $(DOCS_HYGIENE_FORBIDDEN_PATHS); do \
		test ! -e "$(PROJECT_ROOT)/$$path" || { echo "forbidden documentation output: $$path" >&2; exit 1; }; \
	done
