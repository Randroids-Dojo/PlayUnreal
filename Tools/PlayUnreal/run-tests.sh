#!/usr/bin/env bash
# run-tests.sh — Headless test runner for UnrealFrog automation tests
#
# Usage:
#   ./Tools/PlayUnreal/run-tests.sh                       # Run all UnrealFrog tests (default)
#   ./Tools/PlayUnreal/run-tests.sh --all                  # Same as above — run all tests
#   ./Tools/PlayUnreal/run-tests.sh --seam                 # Run seam tests only
#   ./Tools/PlayUnreal/run-tests.sh --audio                # Run audio tests only
#   ./Tools/PlayUnreal/run-tests.sh --e2e                  # Run PlayUnreal E2E tests only
#   ./Tools/PlayUnreal/run-tests.sh --integration          # Run integration tests only
#   ./Tools/PlayUnreal/run-tests.sh --wiring               # Run delegate wiring tests only
#   ./Tools/PlayUnreal/run-tests.sh --spatial              # Run spatial position assertion tests only
#   ./Tools/PlayUnreal/run-tests.sh --collision             # Run collision tests only
#   ./Tools/PlayUnreal/run-tests.sh --gameplay              # Run gameplay scenario tests only
#   ./Tools/PlayUnreal/run-tests.sh "UnrealFrog.Wiring"    # Run custom filter (any UE test path)
#   ./Tools/PlayUnreal/run-tests.sh --list                 # List available tests
#   ./Tools/PlayUnreal/run-tests.sh --report               # Generate JSON test report
#   ./Tools/PlayUnreal/run-tests.sh --functional           # Run functional tests (needs editor, not NullRHI)
#   ./Tools/PlayUnreal/run-tests.sh --check-sync           # Verify Python/C++ constant sync (no UE needed)
#
# Exit codes:
#   0 = all tests passed
#   1 = one or more tests failed
#   2 = timeout, crash, or no tests matched
#
# Requirements:
#   - UE 5.7 installed at /Users/Shared/Epic Games/UE_5.7/
#   - UnrealFrogEditor target built (Editor build)

set -euo pipefail

# -- Configuration -----------------------------------------------------------

ENGINE_DIR="/Users/Shared/Epic Games/UE_5.7"
EDITOR_CMD="${ENGINE_DIR}/Engine/Binaries/Mac/UnrealEditor-Cmd"
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT_FILE="${UE_PROJECT_FILE:-${PROJECT_ROOT}/UnrealFrog.uproject}"
LOG_DIR="${PROJECT_ROOT}/Saved/Logs"
REPORT_DIR="${PROJECT_ROOT}/Saved/Reports"
TEST_LOG="${LOG_DIR}/TestRunner.log"
MACOS_LOG_DIR="${HOME}/Library/Logs/Unreal Engine/UnrealFrogEditor"

# -- Category filter map (--flag -> UE test path prefix) ---------------------

resolve_category_filter() {
    case "$1" in
        --all)          echo "UnrealFrog" ;;
        --seam)         echo "UnrealFrog.Seam" ;;
        --audio)        echo "UnrealFrog.Audio" ;;
        --e2e)          echo "UnrealFrog.PlayUnreal" ;;
        --integration)  echo "UnrealFrog.Integration" ;;
        --wiring)       echo "UnrealFrog.Wiring" ;;
        --vfx)          echo "UnrealFrog.VFX" ;;
        --spatial)      echo "UnrealFrog.Spatial" ;;
        --collision)    echo "UnrealFrog.Collision" ;;
        --gameplay)     echo "UnrealFrog.Gameplay" ;;
        *)              echo "" ;;
    esac
}

# Known category names for per-category reporting
KNOWN_CATEGORIES="Character Collision Ground Input Score LaneSystem HUD Mesh Camera Orchestration GameState Wiring Integration Seam Audio PlayUnreal VFX Spatial Gameplay GameConfig"

# -- Parse arguments ---------------------------------------------------------

TEST_FILTER="UnrealFrog"
CATEGORY_NAME=""
LIST_MODE=false
REPORT_MODE=false
FUNCTIONAL_MODE=false
CHECK_SYNC_MODE=false
TIMEOUT_SECONDS=300  # 5 minutes

