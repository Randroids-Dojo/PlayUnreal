#!/usr/bin/env bash
# build-and-verify.sh — Build, test, and auto-screenshot in one pipeline.
#
# The auto-screenshot build gate:
#   1. Build Game + Editor targets (sequential — UBT mutex)
#   2. Run all tests via run-tests.sh — abort if any fail
#   3. Launch editor with -game + Remote Control API
#   4. Wait for RC API readiness
#   5. Take a screenshot via client.py
#   6. Save to Saved/Screenshots/auto/build_YYYYMMDD_HHMMSS.png
#   7. Print [SCREENSHOT] /absolute/path for agent consumption
#   8. Clean up editor process
#
# Usage:
#   ./Tools/PlayUnreal/build-and-verify.sh              # Full pipeline
#   ./Tools/PlayUnreal/build-and-verify.sh --skip-build  # Skip build (already built)
#   ./Tools/PlayUnreal/build-and-verify.sh --skip-tests  # Skip tests (already verified)
#
# Exit codes:
#   0 = build + tests + screenshot all succeeded
#   1 = test failure
#   2 = build failure or launch error

set -euo pipefail

# -- Configuration -----------------------------------------------------------

ENGINE_DIR="/Users/Shared/Epic Games/UE_5.7"
BUILD_SH="${ENGINE_DIR}/Engine/Build/BatchFiles/Mac/Build.sh"
EDITOR_APP="${ENGINE_DIR}/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor"
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT_FILE="${PROJECT_ROOT}/UnrealFrog.uproject"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_TESTS="${SCRIPT_DIR}/run-tests.sh"

RC_PORT=30010
RC_URL="http://localhost:${RC_PORT}/remote/info"
STARTUP_TIMEOUT=120
SCREENSHOT_DIR="${PROJECT_ROOT}/Saved/Screenshots/auto"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
SCREENSHOT_PATH="${SCREENSHOT_DIR}/build_${TIMESTAMP}.png"

SKIP_BUILD=false
SKIP_TESTS=false

# -- Parse arguments ---------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-build)  SKIP_BUILD=true; shift ;;
        --skip-tests)  SKIP_TESTS=true; shift ;;
        *)             echo "Unknown argument: $1"; exit 2 ;;
    esac
done

# -- Cleanup on exit (always kill editor we launched) ------------------------

EDITOR_PID=""

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

# -- Banner ------------------------------------------------------------------

echo "============================================"
echo "  Build & Verify Pipeline"
echo "============================================"
echo "  Engine:     ${ENGINE_DIR}"
echo "  Project:    ${PROJECT_FILE}"
echo "  Screenshot: ${SCREENSHOT_PATH}"
echo "  Skip build: ${SKIP_BUILD}"
echo "  Skip tests: ${SKIP_TESTS}"
echo "============================================"
echo ""

# -- Step 1: Build Game + Editor targets -------------------------------------

if [ "${SKIP_BUILD}" = false ]; then
    echo "--- Step 1: Build Game target ---"
    if ! "${BUILD_SH}" UnrealFrog Mac Development "${PROJECT_FILE}" 2>&1 | tail -3; then
        echo "ERROR: Game target build failed."
        exit 2
    fi
    echo ""

    echo "--- Step 1b: Build Editor target ---"
    if ! "${BUILD_SH}" UnrealFrogEditor Mac Development "${PROJECT_FILE}" 2>&1 | tail -3; then
        echo "ERROR: Editor target build failed."
        exit 2
    fi
    echo ""
else
    echo "--- Step 1: Build SKIPPED (--skip-build) ---"
    echo ""
fi

# -- Step 2: Run all tests ---------------------------------------------------

if [ "${SKIP_TESTS}" = false ]; then
    echo "--- Step 2: Run all tests ---"
    if ! "${RUN_TESTS}" --all; then
        echo ""
        echo "ERROR: Tests failed. Aborting pipeline."
        exit 1
    fi
    echo ""
else
    echo "--- Step 2: Tests SKIPPED (--skip-tests) ---"
    echo ""
fi

# -- Step 3: Kill stale editors and launch with RC API -----------------------

echo "--- Step 3: Launch editor for screenshot ---"

# Kill stale processes
STALE_PIDS=$(pgrep -f "UnrealEditor|UnrealTraceServer" 2>/dev/null || true)
if [ -n "${STALE_PIDS}" ]; then
    echo "Killing stale editor processes..."
    pkill -f "UnrealTraceServer" 2>/dev/null || true
    pkill -f "UnrealEditor" 2>/dev/null || true
    sleep 3
fi

EDITOR_LOG="${PROJECT_ROOT}/Saved/PlayUnreal/verify_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$(dirname "${EDITOR_LOG}")"

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

# -- Step 4: Wait for RC API ------------------------------------------------

echo ""
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
        echo "ERROR: Editor process exited before RC API was ready."
        echo "       Check log: ${EDITOR_LOG}"
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
    echo "ERROR: RC API did not respond within ${STARTUP_TIMEOUT}s."
    echo "       Check log: ${EDITOR_LOG}"
    tail -20 "${EDITOR_LOG}" 2>/dev/null || true
    exit 2
fi

echo "RC API ready (took ~${ELAPSED}s)."
echo "Waiting 3s for game actors to spawn..."
sleep 3

# -- Step 5: Take screenshot via client.py ----------------------------------

echo ""
echo "--- Step 5: Take screenshot ---"

mkdir -p "${SCREENSHOT_DIR}"

python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
from client import PlayUnreal

pu = PlayUnreal()
if not pu.is_alive():
    print('ERROR: RC API not responding')
    sys.exit(1)

success = pu.screenshot('${SCREENSHOT_PATH}')
if success:
    print('Screenshot saved.')
else:
    print('WARNING: Screenshot may have failed.')
"

# -- Step 6: Report result ---------------------------------------------------

echo ""
echo "============================================"

if [ -f "${SCREENSHOT_PATH}" ]; then
    echo "[SCREENSHOT] ${SCREENSHOT_PATH}"
    echo ""
    echo "  Pipeline complete. Screenshot saved."
    echo "  Read the screenshot to verify visual correctness."
else
    echo "WARNING: Screenshot file not found at ${SCREENSHOT_PATH}"
    echo "  The editor may not have rendered in time."
    echo "  Try running again or use run-playunreal.sh manually."
fi

echo "============================================"
exit 0
