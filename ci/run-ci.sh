#!/usr/bin/env bash
# run-ci.sh — Full CI pipeline: build, launch UE, demonstrate all features, collect artifacts.
#
# This is the top-level script that a CI runner (or developer) executes.
# It drives the real Unreal Engine headlessly and exercises every PlayUnreal
# feature against the live game.
#
# Stages:
#   1. Validate environment (UE engine, project file, Python)
#   2. Build Game + Editor targets
#   3. Run headless UE automation tests (NullRHI — no game window)
#   4. Run Python/C++ constant sync check (no UE needed)
#   5. Launch game with Remote Control API
#   6. Wait for RC API readiness
#   7. Run comprehensive feature demonstration (13 features)
#   8. Run individual test scripts (diagnose, acceptance, qa_checklist)
#   9. Run pytest E2E tests
#  10. Collect artifacts and report results
#
# Usage:
#   ./ci/run-ci.sh                         # Full pipeline
#   ./ci/run-ci.sh --skip-build            # Skip UE build (already built)
#   ./ci/run-ci.sh --skip-ue-tests         # Skip NullRHI automation tests
#   ./ci/run-ci.sh --game-only             # Skip build + UE tests, just run game tests
#   ./ci/run-ci.sh --timeout 180           # Custom startup timeout (seconds)
#
# Environment variables:
#   UE_ENGINE_DIR   — Path to UE installation (default: auto-detect)
#   UE_PROJECT_FILE — Path to .uproject (default: PROJECT_ROOT/UnrealFrog.uproject)
#   RC_PORT         — Remote Control API port (default: 30010)
#
# Exit codes:
#   0 = all stages passed
#   1 = one or more test stages failed
#   2 = build failure, launch error, or missing prerequisites

set -euo pipefail

# -- Resolve paths -----------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TOOLS_DIR="${PROJECT_ROOT}/Tools/PlayUnreal"
ARTIFACT_DIR="${PROJECT_ROOT}/Saved/CI/artifacts"
LOG_DIR="${PROJECT_ROOT}/Saved/CI/logs"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

# -- Detect UE engine path --------------------------------------------------

detect_engine_dir() {
    # 1. Explicit environment variable
    if [ -n "${UE_ENGINE_DIR:-}" ] && [ -d "${UE_ENGINE_DIR}" ]; then
        echo "${UE_ENGINE_DIR}"
        return
    fi

    # 2. macOS default locations
    for ver in "5.7" "5.6" "5.5" "5.4"; do
        local path="/Users/Shared/Epic Games/UE_${ver}"
        if [ -d "${path}" ]; then
            echo "${path}"
            return
        fi
    done

    # 3. Linux default locations
    for ver in "5.7" "5.6" "5.5" "5.4"; do
        local path="/opt/UnrealEngine/UE_${ver}"
        if [ -d "${path}" ]; then
            echo "${path}"
            return
        fi
        local path2="${HOME}/UnrealEngine/UE_${ver}"
        if [ -d "${path2}" ]; then
            echo "${path2}"
            return
        fi
    done

    echo ""
}

ENGINE_DIR="$(detect_engine_dir)"
PROJECT_FILE="${UE_PROJECT_FILE:-${PROJECT_ROOT}/UnrealFrog.uproject}"
RC_PORT="${RC_PORT:-30010}"
RC_URL="http://localhost:${RC_PORT}/remote/info"

# -- Detect platform-specific editor paths ----------------------------------

detect_editor_paths() {
    if [[ "$(uname)" == "Darwin" ]]; then
        EDITOR_CMD="${ENGINE_DIR}/Engine/Binaries/Mac/UnrealEditor-Cmd"
        EDITOR_APP="${ENGINE_DIR}/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor"
        BUILD_SCRIPT="${ENGINE_DIR}/Engine/Build/BatchFiles/Mac/Build.sh"
    else
        EDITOR_CMD="${ENGINE_DIR}/Engine/Binaries/Linux/UnrealEditor-Cmd"
        EDITOR_APP="${ENGINE_DIR}/Engine/Binaries/Linux/UnrealEditor"
        BUILD_SCRIPT="${ENGINE_DIR}/Engine/Build/BatchFiles/Linux/Build.sh"
    fi
}

