APP_DIR                         ?= src
API_BASE_PATH                   ?= /v1
API_APP                         ?= app
API_MODULE                      ?=
API_FACTORY                     ?=
API_WAIT_SECS                   ?= 30
HEALTH_PATH                     ?= /health
SCHEMA_URL                      ?= http://$(API_HOST):$(API_PORT)
SCHEMATHESIS_TIMEOUT            ?= 30
SCHEMATHESIS_JUNIT              ?= $(API_TEST_DIR)/schemathesis.xml
SCHEMATHESIS_JUNIT_ABS          := $(abspath $(SCHEMATHESIS_JUNIT))
SCHEMATHESIS_CFG                ?= $(MONOREPO_ROOT)/configs/schemathesis.toml
SCHEMATHESIS_CFG_ABS            := $(abspath $(SCHEMATHESIS_CFG))
SCHEMA_BUNDLE_DIR               ?= $(API_ARTIFACTS_DIR)/schemas
SCHEMA_BUNDLE_DIR_ABS           := $(abspath $(SCHEMA_BUNDLE_DIR))
HYPOTHESIS_DB_API               ?= $(API_TEST_DIR)/hypothesis
HYPOTHESIS_DB_API_ABS           := $(abspath $(HYPOTHESIS_DB_API))
API_NODE_DIR                    ?= $(API_ARTIFACTS_DIR)/node
API_NODE_DIR_ABS                := $(abspath $(API_NODE_DIR))
API_NODE_READY_MARKER           := $(API_NODE_DIR_ABS)/.deps-ok
REDOCLY_ABS                     := $(API_NODE_DIR_ABS)/node_modules/.bin/redocly
OPENAPI_GENERATOR_ABS           := $(API_NODE_DIR_ABS)/node_modules/.bin/openapi-generator-cli
ALL_API_SCHEMAS                 := $(shell if [ -d "$(API_DIR)" ]; then find "$(API_DIR)" -type f \( -name '*.yaml' -o -name '*.yml' \); fi)
ALL_API_SCHEMAS_ABS             := $(abspath $(ALL_API_SCHEMAS))
PRANCE                          ?= $(if $(ACT),$(ACT)/prance,prance)
OPENAPI_SPEC_VALIDATOR          ?= $(if $(ACT),$(ACT)/openapi-spec-validator,openapi-spec-validator)
SCHEMATHESIS                    ?= $(if $(ACT),$(ACT)/schemathesis,schemathesis)
API_PYTHON                      ?= $(VENV_PYTHON)
API_INSTALL_PYTHON_PACKAGES     ?= prance openapi-spec-validator uvicorn schemathesis
API_INSTALL_EDITABLE            ?= 0
API_ENABLE_NODE_TOOLS           ?= 1
API_SKIP_IF_NO_SCHEMAS          ?= 0
API_LINT_MISSING_MESSAGE        ?= ✘ No API schemas found under $(API_DIR)
API_TEST_MISSING_MESSAGE        ?= $(API_LINT_MISSING_MESSAGE)
API_DYNAMIC_PORT                ?= 0
API_VALIDATE_IN_NODE_DIR        ?= 0
API_NODE_BOOTSTRAP_MODE         ?= npm-install-fallback
OPENAPI_GENERATOR_NPM_PACKAGE   ?= @openapitools/openapi-generator-cli@7.14.0
OPENAPI_GENERATOR_FALLBACK_PACKAGE ?= @openapitools/openapi-generator-cli@latest
REDOCLY_NPM_PACKAGE             ?= @redocly/cli
OPENAPI_GENERATOR_JAR_VERSION   ?=
NODE_REQUIRED                   ?= 20
NODE_DIST_VERSION               ?= v20.18.0
API_NODE_PACKAGE_MANIFEST       ?= $(MONOREPO_ROOT)/configs/package.json
API_NODE_PACKAGE_MANIFEST_ABS   := $(abspath $(API_NODE_PACKAGE_MANIFEST))
API_NODE_LOCKFILE               ?= $(MONOREPO_ROOT)/configs/package-lock.json
API_NODE_LOCKFILE_ABS           := $(abspath $(API_NODE_LOCKFILE))
API_SCHEMATHESIS_FILTER_MODE    ?= none
API_OPENAPI_DRIFT_CHECK         ?=
API_OPENAPI_DRIFT_COMMAND       ?=
API_PYTHON_ENV                  ?= $(CANON_DEV_PYTHON_ENV)
API_ENABLE_REPRO                ?= 0
SCHEMATHESIS_OPTS               ?= \
  --checks=all --max-failures=1 \
  --report junit --report-junit-path $(SCHEMATHESIS_JUNIT_ABS) \
  --request-timeout=5 --max-response-time=3 \
  --max-examples=50 --seed=1 --generation-deterministic \
  --suppress-health-check=filter_too_much

