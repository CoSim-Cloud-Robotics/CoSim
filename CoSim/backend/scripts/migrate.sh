#!/usr/bin/env bash
#
# migrate.sh — Alembic migration helper for CoSim
#
# Usage:
#   ./scripts/migrate.sh migrate          Apply all pending migrations
#   ./scripts/migrate.sh rollback         Downgrade by one revision
#   ./scripts/migrate.sh check            Show current revision
#   ./scripts/migrate.sh status           Alias for check
#   ./scripts/migrate.sh dry-run          Print SQL without applying (--sql)
#   ./scripts/migrate.sh ci               CI mode: check + migrate + verify
#   ./scripts/migrate.sh new <message>    Create a new migration revision
#
# Environment:
#   COSIM_DATABASE_URL  Postgres connection string (required unless dry-run)
#   CI=true             Enables stricter error handling

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$BACKEND_DIR"

ALEMBIC_CMD="alembic"

# Colour helpers (disabled in CI or non-tty)
if [[ -t 1 ]] && [[ "${CI:-false}" != "true" ]]; then
    GREEN='\033[0;32m'
    RED='\033[0;31m'
    YELLOW='\033[0;33m'
    NC='\033[0m'
else
    GREEN='' RED='' YELLOW='' NC=''
fi

info()  { echo -e "${GREEN}[migrate]${NC} $*"; }
warn()  { echo -e "${YELLOW}[migrate]${NC} $*"; }
error() { echo -e "${RED}[migrate]${NC} $*" >&2; }

usage() {
    head -n 17 "$0" | tail -n 14 | sed 's/^# *//'
    exit 1
}

# ─── Commands ──────────────────────────────────────────────────────────────

cmd_migrate() {
    info "Applying all pending migrations …"
    $ALEMBIC_CMD upgrade head
    info "Done."
}

cmd_rollback() {
    info "Rolling back one migration …"
    $ALEMBIC_CMD downgrade -1
    info "Done."
}

cmd_check() {
    info "Current revision:"
    $ALEMBIC_CMD current
}

cmd_status() {
    cmd_check
}

cmd_dry_run() {
    info "Dry-run — generating SQL for upgrade to head …"
    $ALEMBIC_CMD upgrade head --sql
}

cmd_ci() {
    info "CI mode — checking current state …"
    $ALEMBIC_CMD current
    info "CI mode — applying pending migrations …"
    $ALEMBIC_CMD upgrade head
    info "CI mode — verifying final state …"
    $ALEMBIC_CMD current
    info "CI mode complete ✔"
}

cmd_new() {
    local msg="${1:?Usage: migrate.sh new <message>}"
    info "Creating new migration: $msg"
    $ALEMBIC_CMD revision --autogenerate -m "$msg"
}

# ─── Dispatch ──────────────────────────────────────────────────────────────

case "${1:-}" in
    migrate)   cmd_migrate ;;
    rollback)  cmd_rollback ;;
    check)     cmd_check ;;
    status)    cmd_status ;;
    dry-run)   cmd_dry_run ;;
    ci)        cmd_ci ;;
    new)       shift; cmd_new "$@" ;;
    -h|--help) usage ;;
    *)         error "Unknown command: ${1:-}"; usage ;;
esac
