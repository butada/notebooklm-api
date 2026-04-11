#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="/root/.notebooklm-mcp-cli"
ARCHIVE_PATH="${NLM_AUTH_ARCHIVE:-/bootstrap/nlm-auth.tar.gz}"
FORCE_RESTORE="${NLM_FORCE_RESTORE_AUTH:-0}"
GUI_ENABLE="${NLM_GUI_ENABLE:-1}"
PRESTART_CHROMIUM="${NLM_PRESTART_CHROMIUM:-0}"
PORT="${PORT:-8080}"
DISPLAY="${DISPLAY:-:99}"
NLM_VNC_PORT="${NLM_VNC_PORT:-5900}"
NLM_NOVNC_PORT="${NLM_NOVNC_PORT:-6080}"

log() {
  echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') [entrypoint] $*"
}

mkdir -p "${STATE_DIR}"

is_state_empty=1
if [ -n "$(ls -A "${STATE_DIR}" 2>/dev/null)" ]; then
  is_state_empty=0
fi

if [ "${FORCE_RESTORE}" = "1" ] || [ "${is_state_empty}" = "1" ]; then
  if [ -f "${ARCHIVE_PATH}" ]; then
    log "restoring auth archive from ${ARCHIVE_PATH}"
    tar -xzf "${ARCHIVE_PATH}" -C /
  else
    log "auth archive not found, skip restore: ${ARCHIVE_PATH}"
  fi
fi

if [ "${GUI_ENABLE}" = "1" ]; then
  log "starting Xvfb on ${DISPLAY}"
  Xvfb "${DISPLAY}" -screen 0 1920x1080x24 &

  # Xvfbが起動するまで少し待ってからウィンドウマネージャーを起動
  sleep 1
  fluxbox &

  log "starting x11vnc on :${NLM_VNC_PORT}"
  x11vnc -display "${DISPLAY}" -rfbport "${NLM_VNC_PORT}" -forever -shared -nopw &

  if command -v novnc_proxy >/dev/null 2>&1; then
    log "starting noVNC on :${NLM_NOVNC_PORT}"
    novnc_proxy --vnc "localhost:${NLM_VNC_PORT}" --listen "${NLM_NOVNC_PORT}" &
  elif [ -x /usr/share/novnc/utils/novnc_proxy ]; then
    log "starting noVNC on :${NLM_NOVNC_PORT}"
    /usr/share/novnc/utils/novnc_proxy --vnc "localhost:${NLM_VNC_PORT}" --listen "${NLM_NOVNC_PORT}" &
  else
    log "noVNC launcher not found, skip"
  fi
fi

if [ "${PRESTART_CHROMIUM}" = "1" ]; then
  log "prestarting chromium on CDP port 9222"
  google-chrome --remote-debugging-port=9222 --no-first-run --no-default-browser-check --disable-extensions --remote-allow-origins=* about:blank &
  sleep 3
fi

log "$(nlm --version 2>&1)"
log "starting API on :${PORT}"

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" --log-config /app/app/log_config.json
