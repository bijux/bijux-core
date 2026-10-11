BUILD_DIR                 ?= $(PROJECT_ARTIFACTS_DIR)/build
BUILD_PYTHON              ?= $(VENV_PYTHON)
BUILD_CHECK_DISTS         ?= 1
BUILD_REQUIRE_PYPROJECT   ?= 1
BUILD_CLEAN_PATHS         ?= build dist *.egg-info
BUILD_CLEAN_PYCACHE       ?= 0
BUILD_TEMP_CLEAN_PATHS    ?= $(BUILD_CLEAN_PATHS)
BUILD_TEMP_CLEAN_PYCACHE  ?= 0
BUILD_RELEASE_DRY_RUN_CMD ?=
BUILD_PRE_TARGETS         ?=
BUILD_POST_TARGETS        ?=
BUILD_PACKAGE_DIR         ?= .
BUILD_PACKAGE_NAME        ?= $(if $(strip $(PACKAGE_NAME)),$(PACKAGE_NAME),$(PROJECT_SLUG))
BUILD_PER_PACKAGE_DIRS    ?= 0
ROOT_BUILD_PACKAGE_DIRS   ?=
ROOT_BUILD_ALIAS_PACKAGES ?=
BUILD_TOOLS_COMMAND       ?= $(UV) pip install --python "$(BUILD_PYTHON)" --upgrade build twine
BUILD_SELF_MAKE           ?= $(MAKE) -f $(firstword $(MAKEFILE_LIST))
BUILD_COMMAND             ?= $(BUILD_PYTHON) -m build --wheel --sdist --outdir "$(BUILD_DIR_ABS)" .
BUILD_SDIST_COMMAND       ?= $(BUILD_PYTHON) -m build --sdist --outdir "$(BUILD_DIR_ABS)" .
BUILD_WHEEL_COMMAND       ?= $(BUILD_PYTHON) -m build --wheel --outdir "$(BUILD_DIR_ABS)" .
BUILD_SUCCESS_MESSAGE     ?= ✔ Build artifacts ready in '$(BUILD_DIR_ABS)'

include $(abspath $(dir $(lastword $(MAKEFILE_LIST))))/util.mk

BUILD_DIR_ABS := $(abspath $(BUILD_DIR))
PYPROJECT_ABS := $(abspath pyproject.toml)
TWINE         ?= $(BUILD_PYTHON) -m twine

.PHONY: build build-package build-sdist build-wheel build-check build-tools build-clean build-clean-temp release-dry

define define_root_build_alias
build-$(1):
	@$$(MAKE) build-package PACKAGE_DIR=packages/$(1) PACKAGE_NAME=$(1)
.PHONY: build-$(1)
endef

$(foreach package,$(ROOT_BUILD_ALIAS_PACKAGES),$(eval $(call define_root_build_alias,$(package))))

build-tools: | $(VENV_PYTHON)
	@echo "→ Ensuring build toolchain..."
	@$(BUILD_TOOLS_COMMAND)

build: build-tools
	@if [ -n "$(strip $(ROOT_BUILD_PACKAGE_DIRS))" ]; then \
	  set -e; \
	  for package_dir in $(ROOT_BUILD_PACKAGE_DIRS); do \
	    package_name="$$(basename "$$package_dir")"; \
	    $(BUILD_SELF_MAKE) build-package PACKAGE_DIR="$$package_dir" PACKAGE_NAME="$$package_name"; \
	  done; \
	  echo "$(BUILD_SUCCESS_MESSAGE)"; \
	else \
	  $(BUILD_SELF_MAKE) build-package PACKAGE_DIR="$(BUILD_PACKAGE_DIR)" PACKAGE_NAME="$(BUILD_PACKAGE_NAME)"; \
	fi

