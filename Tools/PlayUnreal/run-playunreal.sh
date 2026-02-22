#!/usr/bin/env bash
# run-playunreal.sh — Launch game with Remote Control API and run a Python test script
#
# Usage:
#   ./Tools/PlayUnreal/run-playunreal.sh                      # Run diagnose (default)
#   ./Tools/PlayUnreal/run-playunreal.sh diagnose.py          # Run diagnostics
#   ./Tools/PlayUnreal/run-playunreal.sh verify_visuals.py    # Run visual verification
#   ./Tools/PlayUnreal/run-playunreal.sh acceptance_test.py   # Run full acceptance test
#   ./Tools/PlayUnreal/run-playunreal.sh --no-launch diagnose.py  # Skip editor launch (already running)
#
# Exit codes:
#   0 = PASS — all checks passed
#   1 = FAIL — one or more checks failed
#   2 = ERROR — launch failure or timeout
#
# Prerequisites:
#   - UE 5.7 installed at /Users/Shared/Epic Games/UE_5.7/
#   - UnrealFrogEditor target built with RemoteControl plugin enabled
#   - Python 3 available

set -euo pipefail

# -- Configuration -----------------------------------------------------------

ENGINE_DIR="/Users/Shared/Epic Games/UE_5.7"
EDITOR_APP="${ENGINE_DIR}/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor"
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT_FILE="${PROJECT_ROOT}/UnrealFrog.uproject"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="${PROJECT_ROOT}/Saved/PlayUnreal"

RC_PORT=30010
RC_URL="http://localhost:${RC_PORT}/remote/info"
STARTUP_TIMEOUT=120  # seconds to wait for editor + RC API
SKIP_LAUNCH=false

# -- Parse arguments ---------------------------------------------------------

SCRIPT_NAME=""
for arg in "$@"; do
    case "${arg}" in
        --no-launch)
            SKIP_LAUNCH=true
            ;;
        *)
            SCRIPT_NAME="${arg}"
            ;;
    esac
done

# Default to diagnose.py
SCRIPT_NAME="${SCRIPT_NAME:-diagnose.py}"
SCRIPT_PATH="${SCRIPT_DIR}/${SCRIPT_NAME}"

# -- Validation --------------------------------------------------------------

if [ "${SKIP_LAUNCH}" = false ] && [ ! -f "${EDITOR_APP}" ]; then
    echo "ERROR: UnrealEditor not found at: ${EDITOR_APP}"
    exit 2
fi

if [ ! -f "${PROJECT_FILE}" ]; then
    echo "ERROR: Project file not found at: ${PROJECT_FILE}"
    exit 2
fi

