"""Predictive safe-path planner for Frogger-style games.

Strategy: instead of waiting at one column for a gap to pass, FIND the
nearest column that's already safe and move there. Like a human player
who looks at the whole lane and picks the gap.

Incremental: queries fresh hazard data before each dangerous hop.
Measured API latency: ~9ms. Hop response: ~33ms.

Usage:
    from path_planner import navigate_to_home_slot
    result = navigate_to_home_slot(pu, target_col=6)
"""

import json
import os
import time

# Game constants — defaults, call init_from_config() to overwrite from live game
CELL_SIZE = 100.0  # SYNC: Source/UnrealFrog/Public/Core/FrogCharacter.h:GridCellSize
GRID_COLS = 13  # SYNC: Source/UnrealFrog/Public/Core/FrogCharacter.h:GridColumns
HOP_DURATION = 0.15  # SYNC: Source/UnrealFrog/Public/Core/FrogCharacter.h:HopDuration
SAFE_ROWS = {0, 6, 13}
ROAD_ROWS = {1, 2, 3, 4, 5}
RIVER_ROWS = {7, 8, 9, 10, 11, 12}
HOME_ROW = 14  # SYNC: Source/UnrealFrog/Public/Core/UnrealFrogGameMode.h:HomeSlotRow
HOME_COLS = {1, 4, 6, 8, 11}

# Collision geometry
FROG_CAPSULE_RADIUS = 34.0  # SYNC: Source/UnrealFrog/Private/Core/FrogCharacter.cpp:InitCapsuleSize
# Safety margin: capsule (34) + generous buffer (80) = 114 total.
# At 250 u/s (fastest hazard), 114 units = 0.46s of margin.
SAFETY_MARGIN = 80.0

# Platform landing margin: frog center must be this far inside the platform edge.
# Game uses FROG_CAPSULE_RADIUS (34). We add 10 UU buffer for prediction drift.
PLATFORM_INSET = FROG_CAPSULE_RADIUS + 10.0  # 44 UU

# Measured timing (from debug_navigation.py)
API_LATENCY = 0.01  # 9ms measured
HOP_RESPONSE = 0.035  # 33ms until position changes
POST_HOP_WAIT = HOP_DURATION + 0.04  # total wait after hop command


# -- Runtime config sync (Task #5) -------------------------------------------
# Call init_from_config(config_dict) to overwrite defaults from GetGameConfigJSON().
# Fallback: reads game_constants.json from disk if present.

_CONFIG_LOADED = False


def init_from_config(config):
    """Overwrite module-level constants from a GetGameConfigJSON() dict."""
    global CELL_SIZE, GRID_COLS, HOP_DURATION, HOME_ROW, FROG_CAPSULE_RADIUS
    global PLATFORM_INSET, POST_HOP_WAIT, _CONFIG_LOADED
    if not config or _CONFIG_LOADED:
        return
    if "cellSize" in config:
        CELL_SIZE = float(config["cellSize"])
    if "gridCols" in config:
        GRID_COLS = int(config["gridCols"])
    if "hopDuration" in config:
        HOP_DURATION = float(config["hopDuration"])
        POST_HOP_WAIT = HOP_DURATION + 0.04
    if "homeRow" in config:
        HOME_ROW = int(config["homeRow"])
    if "capsuleRadius" in config:
        FROG_CAPSULE_RADIUS = float(config["capsuleRadius"])
    if "platformLandingMargin" in config:
        PLATFORM_INSET = float(config["platformLandingMargin"]) + 10.0
    elif "capsuleRadius" in config:
        PLATFORM_INSET = FROG_CAPSULE_RADIUS + 10.0
    _CONFIG_LOADED = True


def _try_load_fallback_config():
    """Try to load game_constants.json from disk at import time."""
    fallback_paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "game_constants.json"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "Saved", "game_constants.json"),
    ]
    for path in fallback_paths:
        if os.path.exists(path):
            try:
                with open(path) as f:
                    config = json.loads(f.read())
                init_from_config(config)
                return
            except (json.JSONDecodeError, IOError):
                continue


_try_load_fallback_config()


