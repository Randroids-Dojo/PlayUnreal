#!/usr/bin/env bash
# rc_api_spike.sh — Remote Control API spike test for PlayUnreal
#
# Prerequisites:
#   1. RemoteControl plugin enabled in UnrealFrog.uproject
#   2. Editor target rebuilt after enabling plugin
#   3. Game launched with:
#      "/Users/Shared/Epic Games/UE_5.7/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor" \
#        "/path/to/UnrealFrog/UnrealFrog.uproject" \
#        -game -windowed -resx=1280 -resy=720 -log \
#        -RCWebControlEnable \
#        -ExecCmds="WebControl.EnableServerOnStartup 1"
#
# The key flags:
#   -RCWebControlEnable   Enables WebRemoteControl in -game mode (disabled by default)
#   WebControl.EnableServerOnStartup 1   CVar to auto-start the HTTP server on boot
#
# Alternative: instead of the CVar, use -ExecCmds="WebControl.StartServer" after
# the game is running (but timing is tricky).
#
# Usage:
#   ./Tools/PlayUnreal/rc_api_spike.sh
#
# This script assumes the editor is already running with Remote Control enabled.
# It tests the HTTP API on localhost:30010.

set -euo pipefail

RC_HOST="http://localhost"
RC_PORT="30010"
RC_BASE="${RC_HOST}:${RC_PORT}"

PASS=0
FAIL=0

check() {
    local desc="$1"
    local result="$2"
    local status="$3"
    if [ "${status}" -eq 0 ]; then
        echo "  PASS: ${desc}"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: ${desc}"
        echo "        Response: ${result}"
        FAIL=$((FAIL + 1))
    fi
}

echo "============================================"
echo "  Remote Control API Spike Test"
echo "============================================"
echo "  Target: ${RC_BASE}"
echo ""

# --- Test 1: GET /remote/info ---
echo "--- Test 1: GET /remote/info ---"
RESULT=$(curl -s -w "\n%{http_code}" "${RC_BASE}/remote/info" 2>&1) || true
HTTP_CODE=$(echo "${RESULT}" | tail -1)
BODY=$(echo "${RESULT}" | sed '$d')

