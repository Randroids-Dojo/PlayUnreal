#!/usr/bin/env bash
# play-game.sh — Launch UnrealFrog in PIE (Play-In-Editor) mode
#
# Usage:
#   ./Tools/PlayUnreal/play-game.sh           # Launch editor with auto-PIE
#   ./Tools/PlayUnreal/play-game.sh --editor  # Launch editor only (no auto-play)
#
# Requirements:
#   - UE 5.7 installed at /Users/Shared/Epic Games/UE_5.7/
#   - UnrealFrogEditor target built (Editor build)
#   - FroggerMain.umap exists (run Tools/CreateMap/create_frog_map.py first)

set -euo pipefail

# -- Configuration -----------------------------------------------------------

ENGINE_DIR="/Users/Shared/Epic Games/UE_5.7"
EDITOR="${ENGINE_DIR}/Engine/Binaries/Mac/UnrealEditor"
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT_FILE="${PROJECT_ROOT}/UnrealFrog.uproject"

MODE="${1:---play}"

# -- Validation --------------------------------------------------------------

if [ ! -f "${EDITOR}" ]; then
    echo "ERROR: UnrealEditor not found at: ${EDITOR}"
    echo "       Is UE 5.7 installed?"
    exit 1
fi

if [ ! -f "${PROJECT_FILE}" ]; then
    echo "ERROR: Project file not found at: ${PROJECT_FILE}"
    exit 1
fi

# -- Launch ------------------------------------------------------------------

echo "============================================"
echo "  UnrealFrog — Play Game"
echo "============================================"
echo "  Engine:  ${ENGINE_DIR}"
echo "  Project: ${PROJECT_FILE}"
echo "  Mode:    ${MODE}"
echo "============================================"
echo ""

case "${MODE}" in
    --editor)
        echo "Launching Unreal Editor..."
        "${EDITOR}" "${PROJECT_FILE}" &
        ;;
    --play|*)
        echo "Launching Unreal Editor with auto-PIE..."
        echo "(Press Play manually if auto-PIE doesn't trigger)"
        "${EDITOR}" "${PROJECT_FILE}" \
            -game \
            -windowed \
            -ResX=1280 -ResY=720 \
            -log &
        ;;
esac

echo ""
echo "Editor launched (PID: $!)"
echo "Use arrow keys to move the frog. Escape to pause."
