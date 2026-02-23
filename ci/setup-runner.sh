#!/usr/bin/env bash
# setup-runner.sh — Register this Mac as a GitHub Actions self-hosted runner for PlayUnreal CI.
#
# Usage:
#   ./ci/setup-runner.sh [OPTIONS]
#
# Options:
#   --token TOKEN       GitHub runner registration token (required unless --check-only)
#   --runner-dir DIR    Where to install the runner (default: ~/actions-runner)
#   --runner-name NAME  Runner name (default: <hostname>-mac-ue)
#   --check-only        Only verify prerequisites, don't install
#   --start             Start the runner service
#   --stop              Stop the runner service
#   --restart           Restart the runner service
#   --status            Show runner service status
#   --uninstall         Remove the runner service and deregister
#
# How to get a registration token:
#   1. Go to https://github.com/Randroids-Dojo/PlayUnreal/settings/actions/runners/new
#   2. Copy the token shown in the "Configure" step, OR run:
#      gh api repos/Randroids-Dojo/PlayUnreal/actions/runners/registration-token --method POST --jq '.token'
#
# Prerequisites this script checks:
#   - macOS (arm64 or x86_64)
#   - Unreal Engine 5.x at /Users/Shared/Epic Games/UE_5.x
#   - Python 3.9+
#   - curl
#   - (optional) GitHub CLI for token generation

set -euo pipefail

REPO_URL="https://github.com/Randroids-Dojo/PlayUnreal"
RUNNER_VERSION="2.331.0"
RUNNER_DIR="${HOME}/actions-runner"
RUNNER_NAME="$(hostname -s)-mac-ue"
RUNNER_LABELS="self-hosted,macOS,unreal-engine"
REG_TOKEN=""
CHECK_ONLY=false
UNINSTALL=false
ACTION=""  # start | stop | restart | status

# ── Parse arguments ────────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
    case "$1" in
        --token)      REG_TOKEN="$2"; shift 2 ;;
        --runner-dir) RUNNER_DIR="$2"; shift 2 ;;
        --runner-name) RUNNER_NAME="$2"; shift 2 ;;
        --check-only) CHECK_ONLY=true; shift ;;
        --start)      ACTION=start; shift ;;
        --stop)       ACTION=stop; shift ;;
        --restart)    ACTION=restart; shift ;;
        --status)     ACTION=status; shift ;;
        --uninstall)  UNINSTALL=true; shift ;;
        -h|--help)
            sed -n '2,35p' "$0"   # print the header comment
            exit 0 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

# ── Helpers ────────────────────────────────────────────────────────────────────

ok()   { echo "  [OK]   $*"; }
fail() { echo "  [FAIL] $*"; }
info() { echo "  [INFO] $*"; }
hr()   { echo "──────────────────────────────────────────────────────────────────"; }

# ── Start / Stop / Restart / Status ───────────────────────────────────────────

if [ -n "${ACTION}" ]; then
    if [ ! -d "${RUNNER_DIR}" ]; then
        echo "Runner directory not found: ${RUNNER_DIR}"
        echo "Run ./ci/setup-runner.sh --token <TOKEN> to install first."
        exit 1
    fi
    cd "${RUNNER_DIR}"
    case "${ACTION}" in
        start)
            echo "Starting runner service..."
            ./svc.sh start
            ;;
        stop)
            echo "Stopping runner service..."
            ./svc.sh stop
            ;;
        restart)
            echo "Restarting runner service..."
            ./svc.sh stop
            sleep 2
            ./svc.sh start
            ;;
        status)
            ./svc.sh status
            ;;
    esac
    exit 0
fi

# ── Uninstall path ─────────────────────────────────────────────────────────────

if [ "${UNINSTALL}" = true ]; then
    echo ""
    hr
    echo "  Uninstalling PlayUnreal GitHub Actions runner"
    hr
    if [ ! -d "${RUNNER_DIR}" ]; then
        echo "  Runner directory not found: ${RUNNER_DIR}"
        exit 0
    fi
    cd "${RUNNER_DIR}"
    if [ -f ".service" ]; then
        ./svc.sh stop  2>/dev/null || true
        ./svc.sh uninstall 2>/dev/null || true
        ok "Launchd service removed."
    fi
    if [ -n "${REG_TOKEN}" ]; then
        ./config.sh remove --token "${REG_TOKEN}" 2>/dev/null || true
        ok "Runner deregistered from GitHub."
    else
        info "No --token provided; runner removed locally only (may still show in GitHub)."
    fi
    rm -rf "${RUNNER_DIR}"
    ok "Runner directory removed: ${RUNNER_DIR}"
    exit 0
fi

# ── Prerequisite checks ────────────────────────────────────────────────────────

echo ""
hr
echo "  PlayUnreal CI — Self-Hosted Runner Setup"
hr
echo "  Repo:     ${REPO_URL}"
echo "  Runner:   ${RUNNER_NAME}"
echo "  Labels:   ${RUNNER_LABELS}"
echo "  Dir:      ${RUNNER_DIR}"
echo ""
echo "  Checking prerequisites..."
echo ""

PREREQ_OK=true

# macOS check
if [[ "$(uname -s)" != "Darwin" ]]; then
    fail "This script is for macOS only. (uname: $(uname -s))"
    PREREQ_OK=false
else
    ok "macOS: $(sw_vers -productVersion) ($(uname -m))"
fi

# Architecture
ARCH="$(uname -m)"
case "${ARCH}" in
    arm64)  RUNNER_ARCH="arm64" ;;
    x86_64) RUNNER_ARCH="x64" ;;
    *)
        fail "Unsupported architecture: ${ARCH}"
        PREREQ_OK=false ;;
esac

