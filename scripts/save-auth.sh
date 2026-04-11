#!/usr/bin/env bash
# save-auth.sh — auth_ok になるまで待ってアーカイブを保存する
# 使い方:
#   1. curl -X POST http://localhost:8080/reauth/start
#   2. VNC (http://<host>:6080) でGoogle認証を完了する
#   3. ./scripts/save-auth.sh  ← このスクリプトを実行 (ステップ1と並行でもOK)
set -euo pipefail

CONTAINER="${NLM_CONTAINER:-notebooklm-api3-nlm-api-1}"
ARCHIVE="${NLM_ARCHIVE:-$(dirname "$0")/../secrets/nlm-auth.tar.gz}"
API_URL="${NLM_API_URL:-http://localhost:8080}"
POLL_INTERVAL=10
TIMEOUT=600  # 10分

log() {
  echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') [save-auth] $*"
}

log "waiting for auth_ok (timeout=${TIMEOUT}s, interval=${POLL_INTERVAL}s)"
log "container: ${CONTAINER}"
log "archive:   ${ARCHIVE}"

elapsed=0
while true; do
  if auth_ok=$(curl -sf "${API_URL}/reauth/status" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['auth_ok'])" 2>/dev/null); then
    if [ "$auth_ok" = "True" ]; then
      break
    fi
  fi

  if [ "$elapsed" -ge "$TIMEOUT" ]; then
    log "ERROR: timed out after ${TIMEOUT}s — auth still not valid"
    exit 1
  fi

  log "auth not ready yet (${elapsed}s elapsed), retrying in ${POLL_INTERVAL}s..."
  sleep "$POLL_INTERVAL"
  elapsed=$((elapsed + POLL_INTERVAL))
done

log "auth_ok! exporting archive from container..."
docker exec "${CONTAINER}" \
  tar -czf /tmp/nlm-auth-export.tar.gz -C / root/.notebooklm-mcp-cli

# temp ファイルに受け取ってから移動することで sudo 不要にする
ARCHIVE_ABS="$(cd "$(dirname "$ARCHIVE")" && pwd)/$(basename "$ARCHIVE")"
TMPFILE="$(mktemp)"
docker cp "${CONTAINER}:/tmp/nlm-auth-export.tar.gz" "${TMPFILE}"
docker exec "${CONTAINER}" rm /tmp/nlm-auth-export.tar.gz
mv "${TMPFILE}" "${ARCHIVE_ABS}"

log "saved: ${ARCHIVE_ABS}"
log "done — next restart will use the new credentials"
