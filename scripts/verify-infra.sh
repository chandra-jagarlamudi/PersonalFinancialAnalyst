#!/usr/bin/env bash
# Verifies issue #2 acceptance: compose config, Postgres readiness, connectivity,
# and data persistence across container restart (named volume).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_EXAMPLE="${ROOT}/.env.example"
COMPOSE_FILE="${ROOT}/compose.yaml"
TEARDOWN_VOLUMES=false
for arg in "$@"; do
  case "$arg" in
    --teardown-volumes) TEARDOWN_VOLUMES=true ;;
    -h|--help)
      echo "Usage: $0 [--teardown-volumes]"
      echo "  --teardown-volumes  Run 'docker compose down -v' after checks (removes pg volume)."
      exit 0
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "error: docker not found in PATH" >&2
  exit 1
fi

if [[ ! -f "$ENV_EXAMPLE" ]]; then
  echo "error: missing .env.example at $ENV_EXAMPLE" >&2
  exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "error: missing compose.yaml at $COMPOSE_FILE" >&2
  exit 1
fi

# shellcheck disable=SC1090
set -a && source "$ENV_EXAMPLE" && set +a

export ENV_FILE="$ENV_EXAMPLE"
DC=(docker compose --env-file "$ENV_EXAMPLE" -f "$COMPOSE_FILE")

# Track whether this script started the db (so we never tear down a pre-existing stack).
STACK_STARTED=0
cleanup() {
  local ec=$?
  trap - EXIT
  if [[ "$STACK_STARTED" -eq 1 ]]; then
    if [[ "$TEARDOWN_VOLUMES" == true ]]; then
      echo "==> docker compose down -v"
      "${DC[@]}" down -v || true
    else
      echo "==> docker compose down (volumes retained)"
      "${DC[@]}" down || true
    fi
  fi
  exit "$ec"
}
trap cleanup EXIT

mkdir -p "${RAW_STATEMENTS_HOST_PATH:-./data/raw-statements}"

echo "==> compose config"
"${DC[@]}" config -q

wait_for_db() {
  local attempts=60
  local i
  for ((i = 1; i <= attempts; i++)); do
    if "${DC[@]}" exec -T db pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "error: Postgres did not become ready within ${attempts}s" >&2
  return 1
}

# Detect whether the db container was already running before this script touched it.
# If it was, we leave it running on exit regardless of --teardown-volumes.
DB_WAS_RUNNING=0
if [[ -n "$("${DC[@]}" ps -q db 2>/dev/null)" ]]; then
  DB_WAS_RUNNING=1
fi

echo "==> compose up"
if "${DC[@]}" up -d --wait 2>/dev/null; then
  :
else
  "${DC[@]}" up -d
  wait_for_db
fi
# Only mark the stack for teardown if this script was the one that started it.
if [[ "$DB_WAS_RUNNING" -eq 0 ]]; then
  STACK_STARTED=1
fi

echo "==> connectivity (SELECT 1)"
"${DC[@]}" exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 -c "SELECT 1;" >/dev/null

echo "==> persistence marker + container restart"
"${DC[@]}" exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 -c "
CREATE TABLE IF NOT EXISTS _pfa_infra_issue2 (k text PRIMARY KEY, v text NOT NULL);
INSERT INTO _pfa_infra_issue2 (k, v) VALUES ('marker', 'issue2-persist')
  ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v;
" >/dev/null

"${DC[@]}" restart db >/dev/null

if "${DC[@]}" up -d --wait 2>/dev/null; then
  :
else
  wait_for_db
fi

marker="$("${DC[@]}" exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -At -c \
  "SELECT v FROM _pfa_infra_issue2 WHERE k = 'marker';")"
marker="$(echo "$marker" | tr -d '\r')"
if [[ "$marker" != "issue2-persist" ]]; then
  echo "error: expected persistence marker 'issue2-persist', got '${marker:-}'" >&2
  exit 1
fi

echo "==> raw statements mount visible in container"
"${DC[@]}" exec -T db sh -c "test -d '${RAW_STATEMENTS_CONTAINER_PATH:-/data/raw-statements}'"

echo "All infra checks passed."
