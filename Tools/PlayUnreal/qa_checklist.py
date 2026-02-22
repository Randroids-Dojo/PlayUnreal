"""QA Sprint Sign-Off Checklist -- minimum verification before "QA: verified".

This script is the QA Lead's gate. It connects to a running UnrealFrog game
via the PlayUnreal client, exercises basic gameplay, and verifies the game is
responsive and functional. If this script does not print "QA CHECKLIST: PASS",
the QA Lead MUST NOT sign off on the sprint.

Usage:
    python3 Tools/PlayUnreal/qa_checklist.py

Prerequisites:
    - Editor running with Remote Control API enabled (use run-playunreal.sh)

Exit codes:
    0 = PASS (all checks passed)
    1 = FAIL (one or more checks failed)
    2 = CONNECTION ERROR (game not running or RC API not responding)
"""

import json
import os
import sys
import time

# Add script directory to path so we can import client
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from client import PlayUnreal, PlayUnrealError, ConnectionError as PUConnectionError

SCREENSHOT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "Saved", "Screenshots", "qa_checklist"
)

# Track results
_results = []
_failures = []


def log(msg):
    print(f"[QA] {msg}")


def check(name, condition, detail=""):
    """Record a checklist item result."""
    status = "PASS" if condition else "FAIL"
    entry = f"  [{status}] {name}"
    if detail:
        entry += f" -- {detail}"
    _results.append((name, condition, detail))
    if not condition:
        _failures.append(name)
    print(entry)
    return condition


def main():
    log("=" * 60)
    log("QA SPRINT SIGN-OFF CHECKLIST")
    log("=" * 60)
    log("")

    # ----------------------------------------------------------------
    # 1. Connection check
    # ----------------------------------------------------------------
    log("--- Step 1: Connection ---")
    pu = PlayUnreal(timeout=10)

    if not pu.is_alive():
        log("")
        log("FATAL: Remote Control API is not responding on localhost:30010")
        log("       Launch the editor with: ./Tools/PlayUnreal/run-playunreal.sh")
        log("")
        log("QA CHECKLIST: CANNOT RUN (no game connection)")
        return 2

    check("RC API responding", True)
    log("")

    # ----------------------------------------------------------------
    # 2. Game state is readable
    # ----------------------------------------------------------------
    log("--- Step 2: Game State ---")
    try:
        state = pu.get_state()
        state_readable = isinstance(state, dict) and len(state) > 0
        check("get_state() returns valid dict", state_readable,
              f"keys: {list(state.keys()) if state_readable else 'empty'}")

        game_state = state.get("gameState", None)
        check("gameState field present", game_state is not None,
              f"value: {game_state}")
    except PlayUnrealError as e:
        check("get_state() returns valid dict", False, str(e))
        state = {}

    log("")

    # ----------------------------------------------------------------
    # 3. Reset and start a new game
    # ----------------------------------------------------------------
    log("--- Step 3: Game Reset ---")
    try:
        pu.reset_game()
        time.sleep(1.0)
        state = pu.get_state()
        game_state_str = str(state.get("gameState", ""))
        is_playing = "play" in game_state_str.lower() or game_state_str == "2"
        check("Game resets and enters Playing state", is_playing,
              f"state after reset: {game_state_str}")
    except PlayUnrealError as e:
        check("Game resets and enters Playing state", False, str(e))

    log("")

    # ----------------------------------------------------------------
    # 4. Hop the frog forward 3 times, verify position changes
    # ----------------------------------------------------------------
    log("--- Step 4: Hop Verification (3 forward hops) ---")
    try:
        state_before = pu.get_state()
        pos_before = state_before.get("frogPos", [0, 0])
        score_before = state_before.get("score", 0)
        lives_before = state_before.get("lives", 0)

        log(f"  Before: pos={pos_before}, score={score_before}, lives={lives_before}")

        for i in range(3):
            pu.hop("up")
            time.sleep(0.4)  # HopDuration=0.15s + generous margin

        state_after = pu.get_state()
        pos_after = state_after.get("frogPos", [0, 0])
        score_after = state_after.get("score", 0)
        lives_after = state_after.get("lives", 0)

        log(f"  After:  pos={pos_after}, score={score_after}, lives={lives_after}")

        # Position should have changed (frog moved forward)
        pos_changed = pos_after != pos_before
        check("Frog position changed after hops", pos_changed,
              f"before={pos_before}, after={pos_after}")

        # Score should have increased (forward hops award points)
        score_increased = score_after > score_before
        check("Score increased after forward hops", score_increased,
              f"before={score_before}, after={score_after}")

        # Lives should not have decreased (safe zone hops)
        lives_ok = lives_after >= lives_before
        # If lives decreased, the frog died -- not necessarily a failure
        # of the checklist but worth noting
        if not lives_ok:
            check("Frog survived 3 hops in safe zone", False,
                  f"lives went from {lives_before} to {lives_after}")
        else:
            check("Frog survived 3 hops in safe zone", True,
                  f"lives={lives_after}")

    except PlayUnrealError as e:
        check("Hop commands accepted", False, str(e))

    log("")

    # ----------------------------------------------------------------
    # 5. Game still responsive after gameplay
    # ----------------------------------------------------------------
    log("--- Step 5: Post-Gameplay Responsiveness ---")
    try:
        final_state = pu.get_state()
        check("Game still responsive after hops", isinstance(final_state, dict),
              f"keys: {list(final_state.keys())}")
    except PlayUnrealError as e:
        check("Game still responsive after hops", False, str(e))

    log("")

    # ----------------------------------------------------------------
    # 6. Screenshot capture
    # ----------------------------------------------------------------
    log("--- Step 6: Screenshot ---")
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    screenshot_path = os.path.join(SCREENSHOT_DIR, "qa_checklist.png")
    try:
        pu.screenshot(screenshot_path)
        check("Screenshot command sent", True,
              f"path: {screenshot_path}")
    except PlayUnrealError as e:
        check("Screenshot command sent", False, str(e))

    log("")

    # ----------------------------------------------------------------
    # Summary
    # ----------------------------------------------------------------
    log("=" * 60)
    total = len(_results)
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = total - passed

    log(f"  Total checks: {total}")
    log(f"  Passed:       {passed}")
    log(f"  Failed:       {failed}")

    if _failures:
        log("")
        log("  Failed checks:")
        for name in _failures:
            log(f"    - {name}")

    log("")
    if failed == 0:
        log("QA CHECKLIST: PASS")
        log("")
        log("The QA Lead may sign off with 'QA: verified' in the commit message.")
        return 0
    else:
        log("QA CHECKLIST: FAIL")
        log("")
        log("The QA Lead MUST NOT sign off. Fix failures and re-run.")
        log("If visual verification is impossible, use 'QA: code-level only, visual PENDING'.")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PUConnectionError as e:
        log(f"CONNECTION ERROR: {e}")
        log("")
        log("QA CHECKLIST: CANNOT RUN (no game connection)")
        sys.exit(2)
    except PlayUnrealError as e:
        log(f"UNEXPECTED ERROR: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        log("Interrupted.")
        sys.exit(130)
