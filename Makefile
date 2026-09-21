.PHONY: up down nuke ps logs psql

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