def predict_hazard_x(hazard, dt):
    """Predict hazard CENTER X after dt seconds."""
    x0 = hazard["x"]
    speed = hazard["speed"]
    direction = 1.0 if hazard["movesRight"] else -1.0
    world_width = hazard["width"] * CELL_SIZE
    wrap_min = -world_width
    wrap_max = GRID_COLS * CELL_SIZE + world_width
    wrap_range = wrap_max - wrap_min
    raw_x = x0 + speed * direction * dt
    return ((raw_x - wrap_min) % wrap_range) + wrap_min


def is_column_safe_for_hop(hazards_in_row, col, duration=HOP_DURATION):
    """Check if column `col` is safe for the frog for the full hop duration.

    Checks at 8 time samples across [0, duration] to catch fast movers.
    A column is safe if no hazard's extent + margin overlaps the frog.
    """
    frog_x = col * CELL_SIZE
    danger = FROG_CAPSULE_RADIUS + SAFETY_MARGIN  # 114 units

    check_times = [i * duration / 7 for i in range(8)]

    for h in hazards_in_row:
        if h.get("rideable", False):
            continue
        half_w = h["width"] * CELL_SIZE * 0.5
        for t in check_times:
            hx = predict_hazard_x(h, t)
            if abs(frog_x - hx) < half_w + danger:
                return False
    return True


def find_safe_road_column(hazards_in_row, current_col, preferred_col):
    """Find the nearest column that's safe to hop through RIGHT NOW.

    Searches outward from current_col, preferring the direction of preferred_col.
    Returns (safe_col, wait) where wait is always 0.0 (gap exists now).
    """
    # First check current column
    if is_column_safe_for_hop(hazards_in_row, current_col):
        return current_col, 0.0

    # Search outward, biased toward preferred direction
    for dist in range(1, GRID_COLS):
        # Try direction toward preferred first
        if preferred_col >= current_col:
            candidates = [current_col + dist, current_col - dist]
        else:
            candidates = [current_col - dist, current_col + dist]

        for col in candidates:
            if 0 <= col < GRID_COLS:
                if is_column_safe_for_hop(hazards_in_row, col):
                    return col, 0.0

    # No column is safe right now — wait briefly and return current
    # (the retry loop will re-query hazards next iteration)
    return current_col, 0.3


def find_platform_column(hazards_in_row, current_col, max_wait=4.0):
    """Find the best column to hop to for landing on a river platform.

    Searches for the column + wait combination that gets the frog onto
    a platform soonest, with minimal lateral movement.

    Returns (target_col, wait_time) or (None, None) if impossible.
    """
    rideables = [h for h in hazards_in_row if h.get("rideable", False)]
    if not rideables:
        return None, None

    best_col = None
    best_wait = max_wait
    best_score = float("inf")  # lower is better: wait + lateral_penalty

    # Check all columns within reasonable lateral distance
    for col in range(max(0, current_col - 4), min(GRID_COLS, current_col + 5)):
        frog_x = col * CELL_SIZE
        lateral_cost = abs(col - current_col) * POST_HOP_WAIT  # time to move there

        # Scan forward in time for a platform at this column
        for wait in _frange(0.0, max_wait, 0.02):
            arrival = wait + HOP_DURATION
            on_platform = False
            for h in rideables:
                hx = predict_hazard_x(h, arrival)
                half_w = h["width"] * CELL_SIZE * 0.5
                # Match game's FindPlatformAtCurrentPosition: |frog - hazard| <= half_w - capsule_radius
                # PLATFORM_INSET adds extra buffer beyond the game's check
                if abs(frog_x - hx) <= half_w - PLATFORM_INSET:
                    on_platform = True
                    break

            if on_platform:
                score = wait + lateral_cost
                if score < best_score:
                    best_score = score
                    best_col = col
                    best_wait = wait
                break  # Found earliest wait for this column

    return best_col, best_wait


def _frange(start, stop, step):
    """Float range generator."""
    val = start
    while val < stop:
        yield val
        val += step


def _get_frog_pos(state):
    """Extract (col, row) from game state."""
    pos = state.get("frogPos", [6, 0])
    col = int(pos[0]) if isinstance(pos, list) and len(pos) > 0 else 6
    row = int(pos[1]) if isinstance(pos, list) and len(pos) > 1 else 0
    return col, row