# Python 3.9+
if command -v python3 &>/dev/null; then
    PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    PY_MAJOR="${PY_VER%%.*}"
    PY_MINOR="${PY_VER##*.}"
    if [[ "${PY_MAJOR}" -ge 3 && "${PY_MINOR}" -ge 9 ]]; then
        ok "Python: ${PY_VER}"
    else
        fail "Python 3.9+ required, found ${PY_VER}. Install via: brew install python@3.11"
        PREREQ_OK=false
    fi
else
    fail "python3 not found. Install via: brew install python@3.11"
    PREREQ_OK=false
fi

# curl
if command -v curl &>/dev/null; then
    ok "curl: $(curl --version | head -1)"
else
    fail "curl not found (should be built into macOS)."
    PREREQ_OK=false
fi

# Unreal Engine
UE_FOUND=""
for ver in "5.7" "5.6" "5.5" "5.4"; do
    candidate="/Users/Shared/Epic Games/UE_${ver}"
    if [ -d "${candidate}" ]; then
        UE_FOUND="${candidate}"
        break
    fi
done

if [ -n "${UE_FOUND}" ]; then
    ok "Unreal Engine: ${UE_FOUND}"
else
    fail "No Unreal Engine 5.x found at /Users/Shared/Epic Games/UE_5.x"
    fail "Install UE via the Epic Games Launcher, then re-run this script."
    PREREQ_OK=false
fi

# GitHub CLI (optional but helpful)
if command -v gh &>/dev/null; then
    ok "GitHub CLI: $(gh --version | head -1)"
else
    info "GitHub CLI not found (optional). Install via: brew install gh"
fi

echo ""

if [ "${PREREQ_OK}" = false ]; then
    echo "  Prerequisites not met. Fix the issues above, then re-run."
    exit 1
fi

if [ "${CHECK_ONLY}" = true ]; then
    echo "  All prerequisites satisfied."
    exit 0
fi

# ── Require token ──────────────────────────────────────────────────────────────

if [ -z "${REG_TOKEN}" ]; then
    echo "  A registration token is required to register the runner."
    echo ""
    echo "  Generate one with:"
    echo "    gh api repos/Randroids-Dojo/PlayUnreal/actions/runners/registration-token \\"
    echo "       --method POST --jq '.token'"
    echo ""
    echo "  Then re-run:"
    echo "    ./ci/setup-runner.sh --token <TOKEN>"
    echo ""
    echo "  Or visit:"
    echo "    https://github.com/Randroids-Dojo/PlayUnreal/settings/actions/runners/new"
    exit 1
fi

# ── Download runner ────────────────────────────────────────────────────────────

echo "  Downloading GitHub Actions runner v${RUNNER_VERSION} (osx-${RUNNER_ARCH})..."
echo ""

RUNNER_PACKAGE="actions-runner-osx-${RUNNER_ARCH}-${RUNNER_VERSION}.tar.gz"
RUNNER_URL="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${RUNNER_PACKAGE}"

mkdir -p "${RUNNER_DIR}"
cd "${RUNNER_DIR}"

if [ -f "config.sh" ]; then
    info "Runner binaries already present in ${RUNNER_DIR} — skipping download."
else
    curl -sL "${RUNNER_URL}" -o "${RUNNER_PACKAGE}"
    tar xzf "${RUNNER_PACKAGE}"
    rm "${RUNNER_PACKAGE}"
    ok "Runner extracted to ${RUNNER_DIR}"
fi

# ── Configure runner ───────────────────────────────────────────────────────────

echo ""
echo "  Configuring runner..."
echo ""

./config.sh \
    --url "${REPO_URL}" \
    --token "${REG_TOKEN}" \
    --name "${RUNNER_NAME}" \
    --labels "${RUNNER_LABELS}" \
    --work "_work" \
    --unattended \
    --replace

ok "Runner configured: ${RUNNER_NAME}"

# ── Set UE_ENGINE_DIR in runner env ───────────────────────────────────────────

# Inject UE_ENGINE_DIR into the runner's .env file so all jobs see it.
if [ -n "${UE_FOUND}" ]; then
    ENV_FILE="${RUNNER_DIR}/.env"
    if grep -q "^UE_ENGINE_DIR=" "${ENV_FILE}" 2>/dev/null; then
        sed -i '' "s|^UE_ENGINE_DIR=.*|UE_ENGINE_DIR=${UE_FOUND}|" "${ENV_FILE}"
    else
        echo "UE_ENGINE_DIR=${UE_FOUND}" >> "${ENV_FILE}"
    fi
    ok "Set UE_ENGINE_DIR=${UE_FOUND} in runner .env"
fi

# ── Install and start launchd service ─────────────────────────────────────────

echo ""
echo "  Installing runner as a launchd service (starts at login)..."
echo ""

./svc.sh install
./svc.sh start

ok "Runner service installed and started."

# ── Verify ────────────────────────────────────────────────────────────────────

echo ""
hr
echo "  Setup complete!"
hr
echo ""
echo "  Runner name:   ${RUNNER_NAME}"
echo "  Labels:        ${RUNNER_LABELS}"
echo "  Runner dir:    ${RUNNER_DIR}"
if [ -n "${UE_FOUND}" ]; then
    echo "  UE_ENGINE_DIR: ${UE_FOUND}"
fi
echo ""
echo "  To check status:    cd ${RUNNER_DIR} && ./svc.sh status"
echo "  To view logs:       tail -f ~/Library/Logs/actions.runner.*/runner.log"
echo "  To stop service:    cd ${RUNNER_DIR} && ./svc.sh stop"
echo "  To uninstall:       ./ci/setup-runner.sh --uninstall --token <REMOVE_TOKEN>"
echo ""
echo "  Verify online at:"
echo "    https://github.com/Randroids-Dojo/PlayUnreal/settings/actions/runners"
echo ""
