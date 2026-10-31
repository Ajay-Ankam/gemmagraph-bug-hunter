#!/usr/bin/env bash
# Deploy GemmaGraph Bug Hunter on a Cloudways server (SSH as the application user).
#
#   git clone https://github.com/Ajay-Ankam/gemmagraph-bug-hunter.git && cd gemmagraph-bug-hunter
#   cp .env.example .env && nano .env        # add GEMINI_API_KEY
#   bash deploy_cloudways.sh
#
# Steps: venv + requirements -> tests -> PM2 (Uvicorn workers) -> health check
#        -> pre-warm demo scans (instant cache hits when .scan_cache.json is committed).
# Re-running is safe: PM2 reloads with zero downtime.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8000}"
BASE="http://127.0.0.1:${PORT}"
PYTHON="${PYTHON:-python3}"
cd "$APP_DIR"

log()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# ── 1. Preflight ────────────────────────────────────────────────
command -v "$PYTHON" >/dev/null || fail "$PYTHON not found"
"$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 10))' || fail "Python 3.10+ required"
command -v git >/dev/null || fail "git not found (needed for GitHub scans)"
[[ -f .env ]] || fail ".env missing: cp .env.example .env and set GEMINI_API_KEY"
grep -q '^GEMINI_API_KEY=..*' .env && ! grep -q 'your_gemini_api_key_here' .env \
  || fail "GEMINI_API_KEY is not set in .env"
chmod 600 .env
mkdir -p logs

# ── 2. Python environment ───────────────────────────────────────
log "Creating virtualenv and installing requirements"
[[ -d .venv ]] || "$PYTHON" -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r backend/requirements-dev.txt

# ── 3. Tests (offline: served from the committed cache) ─────────
log "Running test suite"
.venv/bin/python -m pytest -q

# ── 4. PM2 ──────────────────────────────────────────────────────
if ! command -v pm2 >/dev/null; then
  log "Installing PM2"
  npm install -g pm2 >/dev/null 2>&1 || npm install --prefix "$HOME/.local" pm2 >/dev/null
  export PATH="$HOME/.local/bin:$HOME/.local/node_modules/.bin:$PATH"
fi
log "Starting Uvicorn under PM2 on 127.0.0.1:${PORT}"
PORT="$PORT" pm2 startOrReload ecosystem.config.js --update-env
pm2 save >/dev/null

# ── 5. Health check ─────────────────────────────────────────────
log "Waiting for /api/health"
for _ in $(seq 1 30); do
  curl -fsS "$BASE/api/health" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS "$BASE/api/health" || fail "Server did not become healthy; see logs/gemmagraph.err.log"
echo

# ── 6. Pre-warm demo scans ──────────────────────────────────────
for target in "demo_buggy_app" "."; do
  log "Pre-warming scan: ${target}"
  curl -fsS -o /dev/null -w "    HTTP %{http_code} in %{time_total}s\n" \
    -X POST "$BASE/api/scan" -H 'Content-Type: application/json' \
    --max-time 180 -d "{\"repo_url\": \"${target}\"}" \
    || echo "    (warm-up failed for ${target}; it will run live on first request)"
done

log "Deployed. Point your Cloudways application at ${BASE} (see README: Cloudways deployment)."