def _get_frog_world_x(state):
    """Get frog's actual world X position (accounts for platform drift)."""
    world_x = state.get("frogWorldX")
    if world_x is not None:
        return float(world_x)
    # Fallback: use grid position * cell size
    col, _ = _get_frog_pos(state)
    return col * CELL_SIZE


def _find_current_platform(hazards, frog_row, frog_world_x):
    """Find which platform the frog is currently riding.

    Returns (speed, direction) or (0.0, 0.0) if not on a platform.
    """
    row_hazards = [h for h in hazards if h.get("row") == frog_row
                   and h.get("rideable", False)]
    for h in row_hazards:
        half_w = h["width"] * CELL_SIZE * 0.5
        if abs(frog_world_x - h["x"]) <= half_w + 10.0:
            direction = 1.0 if h["movesRight"] else -1.0
            return h["speed"], direction
    return 0.0, 0.0


def _find_platform_at_world_x(next_row_hazards, frog_world_x, max_wait=4.0,
                               drift_speed=0.0, drift_dir=0.0):
    """Find when a next-row platform will align with the frog's position.

    Accounts for the frog DRIFTING with its current platform during the wait.
    At time T, the frog will be at: frog_world_x + drift_speed * drift_dir * T.

    Returns wait_time or None if no platform coming.
    """
    rideables = [h for h in next_row_hazards if h.get("rideable", False)]
    if not rideables:
        return None

    for wait in _frange(0.0, max_wait, 0.02):
        arrival = wait + HOP_DURATION
        # Where will the FROG be at arrival time? (drifting with current platform)
        frog_x_at_arrival = frog_world_x + drift_speed * drift_dir * arrival
        for h in rideables:
            hx = predict_hazard_x(h, arrival)
            half_w = h["width"] * CELL_SIZE * 0.5
            if abs(frog_x_at_arrival - hx) <= half_w - PLATFORM_INSET:
                return wait
    return None


def _is_lateral_safe(hazards, frog_row, target_col):
    """Check if a lateral hop to target_col is safe on the current row.

    For road rows: check road hazards at target_col.
    For river rows: check frog will land on a platform at target_col.
    For safe rows: always safe.
    """
    if frog_row in SAFE_ROWS:
        return True

    row_hazards = [h for h in hazards if h.get("row") == frog_row]

    if frog_row in ROAD_ROWS:
        road_hazards = [h for h in row_hazards if not h.get("rideable", False)]
        return is_column_safe_for_hop(road_hazards, target_col)

    if frog_row in RIVER_ROWS:
        # On river: must stay on a platform. Check if target_col has one.
        rideables = [h for h in row_hazards if h.get("rideable", False)]
        frog_x = target_col * CELL_SIZE
        for h in rideables:
            half_w = h["width"] * CELL_SIZE * 0.5
            # Check at t=0 (current) and t=HOP_DURATION (arrival)
            for t in (0.0, HOP_DURATION):
                hx = predict_hazard_x(h, t)
                if abs(frog_x - hx) <= half_w - PLATFORM_INSET:
                    return True
        return False  # No platform at target column

    return True  # Unknown row type, allow


