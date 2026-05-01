.PHONY: verify-infra test-backend

verify-infra:
	./scripts/verify-infra.sh

# Requires Postgres reachable at DATABASE_URL (e.g. `docker compose up -d db`).
test-backend:
	@test -n "$$DATABASE_URL" || (echo "error: export DATABASE_URL (see .env.example)" >&2; exit 1)
	cd backend && python3 -m pip install -q -e ".[dev]" && python3 -m pytest tests/ -v
