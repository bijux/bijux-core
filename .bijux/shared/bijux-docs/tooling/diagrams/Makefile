# Standalone targets may also be included by the repository's docs Make domain.
DIAGRAM_TOOLING_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
DIAGRAM_ARTIFACT_ROOT ?= artifacts/website-security/dependencies
DIAGRAM_DEPENDENCIES ?= $(DIAGRAM_ARTIFACT_ROOT)/build
DIAGRAM_NODE ?= node
DIAGRAM_PYTHON ?= python3

.PHONY: diagrams-install diagrams-build diagrams-check

diagrams-install:
	$(DIAGRAM_NODE) "$(DIAGRAM_TOOLING_DIR)/install.mjs" --artifact-root "$(DIAGRAM_ARTIFACT_ROOT)"

diagrams-build:
	$(DIAGRAM_NODE) "$(DIAGRAM_TOOLING_DIR)/build.mjs" --dependencies "$(DIAGRAM_DEPENDENCIES)" --output-dir "$(DIAGRAM_ARTIFACT_ROOT)/renderer"

diagrams-check:
	BIJUX_DIAGRAM_DEPENDENCIES="$(abspath $(DIAGRAM_DEPENDENCIES))" PYTHONDONTWRITEBYTECODE=1 $(DIAGRAM_PYTHON) -m unittest discover -s tests -p test_diagram_dependency.py -v