def navigate_to_home_slot(pu, target_col=6, max_deaths=8):
    """Navigate frog from current position to a home slot.

    One-hop-at-a-time strategy:
    - Each iteration: query state, query hazards, decide ONE hop, execute,
      re-query actual position. No multi-hop sequences with stale data.
    - Road rows: if current column safe for next row, hop up. Otherwise,
      take one lateral step toward a safe column (checking current row too).
    - River rows: wait for platform, hop onto it. On a platform, hop up
      when next row has a platform too.
    - Always re-query actual position after each hop.

    Args:
        pu: PlayUnreal client instance
        target_col: home slot column to aim for (default 6)
        max_deaths: give up after this many deaths

    Returns:
        dict with success, total_hops, deaths, elapsed, state
    """
    # Sync constants from live game if not already loaded
    if not _CONFIG_LOADED:
        try:
            config = pu.get_config()
            init_from_config(config)
        except Exception:
            pass

    total_hops = 0
    deaths = 0
    initial_filled = None
    start = time.time()
    max_iterations = 200  # safety limit

    for _ in range(max_iterations):
        state = pu.get_state()
        gs = state.get("gameState", "")

        if gs == "GameOver":
            return _result(False, total_hops, deaths, start, state)
        if gs in ("Dying", "Spawning"):
            deaths += 1
            time.sleep(1.5)
            continue
        if gs == "RoundComplete":
            return _result(True, total_hops, deaths, start, state)
        if gs != "Playing":
            time.sleep(0.3)
            continue

        filled = state.get("homeSlotsFilledCount", 0)
        if initial_filled is None:
            initial_filled = filled
        if filled > initial_filled:
            return _result(True, total_hops, deaths, start, state)

        frog_col, frog_row = _get_frog_pos(state)

        if frog_row >= HOME_ROW:
            return _result(True, total_hops, deaths, start, state)

        next_row = frog_row + 1
        hazards = pu.get_hazards()

        # --- Safe row ahead: align toward target or hop forward ---
        if next_row in SAFE_ROWS or next_row >= HOME_ROW:
            if frog_row in SAFE_ROWS and frog_col != target_col:
                # Align laterally on safe row (no hazards to worry about)
                d = "right" if frog_col < target_col else "left"
                pu.hop(d)
                total_hops += 1
                time.sleep(POST_HOP_WAIT)
                continue
            pu.hop("up")
            total_hops += 1
            time.sleep(POST_HOP_WAIT)
            continue

        # --- Road row ahead ---
        if next_row in ROAD_ROWS:
            next_row_hazards = [h for h in hazards
                                if h.get("row") == next_row
                                and not h.get("rideable", False)]

            # No hazards on next row — hop forward
            if not next_row_hazards:
                pu.hop("up")
                total_hops += 1
                time.sleep(POST_HOP_WAIT)
                continue

            # Current column safe for next row? Hop forward.
            if is_column_safe_for_hop(next_row_hazards, frog_col):
                pu.hop("up")
                total_hops += 1
                time.sleep(POST_HOP_WAIT)
                continue

            # Need lateral movement — try both directions
            # Check each neighbor: safe on current row AND closer to a
            # column that's safe on the next row
            best_step = None
            for step_dir in (1, -1):
                step_col = frog_col + step_dir
                if step_col < 0 or step_col >= GRID_COLS:
                    continue
                if not _is_lateral_safe(hazards, frog_row, step_col):
                    continue
                # This step is safe on current row — is it useful?
                if is_column_safe_for_hop(next_row_hazards, step_col):
                    # Can hop up from here next iteration!
                    best_step = step_dir
                    break
                # Check if it gets us closer to ANY safe column
                if best_step is None:
                    best_step = step_dir

            if best_step is None:
                # Neither direction safe — try hopping backward to escape
                prev_row = frog_row - 1
                if prev_row >= 0:
                    prev_safe = True
                    if prev_row in ROAD_ROWS:
                        prev_hazards = [h for h in hazards
                                        if h.get("row") == prev_row
                                        and not h.get("rideable", False)]
                        prev_safe = is_column_safe_for_hop(
                            prev_hazards, frog_col)
                    if prev_safe:
                        pu.hop("down")
                        total_hops += 1
                        time.sleep(POST_HOP_WAIT)
                        continue
                # Can't go anywhere — wait and retry
                time.sleep(0.05)
                continue

            d = "right" if best_step > 0 else "left"
            pu.hop(d)
            total_hops += 1
            time.sleep(POST_HOP_WAIT)
            continue

        # --- River row ahead ---
        if next_row in RIVER_ROWS:
            row_hazards = [h for h in hazards if h.get("row") == next_row]

            if frog_row in RIVER_ROWS:
                # ON a log — use actual world X + drift prediction
                frog_wx = _get_frog_world_x(state)
                drift_spd, drift_dir = _find_current_platform(
                    hazards, frog_row, frog_wx)
                plat_wait = _find_platform_at_world_x(
                    row_hazards, frog_wx, max_wait=4.0,
                    drift_speed=drift_spd, drift_dir=drift_dir)
                if plat_wait is None:
                    time.sleep(0.1)
                    continue

                if plat_wait > 0.02:
                    time.sleep(plat_wait)
                    # Re-confirm with fresh state
                    fresh_state = pu.get_state()
                    frog_wx = _get_frog_world_x(fresh_state)
                    hazards = pu.get_hazards()
                    row_hazards = [h for h in hazards
                                   if h.get("row") == next_row]
                    drift_spd, drift_dir = _find_current_platform(
                        hazards, frog_row, frog_wx)
                    plat_wait = _find_platform_at_world_x(
                        row_hazards, frog_wx, max_wait=1.0,
                        drift_speed=drift_spd, drift_dir=drift_dir)
                    if plat_wait is None:
                        continue
                    if plat_wait > 0.02:
                        time.sleep(plat_wait)

                pu.hop("up")
                total_hops += 1
                time.sleep(POST_HOP_WAIT)
                continue
            else:
                # On a safe row — can move laterally to align
                plat_col, plat_wait = find_platform_column(
                    row_hazards, frog_col, max_wait=6.0)

                if plat_col is None:
                    time.sleep(0.2)
                    continue

                if frog_col != plat_col:
                    step_dir = 1 if plat_col > frog_col else -1
                    step_col = frog_col + step_dir
                    d = "right" if step_dir > 0 else "left"
                    pu.hop(d)
                    total_hops += 1
                    time.sleep(POST_HOP_WAIT)
                    continue

                # At the right column — wait for platform then hop
                if plat_wait is not None and plat_wait > 0.02:
                    time.sleep(plat_wait)

                pu.hop("up")
                total_hops += 1
                time.sleep(POST_HOP_WAIT)
                continue

        # Unknown row — hop forward
        pu.hop("up")
        total_hops += 1
        time.sleep(POST_HOP_WAIT)

    return _result(False, total_hops, deaths, start,
                   pu.get_state() if pu else {})