if [ ! -f "${SCRIPT_PATH}" ]; then
    echo "ERROR: Test script not found at: ${SCRIPT_PATH}"
    echo "       Available scripts:"
    ls -1 "${SCRIPT_DIR}"/*.py 2>/dev/null | while read -r f; do
        echo "         $(basename "$f")"
    done
    exit 2
fi

# Ensure log directory exists
mkdir -p "${LOG_DIR}"

# -- Kill stale editor processes (only if we are launching) ------------------

EDITOR_PID=""

if [ "${SKIP_LAUNCH}" = false ]; then
    STALE_PIDS=$(pgrep -f "UnrealEditor|UnrealTraceServer" 2>/dev/null || true)
    if [ -n "${STALE_PIDS}" ]; then
        echo "Killing stale editor processes..."
        pkill -f "UnrealTraceServer" 2>/dev/null || true
        pkill -f "UnrealEditor" 2>/dev/null || true
        sleep 3
        echo "Done."
    fi
fi

# -- Banner ------------------------------------------------------------------

echo "============================================"
echo "  PlayUnreal Test Runner"
echo "============================================"
echo "  Engine:  ${ENGINE_DIR}"
echo "  Project: ${PROJECT_FILE}"
echo "  Script:  ${SCRIPT_NAME}"
echo "  RC Port: ${RC_PORT}"
if [ "${SKIP_LAUNCH}" = true ]; then
    echo "  Launch:  SKIPPED (--no-launch)"
else
    echo "  Timeout: ${STARTUP_TIMEOUT}s"
fi
echo "============================================"
echo ""

# -- Launch editor with Remote Control API -----------------------------------

# Cleanup on exit — always kill the editor we launched
cleanup() {
    if [ -n "${EDITOR_PID}" ] && kill -0 "${EDITOR_PID}" 2>/dev/null; then
        echo ""
        echo "Shutting down editor (PID: ${EDITOR_PID})..."
        kill "${EDITOR_PID}" 2>/dev/null || true
        sleep 2
        kill -9 "${EDITOR_PID}" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

if [ "${SKIP_LAUNCH}" = false ]; then
    echo "Launching editor in -game mode with Remote Control API..."

    EDITOR_LOG="${LOG_DIR}/editor_$(date +%Y%m%d_%H%M%S).log"

    "${EDITOR_APP}" \
        "${PROJECT_FILE}" \
        -game \
        -windowed \
        -resx=1280 \
        -resy=720 \
        -log \
        -RCWebControlEnable \
        -ExecCmds="WebControl.EnableServerOnStartup 1" \
        > "${EDITOR_LOG}" 2>&1 &
    EDITOR_PID=$!

    echo "  Editor PID: ${EDITOR_PID}"
    echo "  Editor log: ${EDITOR_LOG}"
    echo ""

    # -- Wait for Remote Control API to respond ------------------------------

    echo "Waiting for Remote Control API on port ${RC_PORT}..."

    ELAPSED=0
    RC_READY=false
    while [ "${ELAPSED}" -lt "${STARTUP_TIMEOUT}" ]; do
        if curl -s --connect-timeout 2 "${RC_URL}" > /dev/null 2>&1; then
            RC_READY=true
            break
        fi

        # Check if editor is still running
        if ! kill -0 "${EDITOR_PID}" 2>/dev/null; then
            echo ""
            echo "ERROR: Editor process exited before Remote Control API was ready."
            echo "       Check editor log: ${EDITOR_LOG}"
            echo "       Last 20 lines:"
            tail -20 "${EDITOR_LOG}" 2>/dev/null || true
            exit 2
        fi

        sleep 2
        ELAPSED=$((ELAPSED + 2))
        if [ $((ELAPSED % 10)) -eq 0 ]; then
            echo "  Still waiting... (${ELAPSED}s / ${STARTUP_TIMEOUT}s)"
        fi
    done

    if [ "${RC_READY}" = false ]; then
        echo ""
        echo "ERROR: Remote Control API did not respond within ${STARTUP_TIMEOUT}s."
        echo "       The editor may have failed to start or the RC plugin is not loading."
        echo "       Check editor log: ${EDITOR_LOG}"
        echo "       Last 20 lines:"
        tail -20 "${EDITOR_LOG}" 2>/dev/null || true
        exit 2
    fi

    echo "Remote Control API is ready (took ~${ELAPSED}s)."

    # Give the game a moment to finish loading actors
    echo "Waiting 3s for game actors to spawn..."
    sleep 3
    echo ""
else
    # --no-launch mode: check if RC API is already responding
    echo "Checking if Remote Control API is already running..."
    if ! curl -s --connect-timeout 2 "${RC_URL}" > /dev/null 2>&1; then
        echo ""
        echo "ERROR: Remote Control API is not responding on localhost:${RC_PORT}."
        echo "       Either launch the editor first, or omit --no-launch."
        exit 2
    fi
    echo "  RC API is already running."
    echo ""
fi

# -- Run the Python test script ----------------------------------------------

echo "Running: python3 ${SCRIPT_PATH}"
echo "============================================"
echo ""

SCRIPT_EXIT=0
python3 "${SCRIPT_PATH}" || SCRIPT_EXIT=$?

echo ""
echo "============================================"
echo ""

if [ "${SCRIPT_EXIT}" -eq 0 ]; then
    echo "  =========================================="
    echo "  ||           RESULT: PASS               ||"
    echo "  =========================================="
else
    echo "  =========================================="
    echo "  ||           RESULT: FAIL               ||"
    echo "  ||      (exit code: ${SCRIPT_EXIT})              ||"
    echo "  =========================================="
fi

echo ""
exit "${SCRIPT_EXIT}"
