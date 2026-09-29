#!/usr/bin/env bash
set -euo pipefail

# Run from the repo root no matter where the script is called from.
cd "$(dirname "$0")/.."

# Send SQL from stdin into psql, as one all-or-nothing transaction.
psql_in() {
  docker compose exec -T postgres sh -c \
    'psql -v ON_ERROR_STOP=1 -q -1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
}

# Send SQL from stdin and print just the bare result value.
psql_val() {
  docker compose exec -T postgres sh -c \
    'psql -v ON_ERROR_STOP=1 -tAq -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
}

if ! docker compose ps --status running --services | grep -q '^postgres$'; then
  echo "postgres is not running - run 'make up' first" >&2
  exit 1
fi

# The ledger of which migrations have already been applied.
echo "CREATE TABLE IF NOT EXISTS schema_migrations (
        version    text PRIMARY KEY,
        applied_at timestamptz NOT NULL DEFAULT now()
      );" | psql_in

shopt -s nullglob
for file in db/migrations/*.sql; do
  version="$(basename "$file" .sql)"

  applied="$(echo "SELECT 1 FROM schema_migrations WHERE version = '$version';" | psql_val)"
  if [ -n "$applied" ]; then
    echo "already applied : $version"
    continue
  fi

  echo "applying        : $version"
  {
    cat "$file"
    echo "INSERT INTO schema_migrations (version) VALUES ('$version');"
  } | psql_in
done

echo "migrations up to date"
