# GitHub Actions entrypoints.
# Keep workflow files thin by routing shell logic through make.

GH_DOCS_PAGES_DIR ?= artifacts/docs/docs/artifacts
GH_RELEASE_TAG_PATTERN ?= ^v[0-9]+\.[0-9]+\.[0-9]+$$
GH_CRATES_RELEASE_PACKAGES ?= bijux-dag-core bijux-dag-artifacts bijux-dag-runtime bijux-dag-app bijux-dag-cli bijux-cli
GH_RELEASE_CI_WORKFLOW_FILE ?= ci.yml
GH_RELEASE_CI_WAIT_TIMEOUT_SECONDS ?= 1800
GH_RELEASE_CI_POLL_INTERVAL_SECONDS ?= 15
GH_RELEASE_CI_LOOKBACK_SECONDS ?= 120
GH_RELEASE_CI_APPEARANCE_GRACE_SECONDS ?= 20
GH_SECURITY_CARGO_DENY_VERSION ?= 0.18.3
GH_SECURITY_CARGO_AUDIT_VERSION ?= 0.22.1
GH_TEST_CARGO_NEXTEST_VERSION ?= 0.9.100

.PHONY: gh-fmt gh-lint gh-security gh-audit gh-test gh-release-validate \
	docs-artifact-pages docs-artifact-pages-check gh-docs-install gh-docs-configure-git \
	gh-security-install-rust-tools gh-test-install-rust-tools \
	gh-release-plan-github gh-release-plan-pypi gh-release-plan-crates \
	gh-release-require-cargo-token gh-release-wait-for-ci

##@ GitHub
gh-fmt: install fmt-rs fmt-check-py ## Run GitHub formatting checks without modifying files

gh-lint: install lint-rs lint-check-py ## Run GitHub lint checks without modifying files

gh-security: install security ## Run GitHub security checks

gh-audit: gh-security ## Compatibility alias for GitHub security checks

gh-test: install test ## Run GitHub test suites

gh-release-validate: install release-validate-rs ## Run the canonical release validation suite in GitHub Actions

gh-security-install-rust-tools: ## Install Rust security tools that match the pinned CI toolchain
	@cargo install --locked cargo-deny --version "$(GH_SECURITY_CARGO_DENY_VERSION)"
	@cargo install --locked cargo-audit --version "$(GH_SECURITY_CARGO_AUDIT_VERSION)"

gh-test-install-rust-tools: ## Install cargo-nextest that matches the pinned CI toolchain
	@cargo install --locked cargo-nextest --version "$(GH_TEST_CARGO_NEXTEST_VERSION)"

docs-artifact-pages: ## Generate documentation pages that summarize release artifacts
	@set -euo pipefail; \
	pages_dir="$(GH_DOCS_PAGES_DIR)"; \
	mkdir -p "$${pages_dir}"; \
	{ \
		echo "# Generated Artifact Snapshot"; \
		echo; \
		echo "This release site summarizes the artifact directories available at docs build time."; \
		echo; \
		echo "- [Rust lane artifacts](rust.md)"; \
		echo "- [Python lane artifacts](python.md)"; \
		echo "- [Documentation artifacts](docs.md)"; \
	} > "$${pages_dir}/index.md"; \
	for page in rust python docs; do \
		case "$${page}" in \
			rust) source_dir="artifacts/rust" ;; \
			python) source_dir="artifacts/python" ;; \
			docs) source_dir="artifacts/docs" ;; \
		esac; \
		title="$$(printf '%s' "$${page}" | tr '[:lower:]' '[:upper:]' | sed 's/^/Artifact Snapshot: /')"; \
		{ \
			printf '# %s\n\n' "$${title}"; \
			printf 'Source directory: `%s`\n\n' "$${source_dir}"; \
			if [ -d "$${source_dir}" ]; then \
				echo "Status: available"; \
				echo; \
				echo '```text'; \
				find "$${source_dir}" -mindepth 1 -maxdepth 4 | sort; \
				echo '```'; \
			else \
				echo "Status: not generated for this workflow run."; \
				echo; \
				echo "No files were present under \`$${source_dir}\`."; \
			fi; \
		} > "$${pages_dir}/$${page}.md"; \
	done

docs-artifact-pages-check: docs-artifact-pages ## Verify that generated release artifact pages exist
	@set -euo pipefail; \
	pages_dir="$(GH_DOCS_PAGES_DIR)"; \
	for page in index rust python docs; do \
		file="$${pages_dir}/$${page}.md"; \
		if [ ! -s "$${file}" ]; then \
			echo "missing generated docs page: $${file}" >&2; \
			exit 1; \
		fi; \
	done

gh-docs-configure-git: ## Configure the Git author identity for documentation deployment
	@git config user.name "github-actions[bot]"
	@git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

