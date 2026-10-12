# Shared Bijux docs shell synchronization and contract enforcement.

# Prefer repository-managed Python interpreters so docs contract checks run in
# the same environment where docs dependencies were installed.
PYTHON_BIN ?= $(or $(VENV_PYTHON),$(DOCS_PYTHON_BIN),$(shell command -v python3 2>/dev/null))
BIJUX_DOCS_SYNC_SCRIPT ?= .bijux/shared/bijux-docs/tooling/scripts/sync_bijux_docs.sh
BIJUX_DOCS_SOT_GUARD ?= .bijux/shared/bijux-checks/scripts/verify-documentation-components.sh
BIJUX_DOCS_CONTRACT_GUARD ?= .bijux/shared/bijux-docs/tooling/quality/validate_bijux_docs_contract.py

.PHONY: bijux-docs-sync bijux-docs-check shell-sync shell-check

bijux-docs-sync: ## Synchronize shared Bijux docs shell into docs assets
	@bash "$(BIJUX_DOCS_SYNC_SCRIPT)"

bijux-docs-check: ## Validate Bijux docs shell contract and drift checks
	@"$(PYTHON_BIN)" "$(BIJUX_DOCS_CONTRACT_GUARD)" .
	@bash "$(BIJUX_DOCS_SOT_GUARD)"

# Backward-compatible aliases.
shell-sync: bijux-docs-sync ## Alias for bijux-docs-sync
shell-check: bijux-docs-check ## Alias for bijux-docs-check
