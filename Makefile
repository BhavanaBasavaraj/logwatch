.PHONY: up down nuke ps logs psql migrate migrate-status

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
