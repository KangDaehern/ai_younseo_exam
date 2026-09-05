#!/usr/bin/env bash
set -euo pipefail

readonly PROJECT_DIR="/home/kd6/gitView/ai/ai_younseo_exam"
readonly WEB_DIR="${PROJECT_DIR}/web"
readonly STATE_DIR="${HOME}/.local/state/yunseo-study"
readonly PID_FILE="${STATE_DIR}/server.pid"
readonly LOG_FILE="${STATE_DIR}/server.log"
readonly PORT="8080"

mkdir -p "${STATE_DIR}"

if [[ -f "${PID_FILE}" ]]; then
  old_pid="$(cat "${PID_FILE}")"
  if [[ "${old_pid}" =~ ^[0-9]+$ ]] && kill -0 "${old_pid}" 2>/dev/null; then
    exit 0
  fi
  rm -f "${PID_FILE}"
fi

nohup python3 -m http.server "${PORT}" \
  --bind 0.0.0.0 \
  --directory "${WEB_DIR}" \
  >>"${LOG_FILE}" 2>&1 &

server_pid="$!"
echo "${server_pid}" > "${PID_FILE}"
sleep 1

if ! kill -0 "${server_pid}" 2>/dev/null; then
  echo "Static server failed to start. See ${LOG_FILE}." >&2
  exit 1
fi

echo "Yunseo study server is running on port ${PORT} (PID ${server_pid})."
