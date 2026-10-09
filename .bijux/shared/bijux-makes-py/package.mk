PACKAGE_PROFILE_MAKEFILE ?= $(abspath $(firstword $(MAKEFILE_LIST)))
PACKAGE_MAKEFILE_DIR ?= $(abspath $(dir $(PACKAGE_PROFILE_MAKEFILE)))
PROJECT_DIR ?= $(CURDIR)
PROJECT_SLUG ?= $(notdir $(abspath $(PROJECT_DIR)))

include $(PACKAGE_MAKEFILE_DIR)/../env.mk

PACKAGE_KIND ?= python

PACKAGE_IMPORT_NAME ?=
PACKAGE_SOURCE_DIR ?= $(if $(strip $(PACKAGE_IMPORT_NAME)),src/$(PACKAGE_IMPORT_NAME),src)
PACKAGE_TEST_DIRS ?= tests
PACKAGE_LINT_EXTRA_DIRS ?=
PACKAGE_CLEAN_EXTRA_PATHS ?=

LINT_DIRS ?= $(strip $(PACKAGE_SOURCE_DIR) $(PACKAGE_TEST_DIRS) $(PACKAGE_LINT_EXTRA_DIRS))
INTERROGATE_PATHS ?= $(PACKAGE_SOURCE_DIR)
QUALITY_PATHS ?= $(PACKAGE_SOURCE_DIR)
QUALITY_MYPY_CONFIG ?= $(MYPY_CONFIG)
QUALITY_VULTURE_MIN_CONFIDENCE ?= 80
SECURITY_PATHS ?= $(PACKAGE_SOURCE_DIR)
PUBLISH_UPLOAD_ENABLED ?= 0
BUILD_CLEAN_PATHS ?= $(COMMON_BUILD_CLEAN_PATHS)
PACKAGE_CLEAN_PATHS ?= $(strip $(COMMON_PYTHON_CLEAN_PATHS) $(COMMON_ARTIFACT_CLEAN_PATHS) $(PACKAGE_CLEAN_EXTRA_PATHS))

ifeq ($(PACKAGE_KIND),python)
else ifeq ($(PACKAGE_KIND),repository-python)
PACKAGE_INSTALL_SPEC ?= .
RUFF_CONFIG ?= $(MONOREPO_ROOT)/configs/ruff.toml
TEST_PATHS ?= tests
TEST_SOURCE_PATHS ?= src
INTERROGATE_PATHS ?= src
QUALITY_PATHS ?= $(TEST_SOURCE_PATHS)
SECURITY_PATHS ?= $(TEST_SOURCE_PATHS)
BUILD_DIR ?= $(PROJECT_ARTIFACTS_DIR)/build
SBOM_DIR ?= $(PROJECT_ARTIFACTS_DIR)/sbom
else ifeq ($(PACKAGE_KIND),api-python)
PYTHON ?= python3.11
ENABLE_CODESPELL ?= 1
ENABLE_RADON ?= 1
ENABLE_PYDOCSTYLE ?= 0
ENABLE_PYTYPE ?= 0
RUFF_CHECK_FIX ?= 1
QUALITY_VULTURE_MIN_CONFIDENCE ?= 80
SECURITY_IGNORE_IDS ?=
API_MODE ?= contract
API_BASE_PATH ?=
BUILD_CHECK_DISTS ?= 1
BUILD_CLEAN_PATHS ?= $(COMMON_BUILD_CLEAN_PATHS)
BUILD_CLEAN_PYCACHE ?= 1
PACKAGE_BOOTSTRAP_TARGETS ?= lint quality security api
PACKAGE_CLEAN_EXTRA_PATHS ?= demo .tmp_home \
	$(COMMON_API_TEMP_CLEAN_PATHS) \
	docs/reference usage_test usage_test_artifacts \
	$(COMMON_CONFIG_CACHE_CLEAN_PATHS)
