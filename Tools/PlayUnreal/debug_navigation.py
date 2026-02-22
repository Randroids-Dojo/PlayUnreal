"""Diagnostic navigation script — logs timing data for every hop.

Measures actual API latency, hazard prediction accuracy, and identifies
exactly where and why the frog dies or gets stuck.

Usage:
    ./Tools/PlayUnreal/run-playunreal.sh debug_navigation.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from client import PlayUnreal
import path_planner

# Lane config for reference
LANE_INFO = {
    1: {"type": "Car",        "speed": 150, "width": 1, "gap": 3, "right": False},
    2: {"type": "Truck",      "speed": 100, "width": 2, "gap": 4, "right": True},
    3: {"type": "Car",        "speed": 200, "width": 1, "gap": 2, "right": False},
    4: {"type": "Bus",        "speed": 175, "width": 2, "gap": 3, "right": True},
    5: {"type": "Motorcycle", "speed": 250, "width": 1, "gap": 2, "right": False},
    7: {"type": "SmallLog",   "speed": 100, "width": 2, "gap": 2, "right": True},
    8: {"type": "TurtleGrp",  "speed":  80, "width": 3, "gap": 2, "right": False},
    9: {"type": "LargeLog",   "speed": 120, "width": 4, "gap": 2, "right": True},
   10: {"type": "SmallLog",   "speed": 100, "width": 2, "gap": 2, "right": False},
   11: {"type": "TurtleGrp",  "speed":  80, "width": 3, "gap": 2, "right": True},
   12: {"type": "LargeLog",   "speed": 150, "width": 4, "gap": 2, "right": False},
}


def log(msg):
    print(f"[DEBUG] {msg}")


def measure_api_latency(pu, samples=10):
    """Measure actual RC API round-trip time."""
    times = []
    for _ in range(samples):
        t0 = time.time()
        pu.get_state()
        t1 = time.time()
        times.append(t1 - t0)
    avg = sum(times) / len(times)
    mn = min(times)
    mx = max(times)
    log(f"API Latency ({samples} samples): avg={avg*1000:.0f}ms, "
        f"min={mn*1000:.0f}ms, max={mx*1000:.0f}ms")
    return avg


def measure_hop_latency(pu):
    """Measure: time from hop() call to frog position actually changing."""
    state0 = pu.get_state()
    pos0 = state0.get("frogPos", [6, 0])
    log(f"  Before hop: frogPos={pos0}")

    t_send = time.time()
    pu.hop("right")  # lateral hop on safe row — won't die

    # Poll until position changes
    for i in range(50):
        time.sleep(0.01)
        state = pu.get_state()
        pos = state.get("frogPos", pos0)
        if pos != pos0:
            t_changed = time.time()
            log(f"  Position changed after {(t_changed - t_send)*1000:.0f}ms: {pos0} -> {pos}")
            return t_changed - t_send

    log(f"  Position did NOT change after 500ms!")
    return 0.5


def log_hazard_state(hazards, target_row):
    """Log all hazards in a specific row."""
    row_h = [h for h in hazards if h.get("row") == target_row]
    info = LANE_INFO.get(target_row, {})
    log(f"  Row {target_row} ({info.get('type', '?')}, "
        f"speed={info.get('speed', '?')}, w={info.get('width', '?')}, "
        f"{'R' if info.get('right') else 'L'}): {len(row_h)} hazards")
    for h in row_h:
        half_w = h["width"] * path_planner.CELL_SIZE * 0.5
        log(f"    x={h['x']:.0f} (extent {h['x']-half_w:.0f} to {h['x']+half_w:.0f}), "
            f"speed={h['speed']:.0f}, {'R' if h['movesRight'] else 'L'}, "
            f"rideable={h.get('rideable', False)}")
    return row_h


def predict_hazard_x(hazard, dt):
    """Delegate to path_planner.predict_hazard_x."""
    return path_planner.predict_hazard_x(hazard, dt)


def find_gaps(hazards_in_row, frog_x):
    """Analyze when gaps pass frog_x in the next 5 seconds."""
    danger_radius = path_planner.FROG_CAPSULE_RADIUS + 40  # 74 units total

    log(f"  Scanning for gaps at frog_x={frog_x:.0f} "
        f"(danger zone +/-{danger_radius:.0f} around hazard center + half_w)")
    safe_windows = []
    t = 0.0
    was_safe = None
    window_start = None

    while t < 5.0:
        all_clear = True
        for h in hazards_in_row:
            if h.get("rideable", False):
                continue
            hx = predict_hazard_x(h, t)
            half_w = h["width"] * path_planner.CELL_SIZE * 0.5
            if abs(frog_x - hx) < half_w + danger_radius:
                all_clear = False
                break

        if all_clear and not was_safe:
            window_start = t
        elif not all_clear and was_safe and window_start is not None:
            safe_windows.append((window_start, t))
            window_start = None
        was_safe = all_clear
        t += 0.01

    if was_safe and window_start is not None:
        safe_windows.append((window_start, 5.0))

    for start, end in safe_windows[:5]:
        log(f"    Gap: {start:.2f}s - {end:.2f}s (duration {end-start:.2f}s)")
    if not safe_windows:
        log(f"    NO GAPS in 5s! (column {frog_x/path_planner.CELL_SIZE:.0f} is blocked)")
    return safe_windows


def find_platform_windows(hazards_in_row, frog_x):
    """Analyze when rideable platforms cover frog_x."""
    rideables = [h for h in hazards_in_row if h.get("rideable", False)]
    if not rideables:
        log(f"  NO rideable platforms in row!")
        return []

    margin = 20.0
    log(f"  Scanning for platforms covering frog_x={frog_x:.0f} "
        f"(need |frog_x - hx| <= half_w - {margin:.0f})")
    windows = []
    t = 0.0
    was_on = False
    window_start = None

    while t < 8.0:
        on_platform = False
        for h in rideables:
            hx = predict_hazard_x(h, t)
            half_w = h["width"] * path_planner.CELL_SIZE * 0.5
            if abs(frog_x - hx) <= half_w - margin:
                on_platform = True
                break

        if on_platform and not was_on:
            window_start = t
        elif not on_platform and was_on and window_start is not None:
            windows.append((window_start, t))
            window_start = None
        was_on = on_platform
        t += 0.01

    if was_on and window_start is not None:
        windows.append((window_start, 8.0))

    for start, end in windows[:5]:
        log(f"    Platform at frog: {start:.2f}s - {end:.2f}s (duration {end-start:.2f}s)")
    if not windows:
        log(f"    NO platform passes frog_x={frog_x:.0f} in 8s!")
        # Show where platforms DO pass
        for h in rideables:
            for check_t in [0.0, 1.0, 2.0, 3.0, 4.0]:
                hx = predict_hazard_x(h, check_t)
                half_w = h["width"] * path_planner.CELL_SIZE * 0.5
                log(f"    t={check_t:.0f}s: platform center={hx:.0f}, "
                    f"extent={hx-half_w:.0f} to {hx+half_w:.0f}")
    return windows


def attempt_road_crossing(pu, frog_row, frog_col, api_latency):
    """Cross one road row with detailed logging."""
    next_row = frog_row + 1
    frog_x = frog_col * path_planner.CELL_SIZE

    log(f"\n=== Crossing road row {next_row} from ({frog_col},{frog_row}) ===")

    hazards = pu.get_hazards()
    row_h = log_hazard_state(hazards, next_row)

    if not row_h:
        log("  No hazards — hopping immediately")
        pu.hop("up")
        time.sleep(path_planner.HOP_DURATION + 0.04)
        return True

    gaps = find_gaps(row_h, frog_x)
    if not gaps:
        log("  BLOCKED — no gaps in 5s at this column")
        return False

    # Pick the first gap that starts after now + API latency
    # Need gap to last at least path_planner.HOP_DURATION
    chosen = None
    for start, end in gaps:
        duration = end - start
        if duration >= path_planner.HOP_DURATION and start >= 0:
            chosen = (start, end)
            break

    if chosen is None:
        log("  No gap wide enough for hop duration!")
        return False

    wait_time = max(0, chosen[0] - api_latency)
    log(f"  Chosen gap: {chosen[0]:.2f}s - {chosen[1]:.2f}s")
    log(f"  Wait time: {wait_time:.3f}s (gap_start={chosen[0]:.3f} - api_lag={api_latency:.3f})")

    if wait_time > 0.02:
        log(f"  Sleeping {wait_time:.3f}s...")
        time.sleep(wait_time)

    # Hop and measure
    t_hop = time.time()
    pu.hop("up")
    time.sleep(path_planner.HOP_DURATION + 0.04)

    state = pu.get_state()
    gs = state.get("gameState", "")
    pos = state.get("frogPos", [frog_col, frog_row])
    t_after = time.time()

    log(f"  After hop ({(t_after-t_hop)*1000:.0f}ms): pos={pos}, state={gs}")

    if gs in ("Dying", "Spawning"):
        log(f"  *** DIED on row {next_row}! ***")
        # Re-query hazards to see where they actually were
        time.sleep(0.5)
        hazards_after = pu.get_hazards()
        row_after = [h for h in hazards_after if h.get("row") == next_row]
        log(f"  Hazards at death time (approx):")
        for h in row_after:
            half_w = h["width"] * path_planner.CELL_SIZE * 0.5
            log(f"    x={h['x']:.0f} (extent {h['x']-half_w:.0f} to {h['x']+half_w:.0f})")
        return False

    return True


def attempt_river_crossing(pu, frog_row, frog_col, api_latency):
    """Cross one river row with detailed logging."""
    next_row = frog_row + 1
    frog_x = frog_col * path_planner.CELL_SIZE

    log(f"\n=== Crossing river row {next_row} from ({frog_col},{frog_row}) ===")

    hazards = pu.get_hazards()
    row_h = log_hazard_state(hazards, next_row)

    rideables = [h for h in row_h if h.get("rideable", False)]
    if not rideables:
        log("  NO rideable platforms — cannot cross!")
        return False

    windows = find_platform_windows(row_h, frog_x)

    if not windows:
        log("  No platform window at this column — trying adjacent columns")
        for offset in [-1, 1, -2, 2, -3, 3]:
            alt_x = (frog_col + offset) * path_planner.CELL_SIZE
            alt_windows = find_platform_windows(row_h, alt_x)
            if alt_windows:
                log(f"  Found platform at col {frog_col + offset}, moving laterally")
                # Only move laterally on safe rows
                if frog_row in path_planner.SAFE_ROWS:
                    direction = "right" if offset > 0 else "left"
                    for _ in range(abs(offset)):
                        pu.hop(direction)
                        time.sleep(path_planner.HOP_DURATION + 0.04)
                    frog_col += offset
                    frog_x = frog_col * path_planner.CELL_SIZE
                    windows = alt_windows
                    break
        if not windows:
            log("  Cannot find any reachable platform!")
            return False

    # Pick first window — need arrival at (wait + path_planner.HOP_DURATION)
    chosen = windows[0]
    # We want the frog to arrive DURING the window
    # Arrival time = wait + path_planner.HOP_DURATION
    # So wait = window_start - path_planner.HOP_DURATION - api_latency
    target_arrival = chosen[0] + (chosen[1] - chosen[0]) / 2  # aim for center of window
    wait_time = max(0, target_arrival - path_planner.HOP_DURATION - api_latency)

    log(f"  Chosen window: {chosen[0]:.2f}s - {chosen[1]:.2f}s")
    log(f"  Target arrival: {target_arrival:.3f}s")
    log(f"  Wait time: {wait_time:.3f}s")

    if wait_time > 0.02:
        log(f"  Sleeping {wait_time:.3f}s...")
        time.sleep(wait_time)

    t_hop = time.time()
    pu.hop("up")
    time.sleep(path_planner.HOP_DURATION + 0.04)

    state = pu.get_state()
    gs = state.get("gameState", "")
    pos = state.get("frogPos", [frog_col, frog_row])
    t_after = time.time()

    log(f"  After hop ({(t_after-t_hop)*1000:.0f}ms): pos={pos}, state={gs}")

    if gs in ("Dying", "Spawning"):
        log(f"  *** DIED on river row {next_row}! ***")
        return False

    return True


def main():
    pu = PlayUnreal()
    if not pu.is_alive():
        log("Cannot connect to RC API!")
        sys.exit(2)

    # Sync constants from live game
    try:
        config = pu.get_config()
        path_planner.init_from_config(config)
    except Exception:
        pass

    log("=== Navigation Diagnostics ===")
    log(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Phase 1: Measure latency
    log("\n--- Phase 1: API Latency ---")
    api_latency = measure_api_latency(pu)

    # Phase 2: Measure hop latency
    log("\n--- Phase 2: Hop Latency ---")
    # Reset to playing state first
    try:
        pu._call_function(pu._get_gm_path(), "ReturnToTitle")
        time.sleep(0.5)
        pu._call_function(pu._get_gm_path(), "StartGame")
        time.sleep(1.0)
    except Exception as e:
        log(f"Reset failed: {e}")

    hop_latency = measure_hop_latency(pu)
    log(f"  Hop latency: {hop_latency*1000:.0f}ms (time until position changes)")

    # Hop back to original position
    pu.hop("left")
    time.sleep(path_planner.HOP_DURATION + 0.04)

    # Phase 3: Full hazard layout dump
    log("\n--- Phase 3: Full Hazard Layout ---")
    hazards = pu.get_hazards()
    log(f"Total hazards: {len(hazards)}")
    for row in sorted(set(h["row"] for h in hazards)):
        log_hazard_state(hazards, row)

    # Phase 4: Attempt crossing row by row with detailed logging
    log("\n--- Phase 4: Row-by-Row Crossing ---")

    state = pu.get_state()
    pos = state.get("frogPos", [6, 0])
    frog_col = int(pos[0]) if isinstance(pos, list) else 6
    frog_row = int(pos[1]) if isinstance(pos, list) and len(pos) > 1 else 0

    log(f"Starting position: ({frog_col}, {frog_row})")

    for target_row in range(frog_row + 1, 15):
        state = pu.get_state()
        gs = state.get("gameState", "")
        if gs != "Playing":
            log(f"\nGame state is {gs} — stopping")
            if gs in ("Dying", "Spawning"):
                log("Waiting for respawn...")
                time.sleep(2.0)
                state = pu.get_state()
                pos = state.get("frogPos", [6, 0])
                frog_col = int(pos[0]) if isinstance(pos, list) else 6
                frog_row = int(pos[1]) if isinstance(pos, list) and len(pos) > 1 else 0
                log(f"Respawned at ({frog_col}, {frog_row})")
                continue
            break

        pos = state.get("frogPos", [frog_col, frog_row])
        frog_col = int(pos[0]) if isinstance(pos, list) else frog_col
        frog_row = int(pos[1]) if isinstance(pos, list) and len(pos) > 1 else frog_row

        if target_row in path_planner.SAFE_ROWS:
            log(f"\n=== Row {target_row} is SAFE — hopping immediately ===")
            pu.hop("up")
            time.sleep(path_planner.HOP_DURATION + 0.04)
            frog_row = target_row
            continue

        if target_row in path_planner.ROAD_ROWS:
            success = attempt_road_crossing(pu, frog_row, frog_col, api_latency)
            if success:
                frog_row = target_row
            else:
                log("Road crossing failed — stopping diagnostic")
                break

        elif target_row in path_planner.RIVER_ROWS:
            success = attempt_river_crossing(pu, frog_row, frog_col, api_latency)
            if success:
                frog_row = target_row
                # After river hop, re-query position (platform drift)
                time.sleep(0.1)
                state = pu.get_state()
                pos = state.get("frogPos", [frog_col, frog_row])
                new_col = int(pos[0]) if isinstance(pos, list) else frog_col
                if new_col != frog_col:
                    log(f"  Platform drift: col {frog_col} -> {new_col}")
                    frog_col = new_col
            else:
                log("River crossing failed — stopping diagnostic")
                break

        elif target_row >= 14:
            log(f"\n=== Row {target_row} is HOME — hopping ===")
            pu.hop("up")
            time.sleep(path_planner.HOP_DURATION + 0.04)
            frog_row = target_row

    # Final state
    log("\n--- Final State ---")
    final = pu.get_state()
    log(f"Position: {final.get('frogPos')}")
    log(f"State: {final.get('gameState')}")
    log(f"Score: {final.get('score')}")
    log(f"Lives: {final.get('lives')}")
    log(f"HomeFilled: {final.get('homeSlotsFilledCount')}")

    log("\n=== Diagnostic Complete ===")


if __name__ == "__main__":
    main()
