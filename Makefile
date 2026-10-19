.PHONY: up down nuke ps logs psql migrate migrate-status venv seed purge-synthetic api-rebuild api-logs

up:
	docker compose up -d --wait

down:
	docker compose down

nuke:
	docker compose down -v

ps:
	docker compose ps

logs:
	docker compose logs -f

psql:
	docker compose exec postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

migrate:
	./scripts/migrate.sh

migrate-status:
	docker compose exec postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -c "SELECT version, applied_at FROM schema_migrations ORDER BY version;"'

venv:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt

seed:
	.venv/bin/python scripts/seed.py $(ARGS)

purge-synthetic:
	.venv/bin/python scripts/seed.py --purge-only

api-rebuild:
	docker compose up -d --build api

api-logs:
	docker compose logs -f api
