"""Minimal test: navigate frog to home slot using the one-hop-at-a-time planner.

Logs every decision and hop. Run with:
    ./Tools/PlayUnreal/run-playunreal.sh test_crossing.py
"""

import os
import sys
import time
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from client import PlayUnreal
import path_planner
from path_planner import (
    navigate_to_home_slot, find_safe_road_column, find_platform_column,
    is_column_safe_for_hop, predict_hazard_x, _is_lateral_safe, _get_frog_pos,
    _get_frog_world_x, _find_platform_at_world_x, _find_current_platform,
)


def log(msg):
    print(f"[NAV] {msg}")


def log_hazards(hazards, row, label="hazard"):
    """Log hazard positions for a specific row."""
    row_h = [h for h in hazards if h.get("row") == row]
    for h in row_h:
        half_w = h["width"] * path_planner.CELL_SIZE * 0.5
        rideable = h.get("rideable", False)
        kind = "platform" if rideable else label
        log(f"  Row {row} {kind}: center={h['x']:.0f} "
            f"({h['x']-half_w:.0f} to {h['x']+half_w:.0f}), "
            f"speed={h['speed']:.0f}, {'R' if h['movesRight'] else 'L'}")


def logged_navigate(pu, target_col=6, max_deaths=8):
    """Navigate with detailed per-hop logging — one hop at a time."""
    total_hops = 0
    deaths = 0
    initial_filled = None
    start = time.time()

    for iteration in range(200):
        state = pu.get_state()
        gs = state.get("gameState", "")

        if gs == "GameOver":
            log(f"GAME OVER after {total_hops} hops, {deaths} deaths")
            return False
        if gs in ("Dying", "Spawning"):
            deaths += 1
            log(f"Death #{deaths} — waiting for respawn...")
            time.sleep(1.5)
            continue
        if gs == "RoundComplete":
            log(f"ROUND COMPLETE! Hops={total_hops}, deaths={deaths}, "
                f"time={time.time()-start:.1f}s")
            return True
        if gs != "Playing":
            time.sleep(0.3)
            continue

        filled = state.get("homeSlotsFilledCount", 0)
        if initial_filled is None:
            initial_filled = filled
        if filled > initial_filled:
            log(f"HOME SLOT FILLED! ({filled}/{5}) Hops={total_hops}, "
                f"deaths={deaths}, time={time.time()-start:.1f}s")
            return True

        frog_col, frog_row = _get_frog_pos(state)

        if frog_row >= path_planner.HOME_ROW:
            log("Reached home row!")
            return True

        next_row = frog_row + 1
        hazards = pu.get_hazards()

        # --- Safe row ahead: align or hop forward ---
        if next_row in path_planner.SAFE_ROWS or next_row >= path_planner.HOME_ROW:
            if frog_row in path_planner.SAFE_ROWS and frog_col != target_col:
                d = "right" if frog_col < target_col else "left"
                log(f"  [{frog_col},{frog_row}] Safe — align {d} toward col {target_col}")
                pu.hop(d)
                total_hops += 1
                time.sleep(path_planner.POST_HOP_WAIT)
                continue
            log(f"  [{frog_col},{frog_row}] -> row {next_row} (safe/home)")
            pu.hop("up")
            total_hops += 1
            time.sleep(path_planner.POST_HOP_WAIT)
            continue

        # --- Road row ahead ---
        if next_row in path_planner.ROAD_ROWS:
            next_row_hazards = [h for h in hazards
                                if h.get("row") == next_row
                                and not h.get("rideable", False)]

            if not next_row_hazards:
                log(f"  [{frog_col},{frog_row}] -> road row {next_row} (no hazards)")
                pu.hop("up")
                total_hops += 1
                time.sleep(path_planner.POST_HOP_WAIT)
                continue

            log_hazards(hazards, next_row, "car")

            # Current column safe for next row?
            col_safe = is_column_safe_for_hop(next_row_hazards, frog_col)
            log(f"  [{frog_col},{frog_row}] Col {frog_col} safe for row {next_row}: {col_safe}")

            if col_safe:
                log(f"  [{frog_col},{frog_row}] -> road row {next_row} (HOP!)")
                t0 = time.time()
                pu.hop("up")
                total_hops += 1
                time.sleep(path_planner.POST_HOP_WAIT)

                # Verify result
                post = pu.get_state()
                post_pos = _get_frog_pos(post)
                post_gs = post.get("gameState", "")
                log(f"  Result: pos={post_pos}, state={post_gs} "
                    f"({(time.time()-t0)*1000:.0f}ms)")
                if post_gs in ("Dying", "Spawning"):
                    log(f"  *** DIED ON ROW {next_row} ***")
                    log_hazards(pu.get_hazards(), next_row, "car")
                continue

            # Need lateral movement — try both directions
            best_step = None
            best_reason = ""
            for step_dir in (1, -1):
                step_col = frog_col + step_dir
                d_name = "right" if step_dir > 0 else "left"
                if step_col < 0 or step_col >= 13:
                    continue
                if not _is_lateral_safe(hazards, frog_row, step_col):
                    log(f"  Try {d_name} to col {step_col}: blocked on row {frog_row}")
                    continue
                if is_column_safe_for_hop(next_row_hazards, step_col):
                    log(f"  Try {d_name} to col {step_col}: safe on BOTH rows!")
                    best_step = step_dir
                    best_reason = "safe for both rows"
                    break
                if best_step is None:
                    log(f"  Try {d_name} to col {step_col}: safe on current row")
                    best_step = step_dir
                    best_reason = "safe on current row"

            if best_step is None:
                # Try hopping backward to escape
                prev_row = frog_row - 1
                if prev_row >= 0:
                    prev_safe = True
                    if prev_row in path_planner.ROAD_ROWS:
                        prev_hazards = [h for h in hazards
                                        if h.get("row") == prev_row
                                        and not h.get("rideable", False)]
                        prev_safe = is_column_safe_for_hop(
                            prev_hazards, frog_col)
                    if prev_safe:
                        log(f"  Both sides blocked — hopping DOWN to row {prev_row}")
                        pu.hop("down")
                        total_hops += 1
                        time.sleep(path_planner.POST_HOP_WAIT)
                        continue
                log(f"  Stuck — waiting 50ms")
                log_hazards(hazards, frog_row, "car")
                time.sleep(0.05)
                continue

            step_col = frog_col + best_step
            d = "right" if best_step > 0 else "left"
            log(f"  [{frog_col},{frog_row}] -> col {step_col} ({d}, {best_reason})")
            pu.hop(d)
            total_hops += 1
            time.sleep(path_planner.POST_HOP_WAIT)
            continue

        # --- River row ahead ---
        if next_row in path_planner.RIVER_ROWS:
            row_hazards = [h for h in hazards if h.get("row") == next_row]
            rideables = [h for h in row_hazards if h.get("rideable", False)]

            log(f"  [{frog_col},{frog_row}] River row {next_row}: "
                f"{len(rideables)} platforms")
            log_hazards(hazards, next_row)

            if frog_row in path_planner.RIVER_ROWS:
                # ON a log — use actual world X + drift prediction
                frog_wx = _get_frog_world_x(state)
                drift_spd, drift_dir = _find_current_platform(
                    hazards, frog_row, frog_wx)
                log(f"  On log: worldX={frog_wx:.0f} (grid col {frog_col}), "
                    f"drift={drift_spd:.0f}*{drift_dir:.0f}")
                plat_wait = _find_platform_at_world_x(
                    row_hazards, frog_wx, max_wait=4.0,
                    drift_speed=drift_spd, drift_dir=drift_dir)
                if plat_wait is None:
                    log(f"  No platform coming — waiting")
                    time.sleep(0.1)
                    continue
                log(f"  Platform arrives in {plat_wait:.2f}s")

                if plat_wait > 0.02:
                    log(f"  Waiting {plat_wait:.2f}s...")
                    time.sleep(plat_wait)
                    # Re-confirm with fresh position
                    state = pu.get_state()
                    frog_wx = _get_frog_world_x(state)
                    hazards = pu.get_hazards()
                    row_hazards = [h for h in hazards
                                   if h.get("row") == next_row]
                    drift_spd, drift_dir = _find_current_platform(
                        hazards, frog_row, frog_wx)
                    plat_wait = _find_platform_at_world_x(
                        row_hazards, frog_wx, max_wait=1.0,
                        drift_speed=drift_spd, drift_dir=drift_dir)
                    if plat_wait is None:
                        log(f"  Platform missed at worldX={frog_wx:.0f}! Retrying")
                        continue
                    if plat_wait > 0.02:
                        log(f"  Re-wait {plat_wait:.2f}s")
                        time.sleep(plat_wait)
            else:
                # On safe row — can move laterally to align
                plat_col, plat_wait = find_platform_column(
                    row_hazards, frog_col, max_wait=6.0)

                if plat_col is None:
                    log(f"  NO platform found! Waiting 200ms...")
                    time.sleep(0.2)
                    continue

                log(f"  Best platform: col {plat_col}, wait={plat_wait:.2f}s")

                if frog_col != plat_col:
                    step_dir = 1 if plat_col > frog_col else -1
                    step_col = frog_col + step_dir
                    d = "right" if step_dir > 0 else "left"
                    log(f"  Safe row — align {d} to col {step_col}")
                    pu.hop(d)
                    total_hops += 1
                    time.sleep(path_planner.POST_HOP_WAIT)
                    continue

                # At the right column — wait for platform then hop
                if plat_wait is not None and plat_wait > 0.02:
                    log(f"  Waiting {plat_wait:.2f}s for platform...")
                    time.sleep(plat_wait)

            log(f"  [{frog_col},{frog_row}] -> river row {next_row} (HOP!)")
            t0 = time.time()
            pu.hop("up")
            total_hops += 1
            time.sleep(path_planner.POST_HOP_WAIT)

            # Check result and track drift
            post = pu.get_state()
            post_col, post_row = _get_frog_pos(post)
            post_gs = post.get("gameState", "")
            log(f"  Result: pos=({post_col},{post_row}), state={post_gs} "
                f"({(time.time()-t0)*1000:.0f}ms)")
            if post_col != frog_col:
                log(f"  Platform drift: col {frog_col} -> {post_col}")
            if post_gs in ("Dying", "Spawning"):
                log(f"  *** DIED IN RIVER ROW {next_row} ***")
            continue

        # Unknown row
        log(f"  [{frog_col},{frog_row}] -> row {next_row} (unknown type)")
        pu.hop("up")
        total_hops += 1
        time.sleep(path_planner.POST_HOP_WAIT)

    log(f"Ran out of iterations. Hops={total_hops}, deaths={deaths}")
    return False