ifneq ($(strip $(API_FACTORY)),)
API_SERVER_CMD ?= PYTHONPATH="$(APP_DIR)$${PYTHONPATH:+:$$PYTHONPATH}" \
  $(VENV_PYTHON) -c 'import sys, importlib, uvicorn, os; \
sys.path.insert(0,"$(APP_DIR)"); \
m=importlib.import_module("$(API_MODULE)"); \
app=getattr(m,"$(API_FACTORY)")(); \
uvicorn.run(app, host=os.environ["API_HOST"], port=int(os.environ["API_PORT"]))'
else
API_SERVER_CMD ?= PYTHONPATH="$(APP_DIR)$${PYTHONPATH:+:$$PYTHONPATH}" \
  $(VENV_PYTHON) -m uvicorn --app-dir "$(APP_DIR)" \
  $(API_MODULE):$(API_APP) --host "$${API_HOST}" --port "$${API_PORT}"
endif

define VALIDATE_ONE_SCHEMA
  @mkdir -p "$(API_LINT_DIR_ABS)"
  @schema_name="$$(basename "$(1)")"; \
  schema_abs="$(abspath $(1))"; \
  log_path="$(API_LINT_DIR_ABS)/$${schema_name}.log"; \
  echo "→ Validating: $(1)"; \
  { \
    set -e; \
    $(PRANCE) validate "$$schema_abs"; \
    $(OPENAPI_SPEC_VALIDATOR) "$$schema_abs"; \
    if [ "$(API_ENABLE_NODE_TOOLS)" = "1" ]; then \
      "$(REDOCLY_ABS)" lint "$$schema_abs"; \
      if [ "$(API_VALIDATE_IN_NODE_DIR)" = "1" ]; then \
        ( cd "$(API_NODE_DIR_ABS)" && NODE_NO_WARNINGS=1 "$(OPENAPI_GENERATOR_ABS)" validate -i "$$schema_abs" ); \
      else \
        NODE_NO_WARNINGS=1 "$(OPENAPI_GENERATOR_ABS)" validate -i "$$schema_abs"; \
      fi; \
    fi; \
  } 2>&1 | tee "$$log_path"
endef

.PHONY: api api-install api-lint api-test api-serve api-serve-bg api-stop api-clean node_deps api-repro openapi-drift

api: api-install api-lint api-test

openapi-drift:
	@if [ -n "$(strip $(API_OPENAPI_DRIFT_COMMAND))" ]; then \
	  $(API_PYTHON_ENV) $(API_OPENAPI_DRIFT_COMMAND); \
	elif [ -n "$(strip $(API_OPENAPI_DRIFT_CHECK))" ] && [ -f "$(API_OPENAPI_DRIFT_CHECK)" ]; then \
	  $(PYTHON) "$(API_OPENAPI_DRIFT_CHECK)"; \
	else \
	  echo "Skipping openapi-drift ($(API_OPENAPI_DRIFT_CHECK) missing)"; \
	fi

api-install: | $(VENV_PYTHON)
	@echo "→ Installing API Python deps..."
	@if [ "$(API_ENABLE_NODE_TOOLS)" = "1" ]; then $(API_SELF_MAKE) node_deps; fi
	@command -v curl >/dev/null || { echo "✘ curl not found"; exit 1; }
	@command -v java >/dev/null || { echo "✘ java not found"; exit 1; }
	@if [ -n "$(strip $(API_INSTALL_PYTHON_PACKAGES))" ]; then \
	  $(UV) pip install --python "$(VENV_PYTHON)" --quiet --upgrade $(API_INSTALL_PYTHON_PACKAGES); \
	fi
	@if [ "$(API_INSTALL_EDITABLE)" = "1" ]; then \
	  $(UV) pip install --python "$(VENV_PYTHON)" --quiet --editable .; \
	fi
	@echo "✔ API toolchain ready."

