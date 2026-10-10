BIJUX_PY_WORKSPACE_DIR ?= $(abspath $(PROJECT_DIR)/..)
BIJUX_PY_REPOS ?= bijux-canon bijux-proteomics bijux-pollenomics bijux-phylogenetics
BIJUX_PY_SYSTEM_REL ?= shared/bijux-makes-py
BIJUX_PY_LOCAL_REL ?= makes/bijux-py
BIJUX_PY_STD_PIN_REL ?= .github/standards/bijux-std.sha
BIJUX_STANDARD_SHARED_DIR ?= $(if $(wildcard $(PROJECT_DIR)/.bijux/shared/bijux-gh),.bijux/shared/bijux-gh,shared/bijux-gh)
BIJUX_STANDARD_CONFIG_RENDER ?= .github/scripts/render_repo_configs.py
BIJUX_STANDARD_RENDERED_FILES ?= \
	.github/release.env \
	.github/dependabot.yml \
	.github/labeler.yml \
	.github/codecov.yml \
	.github/required-status-checks.md \
	.github/rulesets/main-branch-protection.json \
	.github/workflows/ci.yml \
	.github/workflows/verify.yml
BIJUX_STANDARD_REQUIRED_FILES ?= \
	automation-identity.md \
	workflows/deploy-docs.yml
BIJUX_PY_REQUIRED_FILES ?= api-contract.mk api-freeze.mk api-live-contract.mk api.mk bijux.mk package.mk package-catalog.mk ci/build.mk ci/docs.mk ci/help.mk ci/lint.mk ci/quality.mk ci/sbom.mk ci/security.mk ci/test.mk ci/util.mk config/python-baseline.toml repository/artifact_aliases.py repository/badge_renderer.py repository/configuration_baseline.py repository/config-layout.mk repository/env.mk repository/make-layout.mk repository/publish.mk repository/sbom_provenance.py repository/root.mk root/docs.mk root/env.mk root/lifecycle.mk root/package-dispatch.mk
BIJUX_PY_OPTIONAL_FILES ?=

.PHONY: check-bijux-standard bijux-standard-sync bijux-standard-check

check-bijux-standard: ## Verify the local mirror and same-standard sibling parity
	@set -eu; \
	current_repo="$(PROJECT_SLUG)"; \
	workspace_dir="$(BIJUX_PY_WORKSPACE_DIR)"; \
	current_system_dir="$$workspace_dir/$$current_repo/$(BIJUX_PY_SYSTEM_REL)"; \
	current_local_dir="$$workspace_dir/$$current_repo/$(BIJUX_PY_LOCAL_REL)"; \
	current_pin_file="$$workspace_dir/$$current_repo/$(BIJUX_PY_STD_PIN_REL)"; \
	compared_repos=0; \
	[ -d "$$current_system_dir" ] || { echo "✘ Missing shared make directory: $$current_system_dir"; exit 2; }; \
	[ -d "$$current_local_dir" ] || { echo "✘ Missing local make directory: $$current_local_dir"; exit 2; }; \
	[ -f "$$current_pin_file" ] || { echo "✘ Missing accepted standard pin: $$current_pin_file"; exit 2; }; \
	for file in $(BIJUX_PY_REQUIRED_FILES); do \
	  [ -f "$$current_system_dir/$$file" ] || { echo "✘ Missing $$current_system_dir/$$file"; exit 2; }; \
	  [ -f "$$current_local_dir/$$file" ] || { echo "✘ Missing $$current_local_dir/$$file"; exit 2; }; \
	  cmp -s "$$current_system_dir/$$file" "$$current_local_dir/$$file" || { echo "✘ Local bijux-py drift: $$file differs between $(BIJUX_PY_SYSTEM_REL) and $(BIJUX_PY_LOCAL_REL) in $$current_repo"; exit 1; }; \
	done; \
	for file in $(BIJUX_PY_OPTIONAL_FILES); do \
	  if [ -f "$$current_system_dir/$$file" ] && [ -f "$$current_local_dir/$$file" ]; then \
	    cmp -s "$$current_system_dir/$$file" "$$current_local_dir/$$file" || { echo "✘ Local bijux-py drift: $$file differs between $(BIJUX_PY_SYSTEM_REL) and $(BIJUX_PY_LOCAL_REL) in $$current_repo"; exit 1; }; \
	  fi; \
	done; \
	for repo in $(BIJUX_PY_REPOS); do \
	  [ "$$repo" = "$$current_repo" ] && continue; \
	  other_system_dir="$$workspace_dir/$$repo/$(BIJUX_PY_SYSTEM_REL)"; \
	  other_pin_file="$$workspace_dir/$$repo/$(BIJUX_PY_STD_PIN_REL)"; \
	  if [ ! -d "$$other_system_dir" ]; then \
	    echo "→ Skipping sibling shared make check for $$repo; $$other_system_dir is not present"; \
	    continue; \
	  fi; \
	  if [ ! -f "$$other_pin_file" ]; then \
	    echo "→ Skipping sibling shared make check for $$repo; accepted standard pin is not present"; \
	    continue; \
	  fi; \
	  if ! cmp -s "$$current_pin_file" "$$other_pin_file"; then \
	    echo "→ Skipping sibling shared make check for $$repo; accepted standard pins differ"; \
	    continue; \
	  fi; \
	  compared_repos=$$((compared_repos + 1)); \
	  for file in $(BIJUX_PY_REQUIRED_FILES); do \
	    [ -f "$$other_system_dir/$$file" ] || { echo "✘ Missing $$other_system_dir/$$file"; exit 2; }; \
	    cmp -s "$$current_system_dir/$$file" "$$other_system_dir/$$file" || { echo "✘ Shared make drift: $$file differs between $$current_repo and $$repo"; exit 1; }; \
	  done; \
	  for file in $(BIJUX_PY_OPTIONAL_FILES); do \
	    if [ -f "$$current_system_dir/$$file" ] && [ -f "$$other_system_dir/$$file" ]; then \
	      cmp -s "$$current_system_dir/$$file" "$$other_system_dir/$$file" || { echo "✘ Shared make drift: $$file differs between $$current_repo and $$repo"; exit 1; }; \
	    fi; \
	  done; \
	done; \
	if [ "$$compared_repos" -eq 0 ]; then \
	  echo "✔ bijux-py modules match the local synchronized source; no available sibling uses the same accepted standard"; \
	else \
	  echo "✔ bijux-py modules match across $$compared_repos siblings on the same accepted standard"; \
	fi

