define run_make_targets
	@if [ -n "$(strip $(1))" ]; then \
	  for target in $(1); do \
	    echo "→ Running $$target"; \
	    $(2) "$$target" || exit $$?; \
	  done; \
	fi
endef

define clean_paths
	@if [ -n "$(strip $(1))" ]; then \
	  rm -rf $(1); \
	fi
endef