def main():
    pu = PlayUnreal()
    if not pu.is_alive():
        print("Cannot connect to RC API!")
        sys.exit(2)

    # Sync game constants from the running game
    try:
        config = pu.get_config()
        path_planner.init_from_config(config)
    except Exception:
        pass  # Proceed with defaults or fallback file

    log("=== One-Hop-At-A-Time Navigation Test ===")
    log(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Measure API latency
    times = []
    for _ in range(5):
        t0 = time.time()
        pu.get_state()
        times.append(time.time() - t0)
    log(f"API Latency: avg={sum(times)/len(times)*1000:.0f}ms")

    # Reset to playing
    try:
        pu._call_function(pu._get_gm_path(), "ReturnToTitle")
        time.sleep(0.5)
        pu._call_function(pu._get_gm_path(), "StartGame")
        time.sleep(1.0)
    except Exception as e:
        log(f"Reset failed: {e}")
        sys.exit(1)

    state = pu.get_state()
    log(f"Starting state: {json.dumps(state, indent=2)}")

    # Navigate!
    success = logged_navigate(pu, target_col=6)

    log(f"\n{'SUCCESS' if success else 'FAILED'}")

    final = pu.get_state()
    log(f"Final: pos={final.get('frogPos')}, state={final.get('gameState')}, "
        f"score={final.get('score')}, lives={final.get('lives')}, "
        f"filled={final.get('homeSlotsFilledCount')}")


if __name__ == "__main__":
    main()
