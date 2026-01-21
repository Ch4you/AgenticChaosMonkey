#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

LOCUSTFILE="${ROOT_DIR}/tests/performance/locustfile.py"
RESULTS_DIR="${ROOT_DIR}/reports/perf"
mkdir -p "${RESULTS_DIR}"

TARGET_HOST="${TARGET_HOST:-http://localhost:8001}"
TARGET_PATH="${TARGET_PATH:-/health}"
PROXY_URL="${PROXY_URL:-http://localhost:8080}"
TARGET_PORT="${TARGET_PORT:-8001}"
PROXY_PORT="${PROXY_PORT:-8080}"
WAIT_PATH="${WAIT_PATH:-/health}"

USERS="${USERS:-100}"
SPAWN_RATE="${SPAWN_RATE:-100}"
DURATION="${DURATION:-30s}"

BASELINE_CSV="${RESULTS_DIR}/baseline"
CHAOS_CSV="${RESULTS_DIR}/chaos"

PROXY_CONFIG_PATH="${PROXY_CONFIG_PATH:-${ROOT_DIR}/config/chaos_config.yaml}"
BASELINE_CONFIG="${BASELINE_CONFIG:-}"
CHAOS_CONFIG="${CHAOS_CONFIG:-}"

if ! command -v locust >/dev/null 2>&1; then
  echo "locust not found. Install with: pip install locust"
  exit 1
fi

wait_for_port() {
  local host="$1"
  local port="$2"
  local timeout="${3:-10}"
  local start
  start="$(date +%s)"

  while true; do
    if command -v nc >/dev/null 2>&1; then
      if nc -z "${host}" "${port}" >/dev/null 2>&1; then
        return 0
      fi
    else
      if curl --silent --fail "http://${host}:${port}${WAIT_PATH}" >/dev/null 2>&1; then
        return 0
      fi
    fi

    if (( $(date +%s) - start >= timeout )); then
      return 1
    fi
    sleep 0.2
  done
}

MOCK_SERVER_LOG="$(mktemp -t agent-chaos-mock-server.XXXXXX.log)"
PROXY_LOG="$(mktemp -t agent-chaos-proxy.XXXXXX.log)"
MOCK_SERVER_PID=""
PROXY_PID=""

cleanup() {
  if [[ -n "${PROXY_PID}" ]]; then
    kill "${PROXY_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${MOCK_SERVER_PID}" ]]; then
    kill "${MOCK_SERVER_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

start_mock_server() {
  python -m agent_chaos_sdk.tools.mock_server >"${MOCK_SERVER_LOG}" 2>&1 &
  MOCK_SERVER_PID="$!"
  if ! wait_for_port "localhost" "${TARGET_PORT}" 10; then
    echo "Mock server failed to start within 10s."
    echo "---- mock_server.log ----"
    tail -n 100 "${MOCK_SERVER_LOG}" || true
    exit 1
  fi
}

start_proxy() {
  mitmdump -s "${ROOT_DIR}/agent_chaos_sdk/proxy/addon.py" --listen-port "${PROXY_PORT}" >"${PROXY_LOG}" 2>&1 &
  PROXY_PID="$!"
  if ! wait_for_port "localhost" "${PROXY_PORT}" 10; then
    echo "Proxy failed to start within 10s."
    echo "---- proxy.log ----"
    tail -n 100 "${PROXY_LOG}" || true
    exit 1
  fi
}

extract_avg_latency_ms() {
  local csv_file="$1"
  awk -F',' 'NR>1 {
    if ($1=="Aggregated" || $1=="Total" || $2=="Aggregated" || $2=="Total") {
      print $6
      exit
    }
  }' "${csv_file}"
}

run_locust() {
  local prefix="$1"
  HTTP_PROXY="${PROXY_URL}" HTTPS_PROXY="${PROXY_URL}" TARGET_PATH="${TARGET_PATH}" \
    locust -f "${LOCUSTFILE}" \
      --headless \
      --host "${TARGET_HOST}" \
      -u "${USERS}" -r "${SPAWN_RATE}" -t "${DURATION}" \
      --csv "${prefix}" \
      --csv-full-history >/dev/null
}

swap_config_if_needed() {
  local src="$1"
  if [[ -n "${PROXY_CONFIG_PATH}" && -n "${src}" ]]; then
    cp "${src}" "${PROXY_CONFIG_PATH}"
    echo "Updated proxy config: ${PROXY_CONFIG_PATH} <= ${src}"
    sleep 2
  fi
}

echo "Starting mock server..."
start_mock_server

echo "Starting proxy..."
start_proxy

echo "Running baseline (no chaos)..."
swap_config_if_needed "${BASELINE_CONFIG}"
run_locust "${BASELINE_CSV}"
baseline_avg="$(extract_avg_latency_ms "${BASELINE_CSV}_stats.csv")"

echo "Running chaos..."
swap_config_if_needed "${CHAOS_CONFIG}"
run_locust "${CHAOS_CSV}"
chaos_avg="$(extract_avg_latency_ms "${CHAOS_CSV}_stats.csv")"

if [[ -z "${baseline_avg}" || -z "${chaos_avg}" ]]; then
  echo "Failed to parse latency from Locust CSV output."
  exit 1
fi

overhead_ms="$(awk -v c="${chaos_avg}" -v b="${baseline_avg}" 'BEGIN{printf "%.2f", c-b}')"

echo "Baseline Avg Latency (ms): ${baseline_avg}"
echo "Chaos Avg Latency (ms):    ${chaos_avg}"
echo "Overhead Latency (ms):     ${overhead_ms}"
