#!/usr/bin/env python3
"""Sample smoke test — minimal example of using PlayUnreal.

This script connects to a running Unreal Engine game, verifies the
connection, reads game state, and sends a few commands.

Usage:
    python3 examples/sample_project/smoke_test.py
"""

import os
import sys
import time

# Add the python package to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "python"))

from playunreal import PlayUnreal, PlayUnrealError


def main():
    print("=== PlayUnreal Smoke Test ===")
    print()

    # 1. Connect
    pu = PlayUnreal()
    if not pu.is_alive():
        print("ERROR: Remote Control API not responding on localhost:30010")
        print("       Launch the game with Remote Control enabled first.")
        return 1

    print("[OK] Connected to Remote Control API")

    # 2. Read state
    state = pu.get_state()
    print(f"[OK] Game state: {state.get('gameState', 'unknown')}")
    print(f"     Score: {state.get('score', '?')}")
    print(f"     Lives: {state.get('lives', '?')}")

    # 3. Reset and play
    print()
    print("Resetting game...")
    pu.reset_game()
    time.sleep(0.5)

    state = pu.get_state()
    print(f"[OK] State after reset: {state.get('gameState', 'unknown')}")

    # 4. Send a few hops
    print()
    print("Sending 3 hops (right, right, up)...")
    for direction in ["right", "right", "up"]:
        pu.hop(direction)
        time.sleep(0.3)
        state = pu.get_state()
        pos = state.get("frogPos", [0, 0])
        print(f"  hop({direction}) -> pos={pos}, score={state.get('score', 0)}")

    # 5. Diagnostics
    print()
    report = pu.diagnose()
    gm_live = report["gamemode"]["is_live"]
    char_live = report["character"]["is_live"]
    print(f"[{'OK' if gm_live else 'WARN'}] GameMode: "
          f"{'live instance' if gm_live else 'CDO only'}")
    print(f"[{'OK' if char_live else 'WARN'}] Character: "
          f"{'live instance' if char_live else 'CDO only'}")

    print()
    print("=== Smoke Test Complete ===")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PlayUnrealError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("Interrupted.")
        sys.exit(130)
