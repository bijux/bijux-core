ifndef BIJUX_SHARED_REPOSITORY_ENV_INCLUDED
BIJUX_SHARED_REPOSITORY_ENV_INCLUDED := 1

.DELETE_ON_ERROR:
.DEFAULT_GOAL ?= all
.SHELLFLAGS := -eu -o pipefail -c
SHELL := bash

MONOREPO_ROOT ?= $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../../..)
PROJECT_DIR ?= $(CURDIR)
PROJECT_SLUG ?= $(notdir $(abspath $(PROJECT_DIR)))
ROOT_MAKE_DIR ?= $(MONOREPO_ROOT)/makes
CONFIG_DIR ?= $(MONOREPO_ROOT)/configs
API_DIR ?= $(MONOREPO_ROOT)/apis/$(PROJECT_SLUG)
MKDOCS_CFG ?= $(PROJECT_DIR)/mkdocs.yml
ARTIFACTS_ROOT ?= $(MONOREPO_ROOT)/artifacts
PROJECT_ARTIFACTS_DIR ?= $(abspath $(ARTIFACTS_ROOT)/$(PROJECT_SLUG))
PROJECT_PROCESS_DIR ?= $(PROJECT_ARTIFACTS_DIR)/process

PYTHON ?= $(shell command -v python3.11 || command -v python3)
UV ?= uv
VENV ?= $(abspath $(PROJECT_ARTIFACTS_DIR)/venv)
VENV_PYTHON ?= $(VENV)/bin/python
ACT ?= $(VENV)/bin
SELF_MAKE ?= $(if $(PACKAGE_PROFILE_MAKEFILE),$(MAKE) -f "$(PACKAGE_PROFILE_MAKEFILE)",$(MAKE))
override RM := rm -rf
DOCS_CONFIG_CLI ?=
DEPTRY_CONFIG ?= $(CONFIG_DIR)/deptry.toml
QUALITY_DEPTRY_TARGET ?= $(PROJECT_DIR)
SBOM_VERSION_RESOLVER ?=
SBOM_REQUIREMENTS_WRITER ?=
COMMON_BUILD_CLEAN_PATHS := build dist *.egg-info
COMMON_PYTHON_CLEAN_PATHS := \
	.pytest_cache htmlcov coverage.xml \
	$(COMMON_BUILD_CLEAN_PATHS) \
	.tox .nox .ruff_cache .mypy_cache .hypothesis \
	.coverage.* .coverage .benchmarks .cache
COMMON_API_TEMP_CLEAN_PATHS := spec.json openapitools.json node_modules site
COMMON_ARTIFACT_CLEAN_PATHS := artifacts "$(PROJECT_ARTIFACTS_DIR)"
COMMON_CONFIG_CACHE_CLEAN_PATHS := "$(CONFIG_DIR)/.ruff_cache"

# Package roots materialize local alias links that point into the repository
# artifact tree. Preserve the alias links and clean the canonical artifact
# location instead of deleting the aliases themselves.
COMMON_PYTHON_CLEAN_PATHS := $(filter-out .venv .hypothesis .benchmarks,$(COMMON_PYTHON_CLEAN_PATHS))
PROJECT_ARTIFACT_PRESERVE_DIRS ?= venv hypothesis benchmarks
PROJECT_ARTIFACT_CHILD_CLEAN_PATHS := $(shell if [ -d "$(PROJECT_ARTIFACTS_DIR)" ]; then find "$(PROJECT_ARTIFACTS_DIR)" -mindepth 1 -maxdepth 1 $(foreach dir,$(PROJECT_ARTIFACT_PRESERVE_DIRS),! -name "$(dir)") -print; fi)
COMMON_ARTIFACT_CLEAN_PATHS := $(PROJECT_ARTIFACT_CHILD_CLEAN_PATHS)

ifneq ($(strip $(PACKAGE_PROFILE_MAKEFILE)),)
MAKEFLAGS += -f $(PACKAGE_PROFILE_MAKEFILE)
endif

export PYTHONDONTWRITEBYTECODE := 1
export PYTHONPYCACHEPREFIX := $(PROJECT_ARTIFACTS_DIR)/pycache
export XDG_CACHE_HOME := $(PROJECT_ARTIFACTS_DIR)/xdg_cache
export HYPOTHESIS_STORAGE_DIRECTORY := $(PROJECT_ARTIFACTS_DIR)/hypothesis
export COVERAGE_FILE := $(PROJECT_ARTIFACTS_DIR)/test/.coverage
export UV_CACHE_DIR := $(PROJECT_ARTIFACTS_DIR)/uv_cache
export PIP_CACHE_DIR := $(PROJECT_ARTIFACTS_DIR)/pip_cache
export NPM_CONFIG_CACHE := $(PROJECT_ARTIFACTS_DIR)/npm_cache
export TMPDIR := $(PROJECT_PROCESS_DIR)
export PYTHONPATH ?=

export MONOREPO_ROOT PROJECT_DIR PROJECT_SLUG ROOT_MAKE_DIR CONFIG_DIR API_DIR MKDOCS_CFG ARTIFACTS_ROOT PROJECT_ARTIFACTS_DIR

ifneq ($(BIJUX_REPOSITORY_ENV_OVERLAY_INCLUDED),1)
ifneq ($(wildcard $(ROOT_MAKE_DIR)/env.mk),)
include $(ROOT_MAKE_DIR)/env.mk
endif
endif

endif