api-lint:
	@if [ "$(API_ENABLE_NODE_TOOLS)" = "1" ]; then $(API_SELF_MAKE) node_deps; fi
	@if [ -z "$(ALL_API_SCHEMAS)" ]; then \
	  if [ "$(API_SKIP_IF_NO_SCHEMAS)" = "1" ]; then echo "$(API_LINT_MISSING_MESSAGE)"; exit 0; fi; \
	  echo "$(API_LINT_MISSING_MESSAGE)"; exit 1; \
	fi
	@echo "→ Linting OpenAPI specs..."
	$(foreach s,$(ALL_API_SCHEMAS),$(call VALIDATE_ONE_SCHEMA,$(s)))
	@[ -f ./openapitools.json ] && echo "→ Removing stray openapitools.json (root)" && rm -f ./openapitools.json || true
	@echo "✔ All schemas validated. Logs → $(API_LINT_DIR_ABS)"

api-test: | $(VENV_PYTHON)
	@if [ "$(API_ENABLE_NODE_TOOLS)" = "1" ]; then $(API_SELF_MAKE) node_deps; fi
	@if [ -z "$(ALL_API_SCHEMAS)" ]; then \
	  if [ "$(API_SKIP_IF_NO_SCHEMAS)" = "1" ]; then echo "$(API_TEST_MISSING_MESSAGE)"; exit 0; fi; \
	  echo "$(API_TEST_MISSING_MESSAGE)"; exit 1; \
	fi
	@mkdir -p "$(API_ARTIFACTS_DIR_ABS)" "$(API_TEST_DIR_ABS)"
	@if [ "$(API_SCHEMATHESIS_FILTER_MODE)" = "warnings" ]; then \
	  FILTER_PATH="$(API_ARTIFACTS_DIR_ABS)/schemathesis_filter.py"; \
	  printf 'import sys\nskip=False\nfor line in sys.stdin:\n    if "WARNINGS" in line or line.startswith("Warnings:") or "validation mismatch" in line or line.strip().startswith("💡") or line.strip().startswith("- "):\n        skip=True\n        continue\n    if skip and (line.startswith("SUMMARY") or line.startswith("Test cases:") or line.strip() == ""):\n        skip=False\n        if line.startswith("SUMMARY") or line.startswith("Test cases:"):\n            print(line, end="")\n        continue\n    if not skip:\n        print(line, end="")\n' >"$$FILTER_PATH"; \
	fi
	@if [ "$(API_DYNAMIC_PORT)" = "1" ]; then \
	  PORT_FILE="$(API_ARTIFACTS_DIR_ABS)/.api_port"; \
	  $(VENV_PYTHON) -c 'import socket,sys; port=int(sys.argv[1]); s=socket.socket(); in_use=s.connect_ex(("127.0.0.1", port))==0; s.close(); s=socket.socket(); s.bind(("127.0.0.1", 0)); free=s.getsockname()[1]; s.close(); print(free if in_use else port)' "$(API_PORT)" >"$$PORT_FILE"; \
	  PORT="$$(cat "$$PORT_FILE")"; \
	  if [ "$$PORT" != "$(API_PORT)" ]; then echo "↪︎ Port $(API_PORT) busy; using $$PORT"; fi; \
	fi
	@echo "→ Starting API server"
	@script="$(API_ARTIFACTS_DIR_ABS)/run_api_test.sh"; \
	  rm -f "$$script"; \
	  echo '#!/usr/bin/env bash' >> "$$script"; \
	  echo 'set -euo pipefail' >> "$$script"; \
	  if [ "$(API_DYNAMIC_PORT)" = "1" ]; then \
	    echo 'PORT="$$(cat "$(API_ARTIFACTS_DIR_ABS)/.api_port")"' >> "$$script"; \
	  else \
	    echo 'PORT="$(API_PORT)"' >> "$$script"; \
	  fi; \
	  echo 'echo "→ Starting API server"' >> "$$script"; \
	  if [ -n "$(API_FACTORY)" ]; then \
	    printf '%s\n' 'API_HOST="$(API_HOST)" API_PORT="$$PORT" PYTHONPATH="$(APP_DIR)$${PYTHONPATH:+:$$PYTHONPATH}" "$(VENV_PYTHON)" -c '"'"'import sys, importlib, uvicorn, os; sys.path.insert(0,"$(APP_DIR)"); m=importlib.import_module("$(API_MODULE)"); app=getattr(m,"$(API_FACTORY)")(); uvicorn.run(app, host=os.environ["API_HOST"], port=int(os.environ["API_PORT"]))'"'"' >"$(abspath $(API_LOG))" 2>&1 & PID=$$!' >> "$$script"; \
	  else \
	    printf '%s\n' 'PYTHONPATH="$(APP_DIR)$${PYTHONPATH:+:$$PYTHONPATH}" "$(VENV_PYTHON)" -m uvicorn --app-dir "$(APP_DIR)" "$(API_MODULE):$(API_APP)" --host "$(API_HOST)" --port "$$PORT" >"$(abspath $(API_LOG))" 2>&1 & PID=$$!' >> "$$script"; \
	  fi; \
	  echo 'echo $$PID >"$(API_ARTIFACTS_DIR_ABS)/server.pid"' >> "$$script"; \
	  echo 'cleanup(){ kill $$PID >/dev/null 2>&1 || true; wait $$PID >/dev/null 2>&1 || true; }' >> "$$script"; \
	  echo 'trap cleanup EXIT INT TERM' >> "$$script"; \
	  echo 'SCHEMA_URL="http://$(API_HOST):$$PORT"' >> "$$script"; \
	  echo 'echo "→ Waiting up to $(API_WAIT_SECS)s for readiness @ $$SCHEMA_URL$(HEALTH_PATH)"' >> "$$script"; \
	  echo 'READY=' >> "$$script"; \
	  echo 'for i in $$(seq 1 $(API_WAIT_SECS)); do' >> "$$script"; \
	  echo '  if curl -fsS "$$SCHEMA_URL$(HEALTH_PATH)" >/dev/null 2>&1; then READY=1; break; fi' >> "$$script"; \
	  echo '  sleep 1' >> "$$script"; \
	  echo '  if ! kill -0 $$PID >/dev/null 2>&1; then echo "✘ API crashed — see $(abspath $(API_LOG))"; exit 1; fi' >> "$$script"; \
	  echo 'done' >> "$$script"; \
	  echo 'if [ -z "$$READY" ]; then echo "✘ API did not become ready in $(API_WAIT_SECS)s — see $(abspath $(API_LOG))"; exit 1; fi' >> "$$script"; \
	  echo 'BASE_FLAG=$$($(SCHEMATHESIS) run -h 2>&1 | grep -q " --url " && echo --url || echo --base-url)' >> "$$script"; \
	  echo 'STATEFUL_ARGS=""' >> "$$script"; \
	  echo 'if $(SCHEMATHESIS) run -h 2>&1 | grep -q " --stateful"; then STATEFUL_ARGS="--stateful=links"; else echo "↪︎ Schemathesis: --stateful not supported; skipping"; fi' >> "$$script"; \
	  echo 'CFG="$(SCHEMATHESIS_CFG_ABS)"; [ -f "$$CFG" ] || CFG=""' >> "$$script"; \
	  echo 'CFG_ARG=""; [ -n "$$CFG" ] && CFG_ARG="--config-file=$$CFG"' >> "$$script"; \
	  echo 'LOG="$(API_TEST_DIR_ABS)/schemathesis.log"; : > "$$LOG"' >> "$$script"; \
	  echo 'BUF=""; command -v stdbuf >/dev/null 2>&1 && BUF="stdbuf -oL -eL"' >> "$$script"; \
	  echo 'TO=""' >> "$$script"; \
	  echo 'if [ "$(SCHEMATHESIS_TIMEOUT)" -gt 0 ] 2>/dev/null; then' >> "$$script"; \
	  echo '  if command -v gtimeout >/dev/null 2>&1; then TO="gtimeout --kill-after=10 $(SCHEMATHESIS_TIMEOUT)";' >> "$$script"; \
	  echo '  elif command -v timeout >/dev/null 2>&1; then TO="timeout --kill-after=10 $(SCHEMATHESIS_TIMEOUT)";' >> "$$script"; \
	  echo '  fi' >> "$$script"; \
	  echo 'fi' >> "$$script"; \
	  echo 'if [ -n "$$TO" ]; then echo "↪︎ Using timeout wrapper: $$TO"; else echo "↪︎ No timeout wrapper in use"; fi' >> "$$script"; \
	  echo 'echo "→ Running Schemathesis against: $$SCHEMA_URL$(API_BASE_PATH)"' >> "$$script"; \
	  echo 'EXIT_CODE=0' >> "$$script"; \
	  echo 'SCHEMA_BIN="$(SCHEMATHESIS)"; case "$$SCHEMA_BIN" in /*) ;; *) SCHEMA_BIN="$$(command -v "$$SCHEMA_BIN")";; esac' >> "$$script"; \
	  echo 'tmpdir=$$(mktemp -d); trap "rm -rf $$tmpdir" EXIT; cd "$$tmpdir"' >> "$$script"; \
	  echo 'for schema in $(ALL_API_SCHEMAS_ABS); do' >> "$$script"; \
	  echo '  echo "  • $$schema" | tee -a "$$LOG"' >> "$$script"; \
	  echo '  set +e' >> "$$script"; \
	  if [ "$(API_SCHEMATHESIS_FILTER_MODE)" = "warnings" ]; then \
	    echo '  FILTER_PATH="$(API_ARTIFACTS_DIR_ABS)/schemathesis_filter.py"' >> "$$script"; \
	    echo '  ( $$TO $$BUF "$$SCHEMA_BIN" $$CFG_ARG run "$$schema" $$BASE_FLAG "$$SCHEMA_URL$(API_BASE_PATH)" $(SCHEMATHESIS_OPTS) $$STATEFUL_ARGS 2>&1 || [ $$? -eq 124 ] ) | $(API_PYTHON) "$$FILTER_PATH" | tee -a "$$LOG"' >> "$$script"; \
	  else \
	    echo '  ( $$TO $$BUF "$$SCHEMA_BIN" $$CFG_ARG run "$$schema" $$BASE_FLAG "$$SCHEMA_URL$(API_BASE_PATH)" $(SCHEMATHESIS_OPTS) $$STATEFUL_ARGS 2>&1 || [ $$? -eq 124 ] ) | tee -a "$$LOG"' >> "$$script"; \
	  fi; \
	  echo '  rc=$${PIPESTATUS[0]}' >> "$$script"; \
	  echo '  set -e' >> "$$script"; \
	  echo '  if [ $$rc -ne 0 ] && [ $$EXIT_CODE -eq 0 ]; then EXIT_CODE=$$rc; fi' >> "$$script"; \
	  echo 'done' >> "$$script"; \
	  echo 'echo "→ Stopping API server"' >> "$$script"; \
	  echo 'cleanup' >> "$$script"; \
	  echo 'if [ $$EXIT_CODE -ne 0 ]; then echo "✘ Schemathesis reported failures (exit $$EXIT_CODE)"; fi' >> "$$script"; \
	  echo 'exit $$EXIT_CODE' >> "$$script"; \
	  chmod +x "$$script"; "$$script"
	@[ -f ./openapitools.json ] && echo "→ Removing stray openapitools.json (root)" && rm -f ./openapitools.json || true
	@echo "✔ Schemathesis finished. Log → $(API_TEST_DIR_ABS)/schemathesis.log"
	@[ -f "$(SCHEMATHESIS_JUNIT)" ] && echo "  JUnit → $(SCHEMATHESIS_JUNIT)" || true
	@if [ -d .hypothesis ] && [ ! -L .hypothesis ]; then \
	  echo "✘ Refusing to delete legacy .hypothesis; run make artifact-aliases-migrate from the repository root"; \
	  exit 2; \
	fi

