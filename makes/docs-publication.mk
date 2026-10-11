# Publication selects a clean, approved renderer independently of local docs tools.
DOCS_PUBLICATION_SHARED := .bijux/shared/bijux-docs
DOCS_PUBLICATION_PYTHON := $(abspath artifacts/docs/publication/python/bin/python)
DOCS_PUBLICATION_SITE_URL := https://bijux.io/bijux-core/
DOCS_PUBLICATION_SITE_DIR := artifacts/docs/site
DOCS_PUBLICATION_BUILDER := $(DOCS_PUBLICATION_SHARED)/tooling/security/publication_builder.py

.PHONY: gh-docs-install gh-docs-build gh-docs-verify

gh-docs-install: ## Install the frozen documentation publication renderer
	@python3 "$(DOCS_PUBLICATION_SHARED)/tooling/security/install_publication_renderer.py" --recipe history --python python3

gh-docs-build: ## Build and qualify the selected production documentation artifact
	@set -euo pipefail; \
	  test "$${DOCS_BUILD_SITE_URL:-$(DOCS_PUBLICATION_SITE_URL)}" = "$(DOCS_PUBLICATION_SITE_URL)" || { echo "Exact production documentation URL required" >&2; exit 1; }; \
	  test "$${DOCS_SITE_DIR:-$(DOCS_PUBLICATION_SITE_DIR)}" = "$(DOCS_PUBLICATION_SITE_DIR)" || { echo "Exact production documentation artifact required" >&2; exit 1; }; \
	  test -n "$${BIJUX_STD_ROOT:-}" || { echo "Accepted standards checkout required" >&2; exit 1; }; \
	  standard_root="$${BIJUX_STD_ROOT#$(CURDIR)/}"; \
	  test "$$standard_root" != "$$BIJUX_STD_ROOT" || { echo "Standards checkout must belong to artifacts/" >&2; exit 1; }; \
	  source "$(DOCS_PUBLICATION_SHARED)/tooling/scripts/docs_source_authority.sh"; \
	  verify_docs_authority "$(CURDIR)" "$(CURDIR)/$(DOCS_PUBLICATION_SHARED)"; \
	  "$(DOCS_PUBLICATION_PYTHON)" "$(DOCS_PUBLICATION_SHARED)/tooling/scripts/project_bijux_docs.py" "$(CURDIR)" "$(CURDIR)/$(DOCS_PUBLICATION_SHARED)" --check; \
	  make --no-print-directory docs-publication-check docs-mermaid-check check-badges readme-links-check DOCS_PYTHON_BIN="$(DOCS_PUBLICATION_PYTHON)"; \
	  SITE_URL="$(DOCS_PUBLICATION_SITE_URL)" "$(DOCS_PUBLICATION_PYTHON)" "$(DOCS_PUBLICATION_BUILDER)" capture \
	    --standard-root "$$standard_root" --site-url "$(DOCS_PUBLICATION_SITE_URL)" --site-dir "$(DOCS_PUBLICATION_SITE_DIR)" \
	    --config mkdocs.yml --build-command "make gh-docs-build" --verify-command "make gh-docs-verify"; \
	  SITE_URL="$(DOCS_PUBLICATION_SITE_URL)" "$(DOCS_PUBLICATION_PYTHON)" "$(DOCS_PUBLICATION_BUILDER)" render \
	    --config mkdocs.yml --site-dir "$(DOCS_PUBLICATION_SITE_DIR)" --site-url "$(DOCS_PUBLICATION_SITE_URL)"; \
	  make --no-print-directory docs-hygiene docs-navigation-check DOCS_PYTHON_BIN="$(DOCS_PUBLICATION_PYTHON)"; \
	  SITE_URL="$(DOCS_PUBLICATION_SITE_URL)" "$(DOCS_PUBLICATION_PYTHON)" "$(DOCS_PUBLICATION_BUILDER)" admit \
	    --site-dir "$(DOCS_PUBLICATION_SITE_DIR)" --site-url "$(DOCS_PUBLICATION_SITE_URL)"

gh-docs-verify: ## Recheck the qualified artifact and source receipts without rebuilding
	@set -euo pipefail; \
	  test "$${DOCS_BUILD_SITE_URL:-$(DOCS_PUBLICATION_SITE_URL)}" = "$(DOCS_PUBLICATION_SITE_URL)" || { echo "Exact production documentation URL required" >&2; exit 1; }; \
	  test "$${DOCS_SITE_DIR:-$(DOCS_PUBLICATION_SITE_DIR)}" = "$(DOCS_PUBLICATION_SITE_DIR)" || { echo "Exact production documentation artifact required" >&2; exit 1; }; \
	  SITE_URL="$(DOCS_PUBLICATION_SITE_URL)" "$(DOCS_PUBLICATION_PYTHON)" "$(DOCS_PUBLICATION_BUILDER)" verify