def _result(success, total_hops, deaths, start, state):
    return {
        "success": success,
        "total_hops": total_hops,
        "deaths": deaths,
        "elapsed": time.time() - start,
        "state": state,
    }


# Legacy API compatibility for verify_visuals.py
def plan_path(hazards, frog_col=6, frog_row=0, target_col=6,
              target_row=HOME_ROW):
    """Legacy API — returns list of {"wait", "direction"} dicts."""
    path = []
    current_col = frog_col
    current_row = frog_row

    hazards_by_row = {}
    for h in hazards:
        r = h.get("row", -1)
        if r not in hazards_by_row:
            hazards_by_row[r] = []
        hazards_by_row[r].append(h)

    while current_row < target_row:
        if current_row in SAFE_ROWS and current_col != target_col:
            while current_col != target_col:
                d = "right" if current_col < target_col else "left"
                path.append({"wait": 0.0, "direction": d})
                current_col += (1 if d == "right" else -1)

        next_row = current_row + 1

        if next_row in SAFE_ROWS or next_row >= HOME_ROW:
            path.append({"wait": 0.0, "direction": "up"})
            current_row = next_row
            continue

        row_hazards = hazards_by_row.get(next_row, [])
        if not row_hazards:
            path.append({"wait": 0.0, "direction": "up"})
            current_row = next_row
            continue

        if next_row in ROAD_ROWS:
            safe_col, wait = find_safe_road_column(row_hazards, current_col, target_col)
            while current_col != safe_col:
                d = "right" if current_col < safe_col else "left"
                path.append({"wait": 0.0, "direction": d})
                current_col += (1 if d == "right" else -1)
            path.append({"wait": wait, "direction": "up"})
        else:
            plat_col, plat_wait = find_platform_column(row_hazards, current_col)
            if plat_col is not None:
                while current_col != plat_col:
                    d = "right" if current_col < plat_col else "left"
                    path.append({"wait": 0.0, "direction": d})
                    current_col += (1 if d == "right" else -1)
                path.append({"wait": max(plat_wait or 0, 0.0), "direction": "up"})
            else:
                path.append({"wait": 0.5, "direction": "up"})

        current_row = next_row

    return path


def execute_path(pu, path):
    """Legacy API — execute a pre-planned path."""
    total_hops = 0
    start_time = time.time()
    for step in path:
        if step["wait"] > 0.02:
            time.sleep(step["wait"])
        pu.hop(step["direction"])
        total_hops += 1
        time.sleep(POST_HOP_WAIT)
    return {"hops": total_hops, "elapsed": time.time() - start_time}