build-package: build-tools
	@if [ -z "$(PACKAGE_DIR)" ]; then echo "✘ PACKAGE_DIR is required"; exit 1; fi
	@if [ "$(BUILD_REQUIRE_PYPROJECT)" = "1" ] && [ ! -f "$(abspath $(PACKAGE_DIR))/pyproject.toml" ]; then echo "✘ pyproject.toml not found in $(PACKAGE_DIR)"; exit 1; fi
	$(call run_make_targets,$(BUILD_PRE_TARGETS),$(BUILD_SELF_MAKE))
	@set -e; \
	package_slug="$(if $(strip $(PACKAGE_NAME)),$(PACKAGE_NAME),$(notdir $(PACKAGE_DIR)))"; \
	out_dir="$(BUILD_DIR_ABS)"; \
	if [ "$(BUILD_PER_PACKAGE_DIRS)" = "1" ]; then out_dir="$(BUILD_DIR_ABS)/$$package_slug"; fi; \
	mkdir -p "$$out_dir"; \
	printf '→ Preparing Python package artifacts for %s\n' "$(PACKAGE_DIR)"; \
	printf '→ Building wheel + sdist → %s\n' "$$out_dir"; \
	$(BUILD_PYTHON) -m build --wheel --sdist --outdir "$$out_dir" "$(abspath $(PACKAGE_DIR))"; \
	if [ "$(BUILD_CHECK_DISTS)" = "1" ]; then \
	  echo "→ Validating distributions with twine"; \
	  $(TWINE) check "$$out_dir"/*.whl "$$out_dir"/*.tar.gz 2>&1 | tee "$$out_dir/twine-check.log"; \
	else \
	  echo "→ Skipping twine check (BUILD_CHECK_DISTS=$(BUILD_CHECK_DISTS))"; \
	fi; \
	echo "✔ Package artifacts ready in '$$out_dir'"; \
	ls -l "$$out_dir" || true
	$(call run_make_targets,$(BUILD_POST_TARGETS),$(BUILD_SELF_MAKE))
	@$(BUILD_SELF_MAKE) build-clean-temp

build-sdist: build-tools
	@if [ "$(BUILD_REQUIRE_PYPROJECT)" = "1" ] && [ ! -f "$(PYPROJECT_ABS)" ]; then echo "✘ pyproject.toml not found"; exit 1; fi
	@mkdir -p "$(BUILD_DIR_ABS)"
	@echo "→ Building sdist → $(BUILD_DIR_ABS)"
	@$(BUILD_SDIST_COMMAND)
	@$(BUILD_SELF_MAKE) build-clean-temp

build-wheel: build-tools
	@if [ "$(BUILD_REQUIRE_PYPROJECT)" = "1" ] && [ ! -f "$(PYPROJECT_ABS)" ]; then echo "✘ pyproject.toml not found"; exit 1; fi
	@mkdir -p "$(BUILD_DIR_ABS)"
	@echo "→ Building wheel → $(BUILD_DIR_ABS)"
	@$(BUILD_WHEEL_COMMAND)
	@$(BUILD_SELF_MAKE) build-clean-temp

build-check:
	@if find "$(BUILD_DIR_ABS)" \( -name '*.whl' -o -name '*.tar.gz' \) -print -quit | grep -q .; then \
	  find "$(BUILD_DIR_ABS)" \( -name '*.whl' -o -name '*.tar.gz' \) -print0 | xargs -0 "$(BUILD_PYTHON)" -m twine check 2>&1 | tee "$(BUILD_DIR_ABS)/twine-check.log"; \
	else \
	  echo "✘ No artifacts in $(BUILD_DIR_ABS) to check"; exit 1; \
	fi

build-clean-temp:
	@set -e; \
	if [ -z "$(strip $(BUILD_TEMP_CLEAN_PATHS))" ] && [ "$(BUILD_TEMP_CLEAN_PYCACHE)" != "1" ]; then \
	  echo "→ No temporary build files configured"; \
	  exit 0; \
	fi; \
	echo "→ Cleaning temporary build files"; \
	if [ -n "$(strip $(BUILD_TEMP_CLEAN_PATHS))" ]; then rm -rf $(BUILD_TEMP_CLEAN_PATHS) || true; fi; \
	if [ "$(BUILD_TEMP_CLEAN_PYCACHE)" = "1" ]; then \
	  find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true; \
	fi; \
	echo "✔ Temporary build files cleaned"

build-clean:
	@echo "→ Cleaning build artifacts..."
	@rm -rf "$(BUILD_DIR_ABS)" $(BUILD_CLEAN_PATHS) || true
	@if [ "$(BUILD_CLEAN_PYCACHE)" = "1" ]; then \
	  find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true; \
	fi
	@$(BUILD_SELF_MAKE) build-clean-temp
	@echo "✔ Build artifacts cleaned"

release-dry: build
	@if [ -z "$(strip $(BUILD_RELEASE_DRY_RUN_CMD))" ]; then \
	  echo "→ release-dry is not configured for $(PROJECT_SLUG)"; \
	  exit 0; \
	fi
	@echo "→ Running release dry-run checks..."
	@$(BUILD_RELEASE_DRY_RUN_CMD)
	@echo "✔ Release dry-run complete"

##@ Build
build-tools:      ## Ensure the active environment has build tooling available
build-clean:      ## Remove generated build artifacts and package-specific cleanup paths
build-clean-temp: ## Remove temporary build files created during packaging
build:            ## Build package artifacts into $(BUILD_DIR)
build-package:    ## Build wheel and sdist for PACKAGE_DIR into $(BUILD_DIR)
build-sdist:      ## Build an sdist into $(BUILD_DIR)
build-wheel:      ## Build a wheel into $(BUILD_DIR)
build-check:      ## Run twine check on artifacts under $(BUILD_DIR)
release-dry:      ## Run package-defined release verification after building artifacts