# -- Parse arguments ---------------------------------------------------------

SKIP_BUILD=false
SKIP_UE_TESTS=false
GAME_ONLY=false
STARTUP_TIMEOUT=120

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-build)     SKIP_BUILD=true; shift ;;
        --skip-ue-tests)  SKIP_UE_TESTS=true; shift ;;
        --game-only)      GAME_ONLY=true; SKIP_BUILD=true; SKIP_UE_TESTS=true; shift ;;
        --timeout)        STARTUP_TIMEOUT="$2"; shift 2 ;;
        *)                echo "Unknown argument: $1"; exit 2 ;;
    esac
done

# -- Cleanup on exit ---------------------------------------------------------

EDITOR_PID=""
STAGE_FAILURES=0

cleanup() {
    if [ -n "${EDITOR_PID}" ] && kill -0 "${EDITOR_PID}" 2>/dev/null; then
        echo ""
        echo "[CI] Shutting down editor (PID: ${EDITOR_PID})..."
        kill "${EDITOR_PID}" 2>/dev/null || true
        sleep 2
        kill -9 "${EDITOR_PID}" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

# -- Helper: run a stage and track pass/fail ---------------------------------

run_stage() {
    local stage_num="$1"
    local stage_name="$2"
    shift 2

    echo ""
    echo "================================================================"
    echo "  Stage ${stage_num}: ${stage_name}"
    echo "================================================================"

    local stage_log="${LOG_DIR}/stage_${stage_num}_${TIMESTAMP}.log"
    local exit_code=0

    "$@" 2>&1 | tee "${stage_log}" || exit_code=$?

    if [ "${exit_code}" -eq 0 ]; then
        echo "  [STAGE ${stage_num}] ${stage_name}: PASS"
    else
        echo "  [STAGE ${stage_num}] ${stage_name}: FAIL (exit code ${exit_code})"
        STAGE_FAILURES=$((STAGE_FAILURES + 1))
    fi

    return "${exit_code}"
}

# -- Banner ------------------------------------------------------------------

echo "================================================================"
echo "  PlayUnreal CI Pipeline"
echo "================================================================"
echo "  Timestamp:   ${TIMESTAMP}"
echo "  Engine:      ${ENGINE_DIR:-NOT FOUND}"
echo "  Project:     ${PROJECT_FILE}"
echo "  RC Port:     ${RC_PORT}"
echo "  Platform:    $(uname -s) $(uname -m)"
echo "  Python:      $(python3 --version 2>&1 || echo 'NOT FOUND')"
echo "  Skip build:  ${SKIP_BUILD}"
echo "  Skip UE tests: ${SKIP_UE_TESTS}"
echo "  Timeout:     ${STARTUP_TIMEOUT}s"
echo "================================================================"
echo ""

# -- Create directories ------------------------------------------------------

mkdir -p "${ARTIFACT_DIR}" "${LOG_DIR}"

# -- Stage 0: Validate environment ------------------------------------------

echo "================================================================"
echo "  Stage 0: Validate Environment"
echo "================================================================"

VALIDATION_FAILED=false

if [ -z "${ENGINE_DIR}" ]; then
    echo "  [FAIL] Unreal Engine not found."
    echo "         Set UE_ENGINE_DIR environment variable to your UE installation."
    VALIDATION_FAILED=true
else
    echo "  [OK] Unreal Engine: ${ENGINE_DIR}"
fi

detect_editor_paths

if [ "${VALIDATION_FAILED}" = false ] && [ ! -f "${EDITOR_APP}" ]; then
    echo "  [FAIL] UnrealEditor not found at: ${EDITOR_APP}"
    VALIDATION_FAILED=true
else
    echo "  [OK] Editor binary: ${EDITOR_APP}"
fi

if [ ! -f "${PROJECT_FILE}" ]; then
    echo "  [FAIL] Project file not found: ${PROJECT_FILE}"
    VALIDATION_FAILED=true
else
    echo "  [OK] Project file: ${PROJECT_FILE}"
fi

if ! command -v python3 &>/dev/null; then
    echo "  [FAIL] python3 not found in PATH"
    VALIDATION_FAILED=true
else
    echo "  [OK] Python: $(python3 --version)"
fi

if ! command -v curl &>/dev/null; then
    echo "  [FAIL] curl not found in PATH"
    VALIDATION_FAILED=true
else
    echo "  [OK] curl available"
fi

if [ "${VALIDATION_FAILED}" = true ]; then
    echo ""
    echo "  Environment validation FAILED. Cannot continue."
    exit 2
fi

echo "  [OK] All prerequisites satisfied."

# -- Stage 1: Build Game + Editor targets ------------------------------------

if [ "${SKIP_BUILD}" = false ]; then
    run_stage 1 "Build UE Targets" bash -c "
        echo 'Building Game target...'
        '${BUILD_SCRIPT}' UnrealFrog $(uname -s | sed 's/Darwin/Mac/' | sed 's/Linux/Linux/') Development '${PROJECT_FILE}' 2>&1 | tail -5
        echo ''
        echo 'Building Editor target...'
        '${BUILD_SCRIPT}' UnrealFrogEditor $(uname -s | sed 's/Darwin/Mac/' | sed 's/Linux/Linux/') Development '${PROJECT_FILE}' 2>&1 | tail -5
    " || { echo "Build failed — aborting."; exit 2; }
else
    echo ""
    echo "  Stage 1: Build SKIPPED (--skip-build)"
fi

# -- Stage 2: Headless UE Automation Tests (NullRHI) ------------------------

if [ "${SKIP_UE_TESTS}" = false ]; then
    run_stage 2 "Headless UE Automation Tests" \
        "${TOOLS_DIR}/run-tests.sh" --all --timeout 300 || true
else
    echo ""
    echo "  Stage 2: UE Automation Tests SKIPPED"
fi

# -- Stage 3: Python/C++ Constant Sync Check --------------------------------

if [ "${SKIP_UE_TESTS}" = false ]; then
    run_stage 3 "Python/C++ Constant Sync Check" \
        "${TOOLS_DIR}/run-tests.sh" --check-sync || true
else
    echo ""
    echo "  Stage 3: Sync Check SKIPPED"
fi

# -- Stage 4: Kill stale editors, launch game with RC API -------------------

echo ""
echo "================================================================"
echo "  Stage 4: Launch Game with Remote Control API"
echo "================================================================"

# Kill any stale editor/trace processes
STALE_PIDS=$(pgrep -f "UnrealEditor|UnrealTraceServer" 2>/dev/null || true)
if [ -n "${STALE_PIDS}" ]; then
    echo "  Killing stale editor processes..."
    pkill -f "UnrealTraceServer" 2>/dev/null || true
    pkill -f "UnrealEditor" 2>/dev/null || true
    sleep 3
fi

EDITOR_LOG="${LOG_DIR}/editor_${TIMESTAMP}.log"

echo "  Launching: ${EDITOR_APP}"
echo "  Flags: -game -windowed -resx=1280 -resy=720 -RCWebControlEnable"
echo "  Log: ${EDITOR_LOG}"

"${EDITOR_APP}" \
    "${PROJECT_FILE}" \
    -game \
    -windowed \
    -resx=1280 \
    -resy=720 \
    -log \
    -nosound \
    -RCWebControlEnable \
    -ExecCmds="WebControl.EnableServerOnStartup 1" \
    > "${EDITOR_LOG}" 2>&1 &
EDITOR_PID=$!

echo "  Editor PID: ${EDITOR_PID}"

# -- Stage 5: Wait for RC API readiness -------------------------------------

echo ""
echo "  Waiting for Remote Control API on port ${RC_PORT}..."

ELAPSED=0
RC_READY=false
while [ "${ELAPSED}" -lt "${STARTUP_TIMEOUT}" ]; do
    if curl -s --connect-timeout 2 "${RC_URL}" > /dev/null 2>&1; then
        RC_READY=true
        break
    fi

    # Check editor still running
    if ! kill -0 "${EDITOR_PID}" 2>/dev/null; then
        echo ""
        echo "  ERROR: Editor exited before RC API was ready."
        echo "  Last 30 lines of log:"
        tail -30 "${EDITOR_LOG}" 2>/dev/null || true
        exit 2
    fi

    sleep 2
    ELAPSED=$((ELAPSED + 2))
    if [ $((ELAPSED % 10)) -eq 0 ]; then
        echo "    Waiting... (${ELAPSED}s / ${STARTUP_TIMEOUT}s)"
    fi
done

if [ "${RC_READY}" = false ]; then
    echo ""
    echo "  ERROR: RC API did not respond within ${STARTUP_TIMEOUT}s."
    echo "  Last 30 lines of log:"
    tail -30 "${EDITOR_LOG}" 2>/dev/null || true
    exit 2
fi

echo "  RC API ready (took ~${ELAPSED}s)."
echo "  Waiting 5s for game actors to fully spawn..."
sleep 5

# -- Stage 6: Comprehensive Feature Demonstration ---------------------------

run_stage 6 "Comprehensive Feature Demonstration (13 features)" \
    python3 "${SCRIPT_DIR}/ci_demo_all_features.py" || true

# -- Stage 7: Individual Test Scripts ----------------------------------------

echo ""
echo "================================================================"
echo "  Stage 7: Individual Test Scripts"
echo "================================================================"

# diagnose.py
echo ""
echo "--- diagnose.py ---"
python3 "${TOOLS_DIR}/diagnose.py" 2>&1 | tee "${LOG_DIR}/diagnose_${TIMESTAMP}.log" || true

# acceptance_test.py
echo ""
echo "--- acceptance_test.py ---"
python3 "${TOOLS_DIR}/acceptance_test.py" 2>&1 | tee "${LOG_DIR}/acceptance_${TIMESTAMP}.log" || true

# qa_checklist.py
echo ""
echo "--- qa_checklist.py ---"
python3 "${TOOLS_DIR}/qa_checklist.py" 2>&1 | tee "${LOG_DIR}/qa_checklist_${TIMESTAMP}.log" || true

# debug_navigation.py
echo ""
echo "--- debug_navigation.py ---"
python3 "${TOOLS_DIR}/debug_navigation.py" 2>&1 | tee "${LOG_DIR}/debug_nav_${TIMESTAMP}.log" || true

# test_crossing.py
echo ""
echo "--- test_crossing.py ---"
python3 "${TOOLS_DIR}/test_crossing.py" 2>&1 | tee "${LOG_DIR}/test_crossing_${TIMESTAMP}.log" || true

echo ""
echo "  [STAGE 7] Individual Test Scripts: COMPLETE"

# -- Stage 8: Pytest E2E Tests -----------------------------------------------

echo ""
echo "================================================================"
echo "  Stage 8: Pytest E2E Tests"
echo "================================================================"

if command -v pytest &>/dev/null || python3 -m pytest --version &>/dev/null 2>&1; then
    python3 -m pytest "${PROJECT_ROOT}/examples/tests_e2e/" -v \
        --tb=short \
        --junitxml="${ARTIFACT_DIR}/pytest_results.xml" \
        2>&1 | tee "${LOG_DIR}/pytest_${TIMESTAMP}.log" || true
    echo "  [STAGE 8] Pytest E2E: COMPLETE"
else
    echo "  pytest not available — installing dev dependencies..."
    pip3 install pytest >/dev/null 2>&1 || true
    if python3 -m pytest --version &>/dev/null 2>&1; then
        python3 -m pytest "${PROJECT_ROOT}/examples/tests_e2e/" -v \
            --tb=short \
            --junitxml="${ARTIFACT_DIR}/pytest_results.xml" \
            2>&1 | tee "${LOG_DIR}/pytest_${TIMESTAMP}.log" || true
        echo "  [STAGE 8] Pytest E2E: COMPLETE"
    else
        echo "  [STAGE 8] Pytest E2E: SKIPPED (pytest unavailable)"
    fi
fi

# -- Stage 9: Collect Artifacts & Final Report --------------------------------

echo ""
echo "================================================================"
echo "  Stage 9: Collect Artifacts"
echo "================================================================"

# Copy screenshots from all test runs into the CI artifact dir
for dir in \
    "${PROJECT_ROOT}/Saved/Screenshots" \
    "${PROJECT_ROOT}/Saved/Screenshots/acceptance_test" \
    "${PROJECT_ROOT}/Saved/Screenshots/smoke_test" \
    "${PROJECT_ROOT}/Saved/Screenshots/qa_checklist" \
    "${PROJECT_ROOT}/Saved/Screenshots/auto"; do
    if [ -d "${dir}" ]; then
        cp -r "${dir}" "${ARTIFACT_DIR}/" 2>/dev/null || true
    fi
done

# Copy diagnostic reports
for f in "${PROJECT_ROOT}/Saved/PlayUnreal/diagnostic_report.json" \
         "${PROJECT_ROOT}/Saved/CI/ci_report.json"; do
    if [ -f "${f}" ]; then
        cp "${f}" "${ARTIFACT_DIR}/" 2>/dev/null || true
    fi
done

# Copy editor log
cp "${EDITOR_LOG}" "${ARTIFACT_DIR}/" 2>/dev/null || true

echo "  Artifacts directory: ${ARTIFACT_DIR}"
echo "  Contents:"
find "${ARTIFACT_DIR}" -type f 2>/dev/null | while read -r f; do
    size=$(stat -f%z "${f}" 2>/dev/null || stat -c%s "${f}" 2>/dev/null || echo "?")
    echo "    ${f} (${size} bytes)"
done
echo ""

# -- Final Summary -----------------------------------------------------------

echo "================================================================"
echo "  PlayUnreal CI Pipeline — FINAL SUMMARY"
echo "================================================================"

# Parse the CI report if it exists
CI_REPORT="${PROJECT_ROOT}/Saved/CI/ci_report.json"
if [ -f "${CI_REPORT}" ]; then
    TOTAL=$(python3 -c "import json; r=json.load(open('${CI_REPORT}')); print(r['total'])" 2>/dev/null || echo "?")
    PASSED=$(python3 -c "import json; r=json.load(open('${CI_REPORT}')); print(r['passed'])" 2>/dev/null || echo "?")
    FAILED=$(python3 -c "import json; r=json.load(open('${CI_REPORT}')); print(r['failed'])" 2>/dev/null || echo "?")
    echo "  Feature Demo:  ${PASSED}/${TOTAL} passed, ${FAILED} failed"
fi

echo "  Stage failures: ${STAGE_FAILURES}"
echo "  Artifacts:      ${ARTIFACT_DIR}"
echo "  Logs:           ${LOG_DIR}"
echo ""

if [ "${STAGE_FAILURES}" -eq 0 ]; then
    echo "  =========================================="
    echo "  ||       CI PIPELINE: PASS              ||"
    echo "  =========================================="
    exit 0
else
    echo "  =========================================="
    echo "  ||       CI PIPELINE: FAIL              ||"
    echo "  ||   (${STAGE_FAILURES} stage(s) had failures)        ||"
    echo "  =========================================="
    exit 1
fi