api-serve: | $(VENV_PYTHON)
	@mkdir -p "$(API_ARTIFACTS_DIR_ABS)"
	@echo "→ Serving API (foreground) @ $(SCHEMA_URL) — logs → $(abspath $(API_LOG))"
	@API_HOST="$(API_HOST)" API_PORT="$(API_PORT)" $(API_SERVER_CMD)

api-serve-bg: | $(VENV_PYTHON)
	@mkdir -p "$(API_ARTIFACTS_DIR_ABS)"
	@echo "→ Serving API (background) @ $(SCHEMA_URL) — logs → $(abspath $(API_LOG))"
	@API_HOST="$(API_HOST)" API_PORT="$(API_PORT)" $(API_SERVER_CMD) >"$(abspath $(API_LOG))" 2>&1 & echo $$! >"$(API_ARTIFACTS_DIR_ABS)/server.pid"
	@echo "PID $$(cat "$(API_ARTIFACTS_DIR_ABS)/server.pid")"

api-stop:
	@if [ -f "$(API_ARTIFACTS_DIR_ABS)/server.pid" ]; then \
	  PID=$$(cat "$(API_ARTIFACTS_DIR_ABS)/server.pid"); \
	  echo "→ Stopping PID $$PID"; \
	  kill $$PID >/dev/null 2>&1 || true; \
	  wait $$PID >/dev/null 2>&1 || true; \
	  rm -f "$(API_ARTIFACTS_DIR_ABS)/server.pid"; \
	else \
	  echo "→ No server.pid found (nothing to stop)"; \
	fi