bijux-standard-sync: ## Synchronize shared GitHub governance files into .github/
	@set -eu; \
	shared_dir="$(PROJECT_DIR)/$(BIJUX_STANDARD_SHARED_DIR)"; \
	[ -d "$$shared_dir" ] || { echo "✘ Missing shared governance directory: $$shared_dir"; exit 2; }; \
	for rel in $(BIJUX_STANDARD_REQUIRED_FILES); do \
	  src="$$shared_dir/$$rel"; \
	  dst="$(PROJECT_DIR)/.github/$$rel"; \
	  [ -f "$$src" ] || { echo "✘ Missing governance source file: $$src"; exit 2; }; \
	  mkdir -p "$$(dirname "$$dst")"; \
	  cp "$$src" "$$dst"; \
	  echo "→ synced .github/$$rel"; \
	done; \
	render_script="$(PROJECT_DIR)/$(BIJUX_STANDARD_CONFIG_RENDER)"; \
	[ -f "$$render_script" ] || { echo "✘ Missing repo config renderer: $$render_script"; exit 2; }; \
	python3 "$$render_script" --repo "$(PROJECT_SLUG)"; \
	echo "→ rendered managed repository config files"; \
	echo "✔ .github governance files synchronized from $(BIJUX_STANDARD_SHARED_DIR)"

bijux-standard-check: ## Verify .github governance files match shared GitHub governance sources
	@set -eu; \
	shared_dir="$(PROJECT_DIR)/$(BIJUX_STANDARD_SHARED_DIR)"; \
	[ -d "$$shared_dir" ] || { echo "✘ Missing shared governance directory: $$shared_dir"; exit 2; }; \
	for rel in $(BIJUX_STANDARD_REQUIRED_FILES); do \
	  src="$$shared_dir/$$rel"; \
	  dst="$(PROJECT_DIR)/.github/$$rel"; \
	  [ -f "$$src" ] || { echo "✘ Missing governance source file: $$src"; exit 2; }; \
	  [ -f "$$dst" ] || { echo "✘ Missing governed file: $$dst"; echo "  Run: make bijux-standard-sync"; exit 2; }; \
	  cmp -s "$$src" "$$dst" || { echo "✘ Governance drift: .github/$$rel differs from $(BIJUX_STANDARD_SHARED_DIR)/$$rel"; echo "  Run: make bijux-standard-sync"; exit 1; }; \
	done; \
	render_script="$(PROJECT_DIR)/$(BIJUX_STANDARD_CONFIG_RENDER)"; \
	[ -f "$$render_script" ] || { echo "✘ Missing repo config renderer: $$render_script"; exit 2; }; \
	tmp_dir="$$(mktemp -d)"; \
	restore_rendered() { \
	  for rel in $(BIJUX_STANDARD_RENDERED_FILES); do \
	    backup="$$tmp_dir/original/$$rel"; \
	    dst="$(PROJECT_DIR)/$$rel"; \
	    if [ -f "$$backup" ]; then \
	      mkdir -p "$$(dirname "$$dst")"; \
	      cp "$$backup" "$$dst"; \
	    else \
	      rm -f "$$dst"; \
	    fi; \
	  done; \
	  rm -rf "$$tmp_dir"; \
	}; \
	trap 'restore_rendered' EXIT INT TERM; \
	for rel in $(BIJUX_STANDARD_RENDERED_FILES); do \
	  src="$(PROJECT_DIR)/$$rel"; \
	  if [ -f "$$src" ]; then \
	    mkdir -p "$$tmp_dir/original/$$(dirname "$$rel")"; \
	    cp "$$src" "$$tmp_dir/original/$$rel"; \
	  fi; \
	done; \
	python3 "$$render_script" --repo "$(PROJECT_SLUG)"; \
	if [[ -n "$$(git status --short -- $(BIJUX_STANDARD_RENDERED_FILES))" ]]; then \
	  git status --short -- $(BIJUX_STANDARD_RENDERED_FILES); \
	  echo "✘ Governance drift: rendered repository config files are stale"; \
	  echo "  Run: make bijux-standard-sync"; \
	  exit 1; \
	fi; \
	echo "✔ .github governance files match shared $(BIJUX_STANDARD_SHARED_DIR) sources"

.PHONY: check-shared-bijux-py bijux-gh-py-sync bijux-gh-py-check
check-shared-bijux-py: check-bijux-standard ## Backward-compatible alias

bijux-gh-py-sync: bijux-standard-sync ## Backward-compatible alias

bijux-gh-py-check: bijux-standard-check ## Backward-compatible alias