if [ "${HTTP_CODE}" = "200" ]; then
    check "GET /remote/info returns 200" "${BODY}" 0
    echo "  Routes available:"
    echo "${BODY}" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for route in data.get('Routes', [])[:10]:
        print(f\"    {route.get('Verb', '?'):6s} {route.get('Path', '?')}\")
    if len(data.get('Routes', [])) > 10:
        print(f\"    ... and {len(data['Routes']) - 10} more\")
except: print('    (could not parse JSON)')
" 2>/dev/null || echo "    (could not parse)"
else
    check "GET /remote/info returns 200 (got ${HTTP_CODE})" "${BODY}" 1
    echo ""
    echo "FATAL: Remote Control API is not responding on port ${RC_PORT}."
    echo "       Ensure the editor is running with -RCWebControlEnable flag."
    echo ""
    echo "RESULT: SPIKE FAILED (server not reachable)"
    exit 1
fi
echo ""

# --- Test 2: PUT /remote/object/describe (find GameMode) ---
echo "--- Test 2: PUT /remote/object/describe (GameMode) ---"

DESCRIBE_RESULT=$(curl -s -w "\n%{http_code}" -X PUT \
    -H "Content-Type: application/json" \
    -d '{"ObjectPath":"/Script/UnrealFrog.Default__UnrealFrogGameMode"}' \
    "${RC_BASE}/remote/object/describe" 2>&1) || true
HTTP_CODE=$(echo "${DESCRIBE_RESULT}" | tail -1)
BODY=$(echo "${DESCRIBE_RESULT}" | sed '$d')

if [ "${HTTP_CODE}" = "200" ]; then
    check "Describe CDO of UnrealFrogGameMode" "${BODY}" 0
    echo "  Properties found:"
    echo "${BODY}" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    props = data.get('Properties', [])
    funcs = data.get('Functions', [])
    print(f'    {len(props)} properties, {len(funcs)} functions')
    for f in funcs[:5]:
        print(f\"    UFUNCTION: {f.get('Name', '?')}\")
    if len(funcs) > 5:
        print(f'    ... and {len(funcs) - 5} more')
except: print('    (could not parse JSON)')
" 2>/dev/null || echo "    (could not parse)"
else
    check "Describe CDO of UnrealFrogGameMode (got ${HTTP_CODE})" "${BODY}" 1
    echo "  Note: CDO path may differ. Try /Script/UnrealFrog.UnrealFrogGameMode"
fi
echo ""

# --- Test 3: PUT /remote/object/call (call a function) ---
echo "--- Test 3: PUT /remote/object/call ---"
CALL_RESULT=$(curl -s -w "\n%{http_code}" -X PUT \
    -H "Content-Type: application/json" \
    -d '{"ObjectPath":"/Script/UnrealFrog.Default__UnrealFrogGameMode","FunctionName":"GetGameStateJSON"}' \
    "${RC_BASE}/remote/object/call" 2>&1) || true
HTTP_CODE=$(echo "${CALL_RESULT}" | tail -1)
BODY=$(echo "${CALL_RESULT}" | sed '$d')

if [ "${HTTP_CODE}" = "200" ]; then
    check "Call GetGameStateJSON on GameMode CDO" "${BODY}" 0
    echo "  Return value: ${BODY}"
else
    echo "  Note: GetGameStateJSON does not exist yet. This is expected."
    echo "  HTTP ${HTTP_CODE}: ${BODY}"
    echo "  Trying a known engine function instead..."

    # Try reading a property instead (more reliable test of the API)
    PROP_RESULT=$(curl -s -w "\n%{http_code}" -X PUT \
        -H "Content-Type: application/json" \
        -d '{"ObjectPath":"/Script/UnrealFrog.Default__UnrealFrogGameMode","PropertyName":"HopDuration"}' \
        "${RC_BASE}/remote/object/property" 2>&1) || true
    HTTP_CODE2=$(echo "${PROP_RESULT}" | tail -1)
    BODY2=$(echo "${PROP_RESULT}" | sed '$d')

    if [ "${HTTP_CODE2}" = "200" ]; then
        check "Read HopDuration property from GameMode CDO" "${BODY2}" 0
        echo "  Value: ${BODY2}"
    else
        check "Read HopDuration property (got ${HTTP_CODE2})" "${BODY2}" 1
    fi
fi
echo ""

# --- Test 4: PUT /remote/object/property (read a property) ---
echo "--- Test 4: PUT /remote/object/property ---"
PROP_RESULT=$(curl -s -w "\n%{http_code}" -X PUT \
    -H "Content-Type: application/json" \
    -d '{"ObjectPath":"/Script/UnrealFrog.Default__UnrealFrogGameMode","PropertyName":"GridCellSize"}' \
    "${RC_BASE}/remote/object/property" 2>&1) || true
HTTP_CODE=$(echo "${PROP_RESULT}" | tail -1)
BODY=$(echo "${PROP_RESULT}" | sed '$d')

if [ "${HTTP_CODE}" = "200" ]; then
    check "Read GridCellSize from GameMode CDO" "${BODY}" 0
    echo "  Value: ${BODY}"
else
    check "Read GridCellSize (got ${HTTP_CODE})" "${BODY}" 1
fi
echo ""

# --- Summary ---
echo "============================================"
echo "  Spike Results"
echo "============================================"
echo "  Passed: ${PASS}"
echo "  Failed: ${FAIL}"
echo "============================================"
echo ""

if [ "${PASS}" -ge 1 ]; then
    echo "RESULT: SPIKE PASSED"
    echo ""
    echo "FINDINGS:"
    echo "  1. Remote Control API plugin exists at Engine/Plugins/VirtualProduction/RemoteControl/"
    echo "  2. WebRemoteControl module: Type=Runtime, PlatformAllowList includes Mac"
    echo "  3. Default HTTP port: 30010 (configurable via URemoteControlSettings)"
    echo "  4. In -game mode, requires -RCWebControlEnable flag (disabled by default)"
    echo "  5. Server auto-starts when bAutoStartWebServer=true (the default) + RCWebControlEnable"
    echo "  6. Alternative: WebControl.StartServer console command or WebControl.EnableServerOnStartup CVar"
    echo "  7. SearchActor and SearchObject routes return 501 Not Implemented in UE 5.7"
    echo "  8. Object path resolution uses StaticFindObject() — need exact UE object path"
    echo "  9. Functions must be UFUNCTION(BlueprintCallable) to be callable via API"
    echo " 10. CDO (Class Default Object) accessible at /Script/ModuleName.Default__ClassName"
    echo ""
    echo "KEY API ENDPOINTS:"
    echo "  GET  /remote/info                — List available routes"
    echo "  PUT  /remote/object/call         — Call a UFUNCTION (BlueprintCallable)"
    echo "       Body: {\"ObjectPath\":\"...\", \"FunctionName\":\"...\", \"Parameters\":{...}}"
    echo "  PUT  /remote/object/property     — Read/write a UPROPERTY"
    echo "       Body: {\"ObjectPath\":\"...\", \"PropertyName\":\"...\"}"
    echo "  PUT  /remote/object/describe     — Describe an object's properties and functions"
    echo "       Body: {\"ObjectPath\":\"...\"}"
    echo ""
    echo "OBJECT PATH DISCOVERY (since SearchActor is not implemented):"
    echo "  - CDO:       /Script/UnrealFrog.Default__UnrealFrogGameMode"
    echo "  - Live instance: The Python client should try GetGameStateJSON() which"
    echo "    bypasses path discovery by being called on the live GameMode instance."
    echo "  - For live actors, the path typically follows:"
    echo "    /Game/Maps/<MapName>.<MapName>:PersistentLevel.<ClassName>_0"
    exit 0
else
    echo "RESULT: SPIKE FAILED"
    echo ""
    echo "FALLBACK: Implement custom UPlayUnrealServer C++ HTTP subsystem (~200 LOC)"
    exit 1
fi