node_deps: $(API_NODE_READY_MARKER)

$(API_NODE_READY_MARKER):
	@if [ "$(API_ENABLE_NODE_TOOLS)" != "1" ]; then \
	  echo "→ Node toolchain not required for $(PROJECT_SLUG)"; \
	  exit 0; \
	fi
	@mkdir -p "$(API_NODE_DIR_ABS)" "$(API_NODE_DIR_ABS)/.npm-cache"
	@case "$(API_NODE_BOOTSTRAP_MODE)" in \
	  npm-install-fallback) \
	    command -v npm >/dev/null || { echo "✘ npm not found"; exit 1; }; \
	    echo "→ Bootstrapping Node toolchain in $(API_NODE_DIR_ABS)"; \
	    cd "$(API_NODE_DIR_ABS)" && { test -f package.json || npm init -y >/dev/null; }; \
	    PKG="$(OPENAPI_GENERATOR_NPM_PACKAGE)"; \
	    if ! npm view "$$PKG" version >/dev/null 2>&1; then \
	      echo "↪︎ Requested version not on npm; using $(OPENAPI_GENERATOR_FALLBACK_PACKAGE)"; \
	      PKG="$(OPENAPI_GENERATOR_FALLBACK_PACKAGE)"; \
	    fi; \
	    cd "$(API_NODE_DIR_ABS)" && { \
	      NPM_CONFIG_CACHE="$(API_NODE_DIR_ABS)/.npm-cache" \
	      npm install --no-fund --no-audit --loglevel=info --save-dev --save-exact "$(REDOCLY_NPM_PACKAGE)" "$$PKG" > npm-install.log 2>&1 \
	        || { echo "✘ npm install failed — see $(API_NODE_DIR_ABS)/npm-install.log"; tail -n 200 npm-install.log; exit 1; }; \
	    } ;; \
	  npm-ci-sandbox) \
	    command -v npm >/dev/null || { echo "✘ npm not found"; exit 1; }; \
	    test -f "$(API_NODE_PACKAGE_MANIFEST_ABS)" || { echo "✘ Missing $(API_NODE_PACKAGE_MANIFEST_ABS)"; exit 1; }; \
	    test -f "$(API_NODE_LOCKFILE_ABS)" || { echo "✘ Missing $(API_NODE_LOCKFILE_ABS)"; exit 1; }; \
	    echo "→ Recreating Node toolchain sandbox in $(API_NODE_DIR_ABS)"; \
	    rm -rf "$(API_NODE_DIR_ABS)"/*; \
	    cp "$(API_NODE_PACKAGE_MANIFEST_ABS)" "$(API_NODE_DIR_ABS)/package.json"; \
	    cp "$(API_NODE_LOCKFILE_ABS)" "$(API_NODE_DIR_ABS)/package-lock.json"; \
	    cd "$(API_NODE_DIR_ABS)" && NPM_CONFIG_CACHE="$(API_NODE_DIR_ABS)/.npm-cache" npm ci --no-fund --no-audit --loglevel=info > npm-ci.log 2>&1 \
	      || { echo "✘ npm ci failed — see $(API_NODE_DIR_ABS)/npm-ci.log"; tail -n 200 "$(API_NODE_DIR_ABS)/npm-ci.log"; exit 1; } ;; \
	  npm-install-pinned) \
	    command -v npm >/dev/null || { echo "✘ npm not found"; exit 1; }; \
	    echo "→ Installing pinned Node toolchain in $(API_NODE_DIR_ABS)"; \
	    cd "$(API_NODE_DIR_ABS)" && { test -f package.json || npm init -y >/dev/null; }; \
	    PKG="$(OPENAPI_GENERATOR_NPM_PACKAGE)"; \
	    if [ -n "$(strip $(OPENAPI_GENERATOR_JAR_VERSION))" ]; then \
	      PKG="$(OPENAPI_GENERATOR_NPM_PACKAGE)"; \
	    elif ! npm view "$$PKG" version >/dev/null 2>&1; then \
	      echo "↪︎ Requested version not on npm; using $(OPENAPI_GENERATOR_FALLBACK_PACKAGE)"; \
	      PKG="$(OPENAPI_GENERATOR_FALLBACK_PACKAGE)"; \
	    fi; \
	    cd "$(API_NODE_DIR_ABS)" && { \
	      NPM_CONFIG_CACHE="$(API_NODE_DIR_ABS)/.npm-cache" \
	      npm install --no-fund --no-audit --loglevel=info --save-dev --save-exact "$(REDOCLY_NPM_PACKAGE)" "$$PKG" > npm-install.log 2>&1 \
	        || { echo "✘ npm install failed — see $(API_NODE_DIR_ABS)/npm-install.log"; tail -n 200 npm-install.log; exit 1; }; \
	    }; \
	    if [ -n "$(strip $(OPENAPI_GENERATOR_JAR_VERSION))" ]; then \
	      cd "$(API_NODE_DIR_ABS)" && OPENAPI_GENERATOR_VERSION="$(OPENAPI_GENERATOR_JAR_VERSION)" NODE_NO_WARNINGS=1 "$(OPENAPI_GENERATOR_ABS)" version-manager set "$(OPENAPI_GENERATOR_JAR_VERSION)" >/dev/null 2>&1 \
	        || { echo "✘ Failed to pin openapi-generator-cli jar to $(OPENAPI_GENERATOR_JAR_VERSION)"; exit 1; }; \
	    fi ;; \
	  *) echo "✘ Unknown API_NODE_BOOTSTRAP_MODE: $(API_NODE_BOOTSTRAP_MODE)"; exit 1 ;; \
	esac
	@touch "$(API_NODE_READY_MARKER)"

api-repro:
	@if [ "$(API_ENABLE_REPRO)" != "1" ]; then \
	  echo "→ API reproduction hints are disabled"; \
	  exit 0; \
	fi
	@echo "→ Reproduction hints are available in $(API_TEST_DIR_ABS)/schemathesis.log"

api-clean:
	@rm -rf "$(API_ARTIFACTS_DIR_ABS)" || true

##@ API
api:             ## Install the API toolchain, lint schemas, and run live API checks
api-install:     ## Install the package-local API toolchain
api-lint:        ## Validate every discovered OpenAPI schema
api-test:        ## Start the local API server and run schemathesis
api-serve:       ## Run the local API server in the foreground
api-serve-bg:    ## Run the local API server in the background
api-stop:        ## Stop the background API server if it is running
openapi-drift:   ## Check generated OpenAPI output against checked-in schemas
api-clean:       ## Remove API artifacts for this package
api-repro:       ## Print reproducibility guidance for API failures when enabled
