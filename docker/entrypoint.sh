#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Entrypoint do container. Aceita um "modo" como primeiro argumento:
#   worker      -> loop de agendamento (default)
#   migrate     -> aplica migrações Alembic e sai
#   collect     -> executa uma coleta única e sai
#   shell       -> shell interativo
#   <qualquer>  -> executa o comando literalmente
# ---------------------------------------------------------------------------
set -Eeuo pipefail

MODE="${1:-worker}"
shift || true

log() { printf '[entrypoint] %s\n' "$*" >&2; }

wait_for_db() {
  local attempts="${DB_WAIT_ATTEMPTS:-60}"
  local delay="${DB_WAIT_DELAY:-2}"
  local i
  for ((i = 1; i <= attempts; i++)); do
    if campinas-news db-ping >/dev/null 2>&1; then
      log "banco disponível (tentativa ${i})"
      return 0
    fi
    log "aguardando banco... (${i}/${attempts})"
    sleep "${delay}"
  done
  log "ERRO: banco não respondeu após ${attempts} tentativas"
  return 1
}

case "${MODE}" in
  worker)
    wait_for_db
    log "aplicando migrações"
    alembic upgrade head
    log "iniciando worker"
    exec campinas-news worker "$@"
    ;;
  migrate)
    wait_for_db
    exec alembic upgrade head "$@"
    ;;
  shell)
    exec /bin/bash "$@"
    ;;
  *)
    # Qualquer outro subcomando da CLI (collect, stats, sources, db-ping…)
    # roda após garantir schema atualizado.
    wait_for_db
    alembic upgrade head
    exec campinas-news "${MODE}" "$@"
    ;;
esac
