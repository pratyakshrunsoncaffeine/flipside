PY ?= uv run --frozen python
UV_RUN ?= uv run --frozen

.PHONY: help test lint killtests g8 k5 replay-offline fixtures solo solo-all replay demo demo-down
help: ## List targets
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "%-12s %s\n", $$1, $$2}'

test: ## Run the test suite
	$(UV_RUN) pytest

lint: ## ruff and mypy
	$(UV_RUN) ruff check flipside tests docs/seal/example.py examples fixtures killtests demo
	$(UV_RUN) ruff format --check flipside tests docs/seal/example.py examples fixtures killtests demo
	$(UV_RUN) mypy
	$(UV_RUN) mypy --platform win32

g8: ## Offline check: q2-ok verifies OK, q2-forged gives PROOF_FAIL (no network, no Switch)
	$(PY) -m flipside.cli verify --bundle examples/seal.bundle --commit $$(cat examples/commit.txt) --manifest examples/manifest.json examples/q2-ok.json
	$(PY) -m flipside.cli verify --bundle examples/seal.bundle --commit $$(cat examples/commit.txt) --manifest examples/manifest.json examples/q2-forged.json; test $$? -eq 2

killtests: ## K1, K2 and K4 against the local Switch server; writes evidence/k1k2-*.log, k4-*.log
	cd killtests && python3 k1_k2.py && python3 k4.py

k5: ## K5: who Switch admits in Mattermost; needs `flip demo up`; writes evidence/k5-*.log
	cd killtests && python3 k5.py

k3: ## K3: approval card in Slack; needs a Slack connection on the local server and SLACK_BOT_TOKEN_FILE
	cd killtests && python3 k3.py

replay-offline: ## M2: CSV-export scenario over FakeTransport (room lane)
	$(PY) -m flipside.cli replay --offline

fixtures: ## M5: run all 9 fixture cases offline; writes docs/results/fixtures.md
	$(PY) -m flipside.cli replay --fixtures

solo: ## M3: two owners on the local Switch server, full flow over SwitchTransport (room lane)
	$(PY) -m flipside.cli solo

solo-all: ## M5: all 9 fixture cases live on the local Switch server; writes evidence/solo-all-*.log
	$(PY) -m flipside.cli solo --all

replay: ## M4: fresh local server, recorded inputs, no keys needed (room lane)
	$(PY) -m flipside.cli replay

demo: ## Switch 0.31.0 + Mattermost in Docker, people act in Mattermost; writes evidence/demo-mattermost-*.log
	$(PY) -m flipside.cli demo up
	$(PY) -m flipside.cli demo run

demo-down: ## Remove the demo containers, their data and .flipside-demo/
	$(PY) -m flipside.cli demo down
