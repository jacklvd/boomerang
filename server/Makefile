# Quality gates for the Boomerang server. Everything the pre-commit hook runs is in `check`,
# so a developer or agent can reproduce the hook's verdict without staging anything.
#
# dev-note: `uv` manages this workspace — no pip, no requirements.txt (server/AGENTS.md).
# Every target goes through `uv run` so it uses the locked environment, not whatever the
# ambient interpreter happens to have.

.DEFAULT_GOAL := help
.PHONY: help install test cov lint fmt fmt-check typecheck audit check setup-hooks

UV := uv

help:  ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-14s\033[0m %s\n", $$1, $$2}'

install:  ## Sync the locked environment, dev dependencies included
	$(UV) sync --all-groups

test:  ## Run the test suite
	$(UV) run pytest

cov:  ## Run tests and enforce the 95% line + branch coverage floor
	$(UV) run pytest --cov --cov-report=term-missing

lint:  ## Lint (ruff, every rule minus the documented exceptions)
	$(UV) run ruff check .

fmt:  ## Auto-format and auto-fix in place
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

fmt-check:  ## Fail if anything is unformatted (no writes)
	$(UV) run ruff format --check .

typecheck:  ## Static analysis (mypy, strict)
	$(UV) run mypy

audit:  ## Scan runtime dependencies for known CVEs
	@# dev-note: pip-audit reads a requirements file, so the lockfile is exported to one
	@# rather than audited in place. --no-dev keeps the report to what actually ships.
	@tmp=$$(mktemp -t boomerang-reqs); \
	$(UV) export --frozen --no-dev --no-emit-project --format requirements.txt -q -o "$$tmp" && \
	$(UV) run pip-audit --disable-pip --progress-spinner=off -r "$$tmp"; \
	status=$$?; rm -f "$$tmp"; exit $$status

check: fmt-check lint typecheck cov audit  ## Everything the pre-commit hook enforces

setup-hooks:  ## Install the repo-wide git hooks (run once per clone)
	cd .. && ./scripts/setup-hooks.sh
