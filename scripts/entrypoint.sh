#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="/root/.notebooklm-mcp-cli"
GUI_ENABLE="${NLM_GUI_ENABLE:-1}"
PRESTART_CHROMIUM="${NLM_PRESTART_CHROMIUM:-0}"
PORT="${PORT:-8080}"
DISPLAY="${DISPLAY:-:99}"
NLM_VNC_PORT="${NLM_VNC_PORT:-5900}"
NLM_NOVNC_PORT="${NLM_NOVNC_PORT:-6080}"

mkdir -p "${STATE_DIR}"

if [ "${GUI_ENABLE}" = "1" ]; then
  echo "[entrypoint] starting Xvfb on ${DISPLAY}"
  Xvfb "${DISPLAY}" -screen 0 1920x1080x24 &

  echo "[entrypoint] starting x11vnc on :${NLM_VNC_PORT}"
  x11vnc -display "${DISPLAY}" -rfbport "${NLM_VNC_PORT}" -forever -shared -nopw &

  if command -v novnc_proxy >/dev/null 2>&1; then
    echo "[entrypoint] starting noVNC on :${NLM_NOVNC_PORT}"
    novnc_proxy --vnc "localhost:${NLM_VNC_PORT}" --listen "${NLM_NOVNC_PORT}" &
  elif [ -x /usr/share/novnc/utils/novnc_proxy ]; then
    echo "[entrypoint] starting noVNC on :${NLM_NOVNC_PORT}"
    /usr/share/novnc/utils/novnc_proxy --vnc "localhost:${NLM_VNC_PORT}" --listen "${NLM_NOVNC_PORT}" &
  else
    echo "[entrypoint] noVNC launcher not found, skip"
  fi
fi

if [ "${PRESTART_CHROMIUM}" = "1" ]; then
  echo "[entrypoint] prestarting chromium"
  chromium --headless=new --no-sandbox --disable-setuid-sandbox --disable-dev-shm-usage --dump-dom about:blank >/dev/null
fi

echo "[entrypoint] starting API on :${PORT}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