gh-release-plan-github: ## Determine whether the tagged commit should publish a GitHub Release
	@$(call require_var,GITHUB_OUTPUT)
	@$(call require_var,TARGET_SHA)
	@set -euo pipefail; \
	git fetch --tags --force --prune >/dev/null 2>&1; \
	tags="$$(git tag --points-at "$(TARGET_SHA)" | grep -E "$(GH_RELEASE_TAG_PATTERN)" || true)"; \
	if [ -z "$${tags}" ]; then \
		echo "publish=false" >> "$${GITHUB_OUTPUT}"; \
		exit 0; \
	fi; \
	tag="$$(printf '%s\n' "$${tags}" | head -n 1)"; \
	version="$${tag#v}"; \
	{ \
		echo "publish=true"; \
		echo "tag=$${tag}"; \
		echo "version=$${version}"; \
	} >> "$${GITHUB_OUTPUT}"

gh-release-plan-pypi: ## Determine whether the tagged commit should publish to PyPI
	@$(call require_var,GITHUB_OUTPUT)
	@$(call require_var,TARGET_SHA)
	@set -euo pipefail; \
	git fetch --tags --force --prune >/dev/null 2>&1; \
	tags="$$(git tag --points-at "$(TARGET_SHA)" | grep -E "$(GH_RELEASE_TAG_PATTERN)" || true)"; \
	if [ -z "$${tags}" ]; then \
		{ \
			echo "publish=false"; \
			echo "already_published=false"; \
		} >> "$${GITHUB_OUTPUT}"; \
		exit 0; \
	fi; \
	tag="$$(printf '%s\n' "$${tags}" | head -n 1)"; \
	version="$${tag#v}"; \
	status="$$(curl -s -o /dev/null -w '%{http_code}' "https://pypi.org/pypi/bijux-cli/$${version}/json" || true)"; \
	already_published=false; \
	publish=true; \
	if [ "$${status}" = "200" ]; then \
		already_published=true; \
		publish=false; \
	fi; \
	{ \
		echo "publish=$${publish}"; \
		echo "already_published=$${already_published}"; \
		echo "tag=$${tag}"; \
		echo "version=$${version}"; \
	} >> "$${GITHUB_OUTPUT}"

gh-release-plan-crates: ## Determine whether the tagged commit should publish workspace crates
	@$(call require_var,GITHUB_OUTPUT)
	@$(call require_var,TARGET_SHA)
	@set -euo pipefail; \
	git fetch --tags --force --prune >/dev/null 2>&1; \
	tags="$$(git tag --points-at "$(TARGET_SHA)" | grep -E "$(GH_RELEASE_TAG_PATTERN)" || true)"; \
	if [ -z "$${tags}" ]; then \
		echo "publish=false" >> "$${GITHUB_OUTPUT}"; \
		exit 0; \
	fi; \
	tag="$$(printf '%s\n' "$${tags}" | head -n 1)"; \
	version="$${tag#v}"; \
	unpublished=""; \
	for package in $(GH_CRATES_RELEASE_PACKAGES); do \
		status="$$(curl -s -o /dev/null -w '%{http_code}' "https://crates.io/api/v1/crates/$${package}/$${version}" || true)"; \
		if [ "$${status}" != "200" ]; then \
			if [ -n "$${unpublished}" ]; then unpublished="$${unpublished} "; fi; \
			unpublished="$${unpublished}$${package}"; \
		fi; \
	done; \
	if [ -z "$${unpublished}" ]; then \
		{ \
			echo "publish=false"; \
			echo "packages="; \
			echo "tag=$${tag}"; \
			echo "version=$${version}"; \
		} >> "$${GITHUB_OUTPUT}"; \
		exit 0; \
	fi; \
	{ \
		echo "publish=true"; \
		echo "packages=$${unpublished}"; \
		echo "tag=$${tag}"; \
		echo "version=$${version}"; \
	} >> "$${GITHUB_OUTPUT}"

gh-release-require-cargo-token: ## Verify that crates.io credentials are available
	@$(call require_var,CARGO_REGISTRY_TOKEN)

gh-release-wait-for-ci: ## Wait for the latest CI run on the release SHA to succeed
	@$(call require_var,GITHUB_TOKEN)
	@$(call require_var,GITHUB_REPOSITORY)
	@$(call require_var,TARGET_SHA)
	@$(call require_var,CI_WAIT_STARTED_AT)
	@GH_RELEASE_CI_WORKFLOW_FILE="$(GH_RELEASE_CI_WORKFLOW_FILE)" \
	GH_RELEASE_CI_WAIT_TIMEOUT_SECONDS="$(GH_RELEASE_CI_WAIT_TIMEOUT_SECONDS)" \
	GH_RELEASE_CI_POLL_INTERVAL_SECONDS="$(GH_RELEASE_CI_POLL_INTERVAL_SECONDS)" \
	GH_RELEASE_CI_LOOKBACK_SECONDS="$(GH_RELEASE_CI_LOOKBACK_SECONDS)" \
	GH_RELEASE_CI_APPEARANCE_GRACE_SECONDS="$(GH_RELEASE_CI_APPEARANCE_GRACE_SECONDS)" \
	python3 .github/scripts/wait_for_ci.py

include makes/docs-publication.mk