PACKAGE_ALL_TARGETS ?= clean install test lint quality security api build sbom
PACKAGE_DEFINE_ALL_PARALLEL ?= 1
else ifeq ($(PACKAGE_KIND),workspace-python)
PYTHON ?= python3.11
ACT ?= $(if $(wildcard $(VENV)/bin/activate),$(VENV)/bin,$(ACT))
ENABLE_CODESPELL ?= 1
ENABLE_RADON ?= 1
ENABLE_PYDOCSTYLE ?= 1
ENABLE_PYTYPE ?= 0
LINT_PRE_TARGETS ?= ensure-venv
RUFF_CHECK_FIX ?= 0
MYPY_FLAGS ?= --strict --follow-imports silent
RADON_COMPLEXITY_MAX ?= 48
PYDOCSTYLE_ARGS ?= --convention=google --add-ignore=D100,D101,D102,D103,D104,D105,D106,D107
QUALITY_MYPY_CONFIG ?= $(MONOREPO_ROOT)/configs/mypy.ini
QUALITY_MYPY_FLAGS ?= --strict --follow-imports silent
QUALITY_PRE_TARGETS ?= ensure-venv
SKIP_MYPY ?= 0
QUALITY_VULTURE_MIN_CONFIDENCE ?= 90
SECURITY_IGNORE_IDS ?=
SECURITY_BANDIT_SKIP_IDS ?=
API_MODE ?= contract
API_BASE_PATH ?=
API_DYNAMIC_PORT ?= 1
OPENAPI_GENERATOR_NPM_PACKAGE ?= @openapitools/openapi-generator-cli@7.14.0
BUILD_CHECK_DISTS ?= 1
BUILD_TEMP_CLEAN_PATHS ?= $(COMMON_BUILD_CLEAN_PATHS) src/*.egg-info
BUILD_TEMP_CLEAN_PYCACHE ?= 1
PUBLISH_UPLOAD_ENABLED ?= 0
TEST_PRE_TARGETS ?= ensure-venv
TEST_PATHS_E2E ?= tests/e2e
TEST_PATHS_REGRESSION ?= tests/regression
TEST_PATHS_EVALUATION ?= tests/regression
TEST_MAIN_ARGS ?= -m "not real_local and not api"
TEST_CI_TARGETS ?= test-unit test-e2e test-regression test-evaluation
TEST_REAL_LOCAL_PATH ?= tests/real_local
PACKAGE_DEFINE_INSTALL ?= 0
PACKAGE_DEFINE_CLEAN ?= 0
PACKAGE_ALL_TARGETS ?= clean install test lint quality security sbom build api
PACKAGE_HELP_WIDTH ?= 22
PACKAGE_VENV_CREATE_MESSAGE ?= → Creating virtualenv at '$(VENV)' with '$$(which $(PYTHON))' ...
WORKSPACE_EDITABLE_EXTRAS ?= $${EXTRAS:-dev}
WORKSPACE_DEPENDENCY_PATHS ?= "$(VENV_PYTHON)" -c 'from packaging.requirements import Requirement; from pathlib import Path; import tomllib; root = Path("$(MONOREPO_ROOT)"); workspace = tomllib.loads((root / "pyproject.toml").read_text()); package = tomllib.loads(Path("pyproject.toml").read_text()); package_dirs = workspace.get("tool", {}).get("bijux_canon", {}).get("package_dirs", {}); dependencies = package.get("project", {}).get("dependencies", []); current_name = package.get("project", {}).get("name"); [print(root / package_dirs[name]) for dep in dependencies if (name := Requirement(dep).name) != current_name and name in package_dirs]'
WORKSPACE_EXTERNAL_DEPENDENCIES ?= "$(VENV_PYTHON)" -c 'import os, tomllib; from packaging.requirements import Requirement; from pathlib import Path; root = Path("$(MONOREPO_ROOT)"); workspace = tomllib.loads((root / "pyproject.toml").read_text()); package = tomllib.loads(Path("pyproject.toml").read_text()); package_dirs = workspace.get("tool", {}).get("bijux_canon", {}).get("package_dirs", {}); local_names = set(package_dirs); dependencies = list(package.get("project", {}).get("dependencies", [])); extras = [extra.strip() for extra in os.environ.get("EXTRAS", "dev").split(",") if extra.strip()]; optional = package.get("project", {}).get("optional-dependencies", {}); [dependencies.extend(optional.get(extra, [])) for extra in extras]; current_name = package.get("project", {}).get("name"); [print(dep) for dep in dependencies if (name := Requirement(dep).name) != current_name and name not in local_names]'
WORKSPACE_SOFT_CLEAN_PATHS ?= $(COMMON_PYTHON_CLEAN_PATHS) demo .tmp_home $(COMMON_ARTIFACT_CLEAN_PATHS)
else
$(error Unsupported PACKAGE_KIND '$(PACKAGE_KIND)'; expected python, repository-python, api-python, or workspace-python)
endif

PACKAGE_DEFINE_VENV ?= 1
PACKAGE_DEFINE_INSTALL ?= 1
PACKAGE_DEFINE_BOOTSTRAP ?= 1
PACKAGE_DEFINE_CLEAN ?= 1
PACKAGE_DEFINE_ALL ?= 1
PACKAGE_DEFINE_HELP ?= 1

PACKAGE_NOTPARALLEL_TARGETS ?= all clean
PACKAGE_VENV_CREATE_MESSAGE ?= → Creating virtualenv with '$$(which $(PYTHON))' ...
PACKAGE_INSTALL_MESSAGE ?= → Installing dependencies...
PACKAGE_INSTALL_SPEC ?= .[dev]
PACKAGE_INSTALL_EDITABLE ?= 1
PACKAGE_INSTALL_BOOTSTRAP_PACKAGES ?= pip setuptools wheel
PACKAGE_INSTALL_PYTHON_PACKAGES ?=
PACKAGE_INSTALL_STAMP ?=
PACKAGE_BOOTSTRAP_PREREQS ?= install
PACKAGE_CLEAN_MESSAGE ?= → Cleaning ($(VENV)) ...
PACKAGE_CLEAN_SOFT_MESSAGE ?= → Cleaning (artifacts, caches) ...
PACKAGE_CLEAN_DELETE_PYCACHE ?= 1
PACKAGE_CLEAN_DELETE_PYC_FILES ?= 1
PACKAGE_ALL_TARGETS ?= clean install test lint quality security api build sbom
PACKAGE_ALL_MESSAGE ?= ✔ All targets completed
PACKAGE_HELP_WIDTH ?= 20
PACKAGE_BOOTSTRAP_TARGETS ?=
PACKAGE_INSTALL_TARGETS ?= \
	lint-artifacts mypy-core mypy-extended \
	test test-unit test-e2e test-regression test-evaluation real-local \
	quality interrogate-report docs-links \
	security-bandit security-audit security-deps \
	build sbom api
PACKAGE_DEFINE_ALL_PARALLEL ?= 0
PACKAGE_ALL_PARALLEL_PRE_TARGETS ?= clean install
PACKAGE_ALL_PARALLEL_MAIN_TARGETS ?= quality security api
PACKAGE_ALL_PARALLEL_MAIN_JOBS ?= 4
PACKAGE_ALL_PARALLEL_FINAL_TARGETS ?= build sbom
PACKAGE_ALL_PARALLEL_MESSAGE ?= ✔ All targets completed (parallel mode)

.NOTPARALLEL: $(PACKAGE_NOTPARALLEL_TARGETS)

include $(ROOT_MAKE_DIR)/bijux-py/ci/lint.mk
include $(ROOT_MAKE_DIR)/bijux-py/ci/test.mk
include $(ROOT_MAKE_DIR)/bijux-py/ci/quality.mk
include $(ROOT_MAKE_DIR)/bijux-py/ci/security.mk
include $(ROOT_MAKE_DIR)/bijux-py/ci/build.mk
include $(ROOT_MAKE_DIR)/bijux-py/ci/sbom.mk
include $(ROOT_MAKE_DIR)/bijux-py/api.mk
include $(ROOT_MAKE_DIR)/publish.mk

PACKAGE_ARTIFACT_ALIAS_SCRIPT ?= $(ROOT_MAKE_DIR)/bijux-py/repository/artifact_aliases.py

setup: ## Materialize package artifact alias links
	@mkdir -p "$(PROJECT_PROCESS_DIR)"
	@"$(PYTHON)" "$(PACKAGE_ARTIFACT_ALIAS_SCRIPT)" package --repo-root "$(MONOREPO_ROOT)" --package-dir "$(PROJECT_DIR)"
.PHONY: setup

ifeq ($(PACKAGE_DEFINE_VENV),1)
$(VENV_PYTHON): | setup
	@echo "$(PACKAGE_VENV_CREATE_MESSAGE)"
	@$(UV) venv --python "$(PYTHON)" "$(VENV)"
endif

ifeq ($(PACKAGE_DEFINE_INSTALL),1)
ifneq ($(strip $(PACKAGE_INSTALL_STAMP)),)
$(PACKAGE_INSTALL_STAMP): $(VENV_PYTHON)
	@echo "$(PACKAGE_INSTALL_MESSAGE)"
	@mkdir -p "$(PROJECT_ARTIFACTS_DIR)"
	@if [ -n "$(strip $(PACKAGE_INSTALL_BOOTSTRAP_PACKAGES))" ]; then \
	  if ! $(UV) pip install --python "$(VENV_PYTHON)" --upgrade $(PACKAGE_INSTALL_BOOTSTRAP_PACKAGES); then \
	    echo "→ uv pip install failed; retrying with python -m pip"; \
	    "$(VENV_PYTHON)" -m pip install --upgrade $(PACKAGE_INSTALL_BOOTSTRAP_PACKAGES); \
	  fi; \
	fi
	@if [ -n "$(strip $(PACKAGE_INSTALL_PYTHON_PACKAGES))" ]; then \
	  if ! $(UV) pip install --python "$(VENV_PYTHON)" --upgrade $(PACKAGE_INSTALL_PYTHON_PACKAGES); then \
	    echo "→ uv pip install failed; retrying with python -m pip"; \
	    "$(VENV_PYTHON)" -m pip install --upgrade $(PACKAGE_INSTALL_PYTHON_PACKAGES); \
	  fi; \
	fi
	@if [ "$(PACKAGE_INSTALL_EDITABLE)" = "1" ] && [ -n "$(strip $(PACKAGE_INSTALL_SPEC))" ]; then \
	  if ! $(UV) pip install --python "$(VENV_PYTHON)" --editable "$(PACKAGE_INSTALL_SPEC)"; then \
	    echo "→ uv pip install failed; retrying with python -m pip"; \
	    "$(VENV_PYTHON)" -m pip install --editable "$(PACKAGE_INSTALL_SPEC)"; \
	  fi; \
	fi
	@touch "$(PACKAGE_INSTALL_STAMP)"

install: $(PACKAGE_INSTALL_STAMP)
else
install: $(VENV_PYTHON)
	@echo "$(PACKAGE_INSTALL_MESSAGE)"
	@if [ -n "$(strip $(PACKAGE_INSTALL_BOOTSTRAP_PACKAGES))" ]; then \
	  if ! $(UV) pip install --python "$(VENV_PYTHON)" --upgrade $(PACKAGE_INSTALL_BOOTSTRAP_PACKAGES); then \
	    echo "→ uv pip install failed; retrying with python -m pip"; \
	    "$(VENV_PYTHON)" -m pip install --upgrade $(PACKAGE_INSTALL_BOOTSTRAP_PACKAGES); \
	  fi; \
	fi
	@if [ -n "$(strip $(PACKAGE_INSTALL_PYTHON_PACKAGES))" ]; then \
	  if ! $(UV) pip install --python "$(VENV_PYTHON)" --upgrade $(PACKAGE_INSTALL_PYTHON_PACKAGES); then \
	    echo "→ uv pip install failed; retrying with python -m pip"; \
	    "$(VENV_PYTHON)" -m pip install --upgrade $(PACKAGE_INSTALL_PYTHON_PACKAGES); \
	  fi; \
	fi
	@if [ "$(PACKAGE_INSTALL_EDITABLE)" = "1" ] && [ -n "$(strip $(PACKAGE_INSTALL_SPEC))" ]; then \
	  if ! $(UV) pip install --python "$(VENV_PYTHON)" --editable "$(PACKAGE_INSTALL_SPEC)"; then \
	    echo "→ uv pip install failed; retrying with python -m pip"; \
	    "$(VENV_PYTHON)" -m pip install --editable "$(PACKAGE_INSTALL_SPEC)"; \
	  fi; \
	fi
endif
.PHONY: install
endif

ifeq ($(PACKAGE_DEFINE_BOOTSTRAP),1)
bootstrap: $(PACKAGE_BOOTSTRAP_PREREQS)
.PHONY: bootstrap
endif

ifneq ($(strip $(PACKAGE_BOOTSTRAP_TARGETS)),)
$(PACKAGE_BOOTSTRAP_TARGETS): | bootstrap
endif

ifneq ($(strip $(PACKAGE_INSTALL_TARGETS)),)
$(PACKAGE_INSTALL_TARGETS): install
endif

ifeq ($(PACKAGE_DEFINE_CLEAN),1)
clean: clean-soft
	@echo "$(PACKAGE_CLEAN_MESSAGE)"
	@$(RM) "$(VENV)"

clean-soft:
	@echo "$(PACKAGE_CLEAN_SOFT_MESSAGE)"
	@$(RM) $(PACKAGE_CLEAN_PATHS) || true
ifeq ($(PACKAGE_CLEAN_DELETE_PYCACHE),1)
	@if [ "$(OS)" != "Windows_NT" ]; then \
	  find . -type d -name '__pycache__' -exec $(RM) {} +; \
	fi
endif
ifeq ($(PACKAGE_CLEAN_DELETE_PYC_FILES),1)
	@if [ "$(OS)" != "Windows_NT" ]; then \
	  find . -type f -name '*.pyc' -delete; \
	fi
endif
.PHONY: clean clean-soft
endif

ifeq ($(PACKAGE_DEFINE_ALL),1)
all: $(PACKAGE_ALL_TARGETS)
	@echo "$(PACKAGE_ALL_MESSAGE)"
.PHONY: all
endif

ifeq ($(PACKAGE_DEFINE_HELP),1)
HELP_WIDTH := $(PACKAGE_HELP_WIDTH)
include $(ROOT_MAKE_DIR)/bijux-py/ci/help.mk
endif

ifeq ($(PACKAGE_DEFINE_ALL_PARALLEL),1)
all-parallel: $(PACKAGE_ALL_PARALLEL_PRE_TARGETS)
	@$(SELF_MAKE) -j$(PACKAGE_ALL_PARALLEL_MAIN_JOBS) $(PACKAGE_ALL_PARALLEL_MAIN_TARGETS)
	@$(SELF_MAKE) $(PACKAGE_ALL_PARALLEL_FINAL_TARGETS)
	@echo "$(PACKAGE_ALL_PARALLEL_MESSAGE)"
.PHONY: all-parallel
endif

ifeq ($(PACKAGE_KIND),workspace-python)
.PHONY: ensure-venv nlenv clean-venv

ensure-venv: $(VENV_PYTHON) ## Ensure venv exists and deps are installed
	@set -e; \
	echo "→ Ensuring dependencies in $(VENV) ..."; \
	mkdir -p "$(PROJECT_ARTIFACTS_DIR)"; \
	if ! $(UV) pip install --python "$(VENV_PYTHON)" --upgrade pip setuptools wheel; then \
	  echo "→ uv pip install failed; retrying with python -m pip"; \
	  "$(VENV_PYTHON)" -m pip install --upgrade pip setuptools wheel; \
	fi; \
	EXTRAS="$(WORKSPACE_EDITABLE_EXTRAS)"; \
	if [ -n "$$EXTRAS" ]; then SPEC=".[$$EXTRAS]"; else SPEC="."; fi; \
	EXTERNAL_REQS_FILE="$(PROJECT_ARTIFACTS_DIR)/workspace-external-requirements.txt"; \
	: > "$$EXTERNAL_REQS_FILE"; \
	EXTRAS="$$EXTRAS" $(WORKSPACE_EXTERNAL_DEPENDENCIES) > "$$EXTERNAL_REQS_FILE"; \
	if [ -s "$$EXTERNAL_REQS_FILE" ]; then \
	  echo "→ Installing external workspace dependencies"; \
	  if ! $(UV) pip install --python "$(VENV_PYTHON)" --requirement "$$EXTERNAL_REQS_FILE"; then \
	    echo "→ uv pip install failed; retrying with python -m pip"; \
	    "$(VENV_PYTHON)" -m pip install --requirement "$$EXTERNAL_REQS_FILE"; \
	  fi; \
	fi; \
	echo "→ Installing workspace runtime dependencies"; \
	$(WORKSPACE_DEPENDENCY_PATHS) | while IFS= read -r package_dir; do \
	  [ -n "$$package_dir" ] || continue; \
	  if ! $(UV) pip install --python "$(VENV_PYTHON)" --editable "$$package_dir"; then \
	    echo "→ uv pip install failed; retrying with python -m pip"; \
	    "$(VENV_PYTHON)" -m pip install --editable "$$package_dir"; \
	  fi; \
	done; \
	echo "→ Installing: $$SPEC"; \
	if ! $(UV) pip install --python "$(VENV_PYTHON)" --editable "$$SPEC" --no-deps; then \
	  echo "→ uv pip install failed; retrying with python -m pip"; \
	  "$(VENV_PYTHON)" -m pip install --editable "$$SPEC" --no-deps; \
	fi

install: ensure-venv ## Install project into .venv (dev)
	@true

nlenv: ## Print activate command
	@echo "Run: source $(ACT)/activate"

clean-soft: ## Remove build artifacts but keep venv
	@echo "→ Cleaning (no .venv removal) ..."
	@$(RM) $(WORKSPACE_SOFT_CLEAN_PATHS) || true
	@if [ "$(OS)" != "Windows_NT" ]; then \
	  find . -type d -name '__pycache__' -exec $(RM) {} +; \
	fi

clean-venv: ## Remove the virtualenv only
	@echo "→ Cleaning ($(VENV)) ..."
	@$(RM) "$(VENV)"

clean: clean-soft clean-venv ## Remove venv + artifacts

all: ## Full pipeline
help: ## Show this help
endif

##@ Core
clean: ## Remove virtualenv plus package artifacts
clean-soft: ## Remove build artifacts but keep the virtualenv
install: ## Install package dependencies into the virtualenv
help: ## Show package commands
bootstrap: ## Install package prerequisites for gate targets
all-parallel: ## Run parallel package checks when enabled