while [[ $# -gt 0 ]]; do
    case "$1" in
        --list)
            LIST_MODE=true
            shift
            ;;
        --report)
            REPORT_MODE=true
            shift
            ;;
        --functional)
            FUNCTIONAL_MODE=true
            shift
            ;;
        --check-sync)
            CHECK_SYNC_MODE=true
            shift
            ;;
        --timeout)
            TIMEOUT_SECONDS="$2"
            shift 2
            ;;
        --all|--seam|--audio|--e2e|--integration|--wiring|--vfx|--spatial|--collision|--gameplay)
            CATEGORY_NAME="$1"
            TEST_FILTER="$(resolve_category_filter "$1")"
            shift
            ;;
        *)
            TEST_FILTER="$1"
            shift
            ;;
    esac
done

# -- SYNC check mode (no UE needed) ------------------------------------------
# Scan Python files for "# SYNC: path/to/file.h:VARIABLE" annotations and
# verify the Python default matches the C++ source value.

if [ "${CHECK_SYNC_MODE}" = true ]; then
    echo "============================================"
    echo "  Cross-Boundary Constant Sync Check"
    echo "============================================"
    echo ""

    SYNC_ERRORS=0
    SYNC_CHECKED=0

    while IFS= read -r line; do
        # Strip the filename prefix (grep returns "file.py:LINE")
        content=$(echo "${line}" | sed 's|^.*/[^:]*\.py:||')

        # Extract: CONST_NAME = value  # SYNC: relative/path:CppName
        py_const=$(echo "${content}" | sed -n 's/^\([A-Z_]*\) = .*/\1/p')
        py_value=$(echo "${content}" | sed -n 's/^[A-Z_]* = \([0-9.]*\).*/\1/p')
        sync_ref=$(echo "${content}" | sed -n 's/.*# SYNC: \(.*\)/\1/p')

        if [ -z "${py_const}" ] || [ -z "${py_value}" ] || [ -z "${sync_ref}" ]; then
            continue
        fi

        # Parse sync ref: "relative/path.h:CppVariableName"
        cpp_file=$(echo "${sync_ref}" | cut -d: -f1)
        cpp_var=$(echo "${sync_ref}" | cut -d: -f2)
        cpp_full="${PROJECT_ROOT}/${cpp_file}"

        if [ ! -f "${cpp_full}" ]; then
            # Try Source/ prefix
            cpp_full="${PROJECT_ROOT}/Source/UnrealFrog/${cpp_file}"
        fi

        SYNC_CHECKED=$((SYNC_CHECKED + 1))

        if [ ! -f "${cpp_full}" ]; then
            echo "  WARN: ${py_const} -> ${cpp_file}:${cpp_var} — C++ file not found"
            continue
        fi

        # Extract value from C++ (look for "CppVar = VALUE" or "CppVar(VALUE")
        # Note: BSD sed doesn't support \s — use [[:space:]] or explicit spaces
        cpp_value=$(grep -E "${cpp_var}[[:space:]]*=[[:space:]]*[0-9]" "${cpp_full}" 2>/dev/null \
            | head -1 \
            | sed -n "s/.*${cpp_var} *= *\([0-9.]*\).*/\1/p" || true)

        if [ -z "${cpp_value}" ]; then
            # Try constructor-style: CppVar(VALUE)
            cpp_value=$(grep -E "${cpp_var}[[:space:]]*\([[:space:]]*[0-9]" "${cpp_full}" 2>/dev/null \
                | head -1 \
                | sed -n "s/.*${cpp_var} *( *\([0-9.]*\).*/\1/p" || true)
        fi

        if [ -z "${cpp_value}" ]; then
            echo "  WARN: ${py_const}=${py_value} -> ${cpp_var} — could not extract C++ value"
            continue
        fi

        # Compare (strip trailing zeros for float comparison)
        py_norm=$(echo "${py_value}" | sed 's/\.0*$//' | sed 's/\(\.[0-9]*[1-9]\)0*$/\1/')
        cpp_norm=$(echo "${cpp_value}" | sed 's/\.0*$//' | sed 's/\(\.[0-9]*[1-9]\)0*$/\1/')

        if [ "${py_norm}" = "${cpp_norm}" ]; then
            echo "  OK:   ${py_const}=${py_value} == ${cpp_var}=${cpp_value}"
        else
            echo "  MISMATCH: ${py_const}=${py_value} != ${cpp_var}=${cpp_value} (${cpp_file})"
            SYNC_ERRORS=$((SYNC_ERRORS + 1))
        fi
    done < <(grep "# SYNC:" "${PROJECT_ROOT}"/Tools/PlayUnreal/*.py 2>/dev/null || true)

    echo ""
    echo "  Checked: ${SYNC_CHECKED}"
    echo "  Mismatches: ${SYNC_ERRORS}"
    echo "============================================"

    if [ "${SYNC_ERRORS}" -gt 0 ]; then
        exit 1
    fi
    exit 0
fi

# -- Validation --------------------------------------------------------------

if [ ! -f "${EDITOR_CMD}" ]; then
    echo "ERROR: UnrealEditor-Cmd not found at: ${EDITOR_CMD}"
    echo "       Is UE 5.7 installed?"
    exit 2
fi

if [ ! -f "${PROJECT_FILE}" ]; then
    echo "ERROR: Project file not found at: ${PROJECT_FILE}"
    exit 2
fi

# -- Lock file: prevent concurrent test runs ---------------------------------
# mkdir is atomic on POSIX — if it fails, another run is in progress.

LOCK_DIR="/tmp/.unrealFrog_test_lock"
LOCK_PID_FILE="${LOCK_DIR}/pid"

cleanup_lock() {
    rm -rf "${LOCK_DIR}" 2>/dev/null || true
}

acquire_lock() {
    if mkdir "${LOCK_DIR}" 2>/dev/null; then
        echo $$ > "${LOCK_PID_FILE}"
        trap cleanup_lock EXIT INT TERM
        return 0
    fi

    # Lock exists — check if the owning process is still alive
    if [ -f "${LOCK_PID_FILE}" ]; then
        EXISTING_PID=$(cat "${LOCK_PID_FILE}" 2>/dev/null || echo "")
        if [ -n "${EXISTING_PID}" ] && kill -0 "${EXISTING_PID}" 2>/dev/null; then
            echo "ERROR: Another test run is in progress (PID: ${EXISTING_PID})"
            exit 2
        fi
        # PID is dead — stale lock, reclaim it
        echo "Removing stale lock from dead PID ${EXISTING_PID}..."
        rm -rf "${LOCK_DIR}"
        if mkdir "${LOCK_DIR}" 2>/dev/null; then
            echo $$ > "${LOCK_PID_FILE}"
            trap cleanup_lock EXIT INT TERM
            return 0
        fi
    fi

    # Lock dir exists but no PID file or couldn't reclaim — force remove
    echo "Removing orphaned lock directory..."
    rm -rf "${LOCK_DIR}"
    mkdir "${LOCK_DIR}" 2>/dev/null || { echo "ERROR: Could not acquire test lock"; exit 2; }
    echo $$ > "${LOCK_PID_FILE}"
    trap cleanup_lock EXIT INT TERM
}

acquire_lock

# -- Pre-flight: kill stale editor processes ---------------------------------
# Old UnrealEditor-Cmd or UnrealTraceServer processes from prior runs can hold
# stale dylibs and cause silent test failures or startup hangs.

STALE_PIDS=$(pgrep -f "UnrealEditor-Cmd|UnrealTraceServer" 2>/dev/null || true)
if [ -n "${STALE_PIDS}" ]; then
    echo "Cleaning up stale editor processes..."
    pkill -f "UnrealTraceServer" 2>/dev/null || true
    pkill -f "UnrealEditor-Cmd" 2>/dev/null || true
    sleep 2
    echo "Done."
fi

# -- List mode ---------------------------------------------------------------

if [ "${LIST_MODE}" = true ]; then
    echo "Listing available UnrealFrog automation tests..."
    "${EDITOR_CMD}" \
        "${PROJECT_FILE}" \
        -NullRHI \
        -NoSound \
        -NoSplash \
        -Unattended \
        -ExecCmds="Automation List UnrealFrog; Quit" \
        -Log="${TEST_LOG}" \
        2>&1 | grep -E "UnrealFrog\." || true

    echo ""
    echo "Full log: ${TEST_LOG}"
    exit 0
fi

# -- Build RHI flags ---------------------------------------------------------

RHI_FLAGS="-NullRHI -NoSound"
if [ "${FUNCTIONAL_MODE}" = true ]; then
    # Functional tests need a rendering context
    RHI_FLAGS="-NoSound"
fi

# -- Build report flags ------------------------------------------------------

REPORT_FLAGS=""
if [ "${REPORT_MODE}" = true ]; then
    mkdir -p "${REPORT_DIR}"
    REPORT_FLAGS="-ReportExportPath=${REPORT_DIR}"
fi

# -- Run tests ---------------------------------------------------------------

FILTER_LABEL="${CATEGORY_NAME:-custom}"
if [ -z "${CATEGORY_NAME}" ] && [ "${TEST_FILTER}" = "UnrealFrog" ]; then
    FILTER_LABEL="--all"
fi

echo "============================================"
echo "  UnrealFrog Headless Test Runner"
echo "============================================"
echo "  Engine:     ${ENGINE_DIR}"
echo "  Project:    ${PROJECT_FILE}"
echo "  Filter:     ${TEST_FILTER} (${FILTER_LABEL})"
echo "  Mode:       $([ "${FUNCTIONAL_MODE}" = true ] && echo "Functional" || echo "Unit/Integration")"
echo "  Report:     $([ "${REPORT_MODE}" = true ] && echo "${REPORT_DIR}" || echo "Off")"
echo "  Timeout:    ${TIMEOUT_SECONDS}s"
echo "  Log:        ${TEST_LOG}"
echo "============================================"
echo ""

mkdir -p "${LOG_DIR}"

echo "Running tests..."
echo ""

# Timestamp marker so we can find the correct log on macOS
touch /tmp/.unreafrog_test_start

# Launch editor in headless mode with timeout
EDITOR_PID=""
EXIT_CODE=0

# Run with timeout
(
    "${EDITOR_CMD}" \
        "${PROJECT_FILE}" \
        ${RHI_FLAGS} \
        -NoSplash \
        -Unattended \
        -NoPause \
        ${REPORT_FLAGS} \
        -ExecCmds="Automation RunTests ${TEST_FILTER}; Quit" \
        -Log="${TEST_LOG}" \
        2>&1
) &
EDITOR_PID=$!

# Monitor timeout
ELAPSED=0
while kill -0 "${EDITOR_PID}" 2>/dev/null; do
    sleep 1
    ELAPSED=$((ELAPSED + 1))
    if [ "${ELAPSED}" -ge "${TIMEOUT_SECONDS}" ]; then
        echo ""
        echo "TIMEOUT: Editor did not finish within ${TIMEOUT_SECONDS}s — killing process"
        kill -9 "${EDITOR_PID}" 2>/dev/null || true
        wait "${EDITOR_PID}" 2>/dev/null || true
        echo ""
        echo "RESULT: TIMEOUT"
        exit 2
    fi
done

# Capture exit code from editor process
wait "${EDITOR_PID}" 2>/dev/null || EXIT_CODE=$?

# -- Parse results -----------------------------------------------------------

echo ""
echo "============================================"
echo "  Test Results"
echo "============================================"

PASSED=0
FAILED=0
ERRORS=""

# Find the actual log file — check multiple locations since UE nests logs differently
ACTUAL_LOG=""
if [ -f "${TEST_LOG}" ]; then
    ACTUAL_LOG="${TEST_LOG}"
fi

# UE on macOS nests the -Log path under its own log directory, and also writes
# to UnrealFrog.log. Search all candidate locations for the most recent log
# that contains test results.
if [ -z "${ACTUAL_LOG}" ] || ! grep -q "Test Completed" "${ACTUAL_LOG}" 2>/dev/null; then
    for CANDIDATE in \
        "$(find "${MACOS_LOG_DIR}" -name "*.log" -newer /tmp/.unreafrog_test_start 2>/dev/null | head -1)" \
        "${MACOS_LOG_DIR}/UnrealFrog.log" \
        "$(ls -t "${MACOS_LOG_DIR}"/*.log 2>/dev/null | head -1)" \
    ; do
        if [ -n "${CANDIDATE}" ] && [ -f "${CANDIDATE}" ] && grep -q "Test Completed" "${CANDIDATE}" 2>/dev/null; then
            ACTUAL_LOG="${CANDIDATE}"
            break
        fi
    done
fi

if [ -n "${ACTUAL_LOG}" ] && [ -f "${ACTUAL_LOG}" ]; then
    # Count passed/failed from log
    PASSED=$(grep -c "Test Completed\. Result={Success}" "${ACTUAL_LOG}" 2>/dev/null) || true
    FAILED=$(grep -c "Test Completed\. Result={Fail}" "${ACTUAL_LOG}" 2>/dev/null) || true
    PASSED=${PASSED:-0}
    FAILED=${FAILED:-0}

    # Extract failure details
    ERRORS=$(grep -A2 "Result={Fail}" "${ACTUAL_LOG}" 2>/dev/null || true)
    TEST_LOG="${ACTUAL_LOG}"
fi

TOTAL=$((PASSED + FAILED))

echo "  Total:  ${TOTAL}"
echo "  Passed: ${PASSED}"
echo "  Failed: ${FAILED}"
echo "============================================"

# -- Per-category breakdown --------------------------------------------------
# Show pass/fail counts per category when running --all or the default filter

if [ -n "${ACTUAL_LOG}" ] && [ -f "${ACTUAL_LOG}" ] && [ "${TOTAL}" -gt 0 ]; then
    echo ""
    echo "  Per-Category Breakdown:"
    echo "  -------------------------------------------"
    printf "  %-20s %6s %6s %6s\n" "Category" "Pass" "Fail" "Total"
    echo "  -------------------------------------------"

    for CAT in ${KNOWN_CATEGORIES}; do
        CAT_PASS=$(grep "Test Completed\. Result={Success}.*Path={UnrealFrog\.${CAT}\." "${ACTUAL_LOG}" 2>/dev/null | wc -l | tr -d ' ') || true
        CAT_FAIL=$(grep "Test Completed\. Result={Fail}.*Path={UnrealFrog\.${CAT}\." "${ACTUAL_LOG}" 2>/dev/null | wc -l | tr -d ' ') || true
        CAT_PASS=${CAT_PASS:-0}
        CAT_FAIL=${CAT_FAIL:-0}
        CAT_TOTAL=$((CAT_PASS + CAT_FAIL))

        if [ "${CAT_TOTAL}" -gt 0 ]; then
            MARKER=""
            if [ "${CAT_FAIL}" -gt 0 ]; then
                MARKER=" FAIL"
            fi
            printf "  %-20s %6d %6d %6d%s\n" "${CAT}" "${CAT_PASS}" "${CAT_FAIL}" "${CAT_TOTAL}" "${MARKER}"
        fi
    done

    echo "  -------------------------------------------"
fi

if [ -n "${ERRORS}" ]; then
    echo ""
    echo "FAILURES:"
    echo "${ERRORS}"
    echo ""
fi

# Report location
if [ "${REPORT_MODE}" = true ] && [ -d "${REPORT_DIR}" ]; then
    REPORT_FILE=$(ls -t "${REPORT_DIR}"/*.json 2>/dev/null | head -1)
    if [ -n "${REPORT_FILE}" ]; then
        echo "Report: ${REPORT_FILE}"
    fi
fi

echo "Full log: ${TEST_LOG}"

# Exit with failure if any tests failed
if [ "${FAILED}" -gt 0 ]; then
    echo ""
    echo "RESULT: FAIL"
    exit 1
fi

if [ "${TOTAL}" -eq 0 ]; then
    echo ""
    echo "WARNING: No tests matched filter '${TEST_FILTER}'"
    echo "         Try: $0 --list"
    exit 2
fi

# -- Retro-notes nudge -------------------------------------------------------
# Remind agents to document observations when they have uncommitted changes.
if git -C "${PROJECT_ROOT}" diff --name-only HEAD 2>/dev/null | grep -qE "^Source/|^Tools/PlayUnreal/"; then
    echo ""
    echo "  [Retro] You have uncommitted changes in Source/ or Tools/PlayUnreal/."
    echo "  [Retro] Add observations to .team/retro-notes.md as you go."
fi

echo ""
echo "RESULT: PASS"
exit 0
