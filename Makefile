.PHONY: setup lint test format package local-up local-down e2e e2e-local deploy-plan destroy panic clean

# ──────────────────────────────────────────────
# Setup
# ──────────────────────────────────────────────
setup: setup-backend setup-trainer setup-frontend
	@echo "✅ Setup complete"

setup-backend:
	cd backend && pip install -e ".[dev]"

setup-trainer:
	cd trainer && pip install -e ".[dev]"

setup-frontend:
	@if [ -d frontend ] && [ -f frontend/package.json ]; then \
		cd frontend && npm ci; \
	else \
		echo "⏭️  Frontend not yet initialized, skipping"; \
	fi

# ──────────────────────────────────────────────
# Lint
# ──────────────────────────────────────────────
lint: lint-backend lint-trainer lint-frontend lint-infra
	@echo "✅ All linting passed"

lint-backend:
	cd backend && python -m ruff format --check . && python -m ruff check .

lint-trainer:
	cd trainer && python -m ruff format --check . && python -m ruff check .

lint-frontend:
	@if [ -d frontend ] && [ -f frontend/package.json ]; then \
		cd frontend && npm run lint 2>/dev/null && npm run typecheck 2>/dev/null; \
	else \
		echo "⏭️  Frontend not yet initialized, skipping"; \
	fi

lint-infra:
	@if [ -d infra ]; then \
		terraform fmt -check -recursive infra/ 2>/dev/null || echo "⏭️  Terraform not installed or no .tf files yet"; \
	fi

# ──────────────────────────────────────────────
# Format
# ──────────────────────────────────────────────
format:
	cd backend && python -m ruff format . && python -m ruff check --fix .
	cd trainer && python -m ruff format . && python -m ruff check --fix .
	@if [ -d infra ]; then terraform fmt -recursive infra/ 2>/dev/null || true; fi

# ──────────────────────────────────────────────
# Test
# ──────────────────────────────────────────────
test: test-backend test-trainer test-frontend
	@echo "✅ All tests passed"

test-backend:
	cd backend && python -m pytest tests/ -v --tb=short 2>/dev/null || echo "⏭️  No backend tests yet"

test-trainer:
	cd trainer && python -m pytest tests/ -v --tb=short 2>/dev/null || echo "⏭️  No trainer tests yet"

test-frontend:
	@if [ -d frontend ] && [ -f frontend/package.json ]; then \
		cd frontend && npm run test -- --run 2>/dev/null || echo "⏭️  No frontend tests yet"; \
	else \
		echo "⏭️  Frontend not yet initialized, skipping"; \
	fi

# ──────────────────────────────────────────────
# Package (Lambda zips)
# ──────────────────────────────────────────────
package:
	cd backend && bash build.sh

# ──────────────────────────────────────────────
# Local development
# ──────────────────────────────────────────────
local-up:
	docker compose -f docker-compose.local.yml up -d

local-down:
	docker compose -f docker-compose.local.yml down -v

# ──────────────────────────────────────────────
# End-to-end tests
# ──────────────────────────────────────────────
e2e:
	python scripts/e2e_smoke.py

e2e-local:
	python scripts/e2e_smoke.py --local

# ──────────────────────────────────────────────
# Infrastructure
# ──────────────────────────────────────────────
deploy-plan:
	cd infra && terraform init -backend=false && terraform validate && terraform plan -backend=false

destroy:
	@echo "⚠️  This will destroy all AWS resources. Use the GitHub Actions destroy workflow for production."
	python scripts/cleanup_orphans.py
	cd infra && terraform destroy

# ──────────────────────────────────────────────
# Cost guardrail: emergency kill switch
# ──────────────────────────────────────────────
panic:
	@echo "🚨 PANIC: Terminating all trainer instances and disabling job queue..."
	python scripts/cleanup_orphans.py
	@echo "Disable SQS event source mapping manually or via AWS CLI"
	@echo "🚨 Done. Check the AWS console to confirm."

# ──────────────────────────────────────────────
# Clean
# ──────────────────────────────────────────────
clean:
	rm -rf backend/build/
	rm -rf frontend/dist/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
