"""PlayUnreal client — Python interface to UnrealFrog via Remote Control API.

Uses only urllib.request (no pip dependencies). Requires the editor running
with RemoteControl plugin enabled on localhost:30010.

Usage:
    from client import PlayUnreal
    pu = PlayUnreal()
    pu.reset_game()
    pu.hop("up")
    state = pu.get_state()
    print(state)
"""

import json
import os
import time
import urllib.request
import urllib.error


class PlayUnrealError(Exception):
    """Base exception for PlayUnreal client errors."""
    pass


class RCConnectionError(PlayUnrealError):
    """Editor is not running or Remote Control API is not responding."""
    pass

# Keep backward-compatible alias (shadows builtin, but existing code uses it)
ConnectionError = RCConnectionError


class CallError(PlayUnrealError):
    """A remote function call or property read failed."""
    pass


# Direction name -> FVector as dict for RC API
_DIRECTIONS = {
    "up":    {"X": 0.0, "Y": 1.0, "Z": 0.0},
    "down":  {"X": 0.0, "Y": -1.0, "Z": 0.0},
    "left":  {"X": -1.0, "Y": 0.0, "Z": 0.0},
    "right": {"X": 1.0, "Y": 0.0, "Z": 0.0},
}

# Map name from Config/DefaultEngine.ini
_DEFAULT_MAP = "FroggerMain"


class PlayUnreal:
    """Client for controlling UnrealFrog via Remote Control API.

    Args:
        host: RC API host (default localhost)
        port: RC API port (default 30010)
        timeout: HTTP request timeout in seconds (default 5)
    """

    def __init__(self, host="localhost", port=30010, timeout=5):
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout
        self._gm_path = None
        self._frog_path = None
        self._prev_state = None

    # -- Public API ----------------------------------------------------------

    def hop(self, direction):
        """Send a hop command to the frog.

        Args:
            direction: "up", "down", "left", or "right"
        """
        if direction not in _DIRECTIONS:
            raise ValueError(f"Invalid direction '{direction}'. Use: up, down, left, right")
        frog_path = self._get_frog_path()
        self._call_function(frog_path, "RequestHop", {
            "Direction": _DIRECTIONS[direction]
        })

    def set_invincible(self, enabled):
        """Enable or disable frog invincibility.

        When invincible, Die() is a no-op — the frog cannot be killed
        by hazards or drowning. Useful for acceptance testing where you
        want to test the full path without dying.

        Args:
            enabled: True to enable invincibility, False to disable.
        """
        frog_path = self._get_frog_path()
        self._call_function(frog_path, "SetInvincible", {
            "bEnable": bool(enabled)
        })

    def get_hazards(self):
        """Get all hazard positions and properties as a list of dicts.

        Returns:
            list of dicts, each with keys: row, x, speed, width,
            movesRight, rideable
        """
        gm_path = self._get_gm_path()
        try:
            result = self._call_function(gm_path, "GetLaneHazardsJSON")
            ret_val = result.get("ReturnValue", "")
            if ret_val:
                parsed = json.loads(ret_val)
                return parsed.get("hazards", [])
        except (CallError, json.JSONDecodeError):
            pass
        return []

    _cached_config = None

    def get_config(self):
        """Get game configuration constants as a dict.

        Calls GetGameConfigJSON() on the live GameMode. Falls back to reading
        game_constants.json from disk if the RC API is unavailable.

        Returns:
            dict with keys: cellSize, capsuleRadius, gridCols, hopDuration,
            platformLandingMargin, gridRowCount, homeRow. Empty dict on failure.
        """
        if PlayUnreal._cached_config is not None:
            return PlayUnreal._cached_config

        # Try live RC API first
        try:
            gm_path = self._get_gm_path()
            result = self._call_function(gm_path, "GetGameConfigJSON")
            ret_val = result.get("ReturnValue", "")
            if ret_val:
                config = json.loads(ret_val)
                PlayUnreal._cached_config = config
                return config
        except (CallError, RCConnectionError, json.JSONDecodeError):
            pass

        # Fallback: read from game_constants.json on disk
        fallback_paths = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "game_constants.json"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "..", "Saved", "game_constants.json"),
        ]
        for path in fallback_paths:
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        config = json.loads(f.read())
                    PlayUnreal._cached_config = config
                    return config
                except (json.JSONDecodeError, IOError):
                    continue

        return {}

    def navigate(self, target_col=6, max_deaths=8):
        """Navigate frog to a home slot using predictive path planning.

        Uses one-hop-at-a-time strategy: queries fresh hazard data before
        each hop, computes the safest next move, and executes. Handles
        deaths and game-overs automatically.

        Args:
            target_col: home slot column (1, 4, 6, 8, 11)
            max_deaths: give up after this many deaths

        Returns:
            dict with success, total_hops, deaths, elapsed, state
        """
        from path_planner import navigate_to_home_slot
        return navigate_to_home_slot(self, target_col=target_col,
                                     max_deaths=max_deaths)

    def get_state(self):
        """Get current game state as a dict.

        Returns:
            dict with keys: score, lives, wave, frogPos, gameState,
            timeRemaining, homeSlotsFilledCount

        If GetGameStateJSON() exists on the GameMode, uses that (single call).
        Otherwise falls back to reading individual properties.
        """
        gm_path = self._get_gm_path()

        # Try GetGameStateJSON first (Task 5)
        try:
            result = self._call_function(gm_path, "GetGameStateJSON")
            # The function returns an FString containing JSON
            ret_val = result.get("ReturnValue", "")
            if ret_val:
                return json.loads(ret_val)
        except (CallError, json.JSONDecodeError):
            pass

        # Fallback: read individual properties from GameMode and Frog
        state = {}
        try:
            state["gameState"] = self._read_property(gm_path, "CurrentState")
            state["wave"] = self._read_property(gm_path, "CurrentWave")
            state["homeSlotsFilledCount"] = self._read_property(gm_path, "HomeSlotsFilledCount")
            state["timeRemaining"] = self._read_property(gm_path, "RemainingTime")
        except CallError:
            pass

        try:
            frog_path = self._get_frog_path()
            grid_pos = self._read_property(frog_path, "GridPosition")
            if isinstance(grid_pos, dict):
                state["frogPos"] = [grid_pos.get("X", 0), grid_pos.get("Y", 0)]
            else:
                state["frogPos"] = [0, 0]
        except CallError:
            state["frogPos"] = [0, 0]

        return state

    def get_state_diff(self):
        """Get current state and a diff from the previous state.

        Returns:
            dict with keys:
                current: full current state dict
                changes: dict of keys that changed, each with {old, new}
                         Empty dict on first call (no previous state).
        """
        current = self.get_state()
        changes = {}

        if self._prev_state is not None:
            all_keys = set(list(current.keys()) + list(self._prev_state.keys()))
            for key in all_keys:
                old_val = self._prev_state.get(key)
                new_val = current.get(key)
                if old_val != new_val:
                    changes[key] = {"old": old_val, "new": new_val}

        self._prev_state = current
        return {"current": current, "changes": changes}

    _cached_window_id = None

    def record_video(self, path=None):
        """Record a 3-second video of the game window.

        Uses screencapture -V 3 -l <windowID>. The -l flag imposes a hard
        3-second cap, but that's enough if you send the action BEFORE or
        simultaneously with starting the recording.

        Args:
            path: File path for the .mov video.

        Returns:
            subprocess.Popen handle. Call .wait(timeout=8) when done.
        """
        import subprocess

        if path is None:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "Saved", "Screenshots", "recording.mov")

        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

        # Warm up window ID cache before the action so recording starts fast
        self._get_window_id()

        cmd = ["screencapture", "-V", "3", "-x"]
        wid = PlayUnreal._cached_window_id
        if wid:
            cmd.extend(["-l", wid])
        cmd.append(path)

        return subprocess.Popen(cmd)

    def _get_window_id(self):
        """Get the UnrealEditor window ID, using cache for speed."""
        import subprocess

        if PlayUnreal._cached_window_id:
            return PlayUnreal._cached_window_id

        try:
            result = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to get id of every window '
                 'of every process whose name contains "UnrealEditor"'],
                capture_output=True, text=True, timeout=5
            )
            ids_str = result.stdout.strip()
            if ids_str and ids_str != "":
                for token in ids_str.replace(",", " ").split():
                    token = token.strip()
                    if token.isdigit():
                        PlayUnreal._cached_window_id = token
                        return token
        except (subprocess.TimeoutExpired, Exception):
            pass

        return None

    def screenshot(self, path=None):
        """Take a screenshot of the game window.

        Uses macOS screencapture. Caches window ID after first lookup
        so subsequent calls are fast (important for burst screenshots).

        Args:
            path: File path for the screenshot. If None, uses a default path.

        Returns:
            True if the screenshot was saved successfully.
        """
        import subprocess

        if path is None:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "Saved", "Screenshots", "screenshot.png")

        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

        # Use cached window ID if available
        if PlayUnreal._cached_window_id:
            try:
                subprocess.run(
                    ["screencapture", "-l", PlayUnreal._cached_window_id, "-x", path],
                    timeout=5
                )
                if os.path.exists(path):
                    return True
            except (subprocess.TimeoutExpired, Exception):
                PlayUnreal._cached_window_id = None

        # Look up window ID (slow — only done once)
        try:
            result = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to get id of every window '
                 'of every process whose name contains "UnrealEditor"'],
                capture_output=True, text=True, timeout=5
            )
            ids_str = result.stdout.strip()
            if ids_str and ids_str != "":
                for token in ids_str.replace(",", " ").split():
                    token = token.strip()
                    if token.isdigit():
                        PlayUnreal._cached_window_id = token
                        subprocess.run(
                            ["screencapture", "-l", token, "-x", path],
                            timeout=5
                        )
                        if os.path.exists(path):
                            return True
        except (subprocess.TimeoutExpired, Exception):
            pass

        # Fallback: capture entire main display (fast, no window lookup)
        try:
            subprocess.run(["screencapture", "-x", path], timeout=5)
            return os.path.exists(path)
        except (subprocess.TimeoutExpired, Exception):
            return False

    def reset_game(self):
        """Reset the game to title screen and start a new game.

        Calls ReturnToTitle, polls until Title state is confirmed, then
        StartGame, then polls until Playing. Using wait_for_state avoids
        fixed sleeps that fail when the machine is slow or the game was
        in GameOver (which takes longer to clear than a mid-game reset).
        """
        gm_path = self._get_gm_path()
        self._call_function(gm_path, "ReturnToTitle")
        self.wait_for_state("Title", timeout=10)
        self._call_function(gm_path, "StartGame")
        self.wait_for_state("Playing", timeout=10)

    def wait_for_state(self, target_state, timeout=10):
        """Poll get_state() until gameState matches target.

        Args:
            target_state: Target game state string (e.g., "Playing", "Title")
            timeout: Max seconds to wait

        Returns:
            The matching state dict

        Raises:
            PlayUnrealError: If timeout reached without matching state
        """
        start = time.time()
        while time.time() - start < timeout:
            state = self.get_state()
            current = state.get("gameState", "")
            # Handle both string and enum representations
            if isinstance(current, str) and target_state.lower() in current.lower():
                return state
            if isinstance(current, int):
                # EGameState enum values: Title=0, Spawning=1, Playing=2, etc.
                state_map = {0: "Title", 1: "Spawning", 2: "Playing",
                             3: "Paused", 4: "Dying", 5: "RoundComplete", 6: "GameOver"}
                if state_map.get(current, "").lower() == target_state.lower():
                    return state
            time.sleep(0.2)
        raise PlayUnrealError(
            f"Timed out waiting for state '{target_state}' after {timeout}s. "
            f"Last state: {state.get('gameState', 'unknown')}")

    def is_alive(self):
        """Check if the Remote Control API is responding.

        Returns:
            True if the API responds, False otherwise.
        """
        try:
            self._get("/remote/info")
            return True
        except ConnectionError:
            return False

    def diagnose(self):
        """Probe every aspect of the RC API connection and report findings.

        Returns a dict with detailed diagnostic information suitable for
        remote debugging.  Each section reports what was tested, what worked,
        and what failed.
        """
        report = {
            "connection": {},
            "routes": [],
            "gamemode_discovery": {},
            "frog_discovery": {},
            "get_game_state": {},
            "hop_test": {},
            "property_reads": {},
            "screenshot": {},
        }

        # 1. Connection check
        try:
            info = self._get("/remote/info")
            report["connection"] = {
                "status": "OK",
                "url": self.base_url,
                "response_keys": list(info.keys()) if isinstance(info, dict) else str(type(info)),
            }
            # Extract route list
            routes = info.get("Routes", info.get("routes", []))
            report["routes"] = [
                {"verb": r.get("Verb", r.get("verb", "?")),
                 "path": r.get("Path", r.get("path", "?"))}
                for r in (routes[:30] if isinstance(routes, list) else [])
            ]
        except RCConnectionError as e:
            report["connection"] = {"status": "FAILED", "error": str(e)}
            return report

        # 2. GameMode object path discovery — try every candidate
        gm_results = []
        found_gm = None
        for path in self._gm_candidates():
            try:
                result = self._describe_object(path)
                if result:
                    funcs = [f.get("Name", "?") for f in result.get("Functions", [])]
                    props = [p.get("Name", "?") for p in result.get("Properties", [])]
                    entry = {
                        "path": path,
                        "status": "FOUND",
                        "functions_count": len(funcs),
                        "properties_count": len(props),
                        "sample_functions": funcs[:10],
                        "has_GetGameStateJSON": "GetGameStateJSON" in funcs,
                        "has_StartGame": "StartGame" in funcs,
                        "has_ReturnToTitle": "ReturnToTitle" in funcs,
                        "has_HandleHopCompleted": "HandleHopCompleted" in funcs,
                    }
                    gm_results.append(entry)
                    if found_gm is None and "Default__" not in path:
                        found_gm = path
                    elif found_gm is None:
                        found_gm = path
                else:
                    gm_results.append({"path": path, "status": "NOT_FOUND (describe returned None)"})
            except CallError as e:
                gm_results.append({"path": path, "status": "ERROR", "error": str(e)})
            except RCConnectionError as e:
                gm_results.append({"path": path, "status": "CONN_ERROR", "error": str(e)})

        report["gamemode_discovery"] = {
            "candidates_tested": len(gm_results),
            "selected": found_gm,
            "results": gm_results,
        }

        # 3. Frog object path discovery
        frog_results = []
        found_frog = None
        for path in self._frog_candidates():
            try:
                result = self._describe_object(path)
                if result:
                    funcs = [f.get("Name", "?") for f in result.get("Functions", [])]
                    entry = {
                        "path": path,
                        "status": "FOUND",
                        "functions_count": len(funcs),
                        "has_RequestHop": "RequestHop" in funcs,
                        "has_GridToWorld": "GridToWorld" in funcs,
                    }
                    frog_results.append(entry)
                    if found_frog is None and "Default__" not in path:
                        found_frog = path
                    elif found_frog is None:
                        found_frog = path
                else:
                    frog_results.append({"path": path, "status": "NOT_FOUND"})
            except CallError as e:
                frog_results.append({"path": path, "status": "ERROR", "error": str(e)})
            except RCConnectionError as e:
                frog_results.append({"path": path, "status": "CONN_ERROR", "error": str(e)})

        report["frog_discovery"] = {
            "candidates_tested": len(frog_results),
            "selected": found_frog,
            "results": frog_results,
        }

        # 4. Test GetGameStateJSON
        if found_gm:
            try:
                result = self._call_function(found_gm, "GetGameStateJSON")
                ret_val = result.get("ReturnValue", "")
                if ret_val:
                    try:
                        parsed = json.loads(ret_val)
                        report["get_game_state"] = {
                            "status": "OK",
                            "raw_return": ret_val,
                            "parsed": parsed,
                            "has_expected_keys": all(
                                k in parsed for k in
                                ["score", "lives", "wave", "frogPos", "gameState"]
                            ),
                        }
                    except json.JSONDecodeError as e:
                        report["get_game_state"] = {
                            "status": "JSON_PARSE_ERROR",
                            "raw_return": ret_val,
                            "error": str(e),
                        }
                else:
                    report["get_game_state"] = {
                        "status": "EMPTY_RETURN",
                        "raw_result": result,
                    }
            except CallError as e:
                report["get_game_state"] = {"status": "CALL_FAILED", "error": str(e)}

        # 5. Test RequestHop parameter format (dry probe — check if function accepts params)
        if found_frog and "Default__" not in found_frog:
            try:
                # Send a zero-vector hop — should be rejected by game logic (no direction)
                # but the RC API call itself should succeed (200 OK)
                result = self._call_function(found_frog, "RequestHop", {
                    "Direction": {"X": 0.0, "Y": 0.0, "Z": 0.0}
                })
                report["hop_test"] = {
                    "status": "OK",
                    "note": "RequestHop accepted FVector parameter format",
                    "result": result,
                }
            except CallError as e:
                report["hop_test"] = {
                    "status": "CALL_FAILED",
                    "error": str(e),
                    "note": "FVector format {X,Y,Z} may be wrong. Try nested format.",
                }
        else:
            report["hop_test"] = {
                "status": "SKIPPED",
                "note": "No live FrogCharacter found (CDO only). Cannot test hop.",
            }

        # 6. Test property reads on live objects
        prop_tests = {}
        if found_gm and "Default__" not in found_gm:
            for prop in ["CurrentState", "CurrentWave", "RemainingTime", "HomeSlotsFilledCount"]:
                try:
                    val = self._read_property(found_gm, prop)
                    prop_tests[f"GM.{prop}"] = {"status": "OK", "value": val}
                except CallError as e:
                    prop_tests[f"GM.{prop}"] = {"status": "FAILED", "error": str(e)}
        if found_frog and "Default__" not in found_frog:
            for prop in ["GridPosition", "bIsHopping", "bIsDead", "HopDuration"]:
                try:
                    val = self._read_property(found_frog, prop)
                    prop_tests[f"Frog.{prop}"] = {"status": "OK", "value": val}
                except CallError as e:
                    prop_tests[f"Frog.{prop}"] = {"status": "FAILED", "error": str(e)}
        report["property_reads"] = prop_tests

        # 7. Screenshot test (just check if the call is accepted)
        report["screenshot"] = {"status": "SKIPPED", "note": "Screenshot test requires visual verification"}

        return report

    # -- Object path discovery -----------------------------------------------

    def _get_gm_path(self):
        """Get the object path of the live GameMode instance."""
        if self._gm_path:
            return self._gm_path
        self._gm_path = self._discover_gm_path()
        return self._gm_path

    def _get_frog_path(self):
        """Get the object path of the live FrogCharacter instance."""
        if self._frog_path:
            return self._frog_path
        self._frog_path = self._discover_frog_path()
        return self._frog_path

    @staticmethod
    def _gm_candidates():
        """Return all candidate object paths for the GameMode, ordered by likelihood."""
        candidates = []
        # In -game mode the GameMode is auto-spawned by the engine into the
        # persistent level.  The naming convention differs based on whether
        # the class is native C++ (_0 suffix) or Blueprint-derived (_C_0).
        # The AuthorityGameMode sub-object path is another common pattern.
        for map_name in [_DEFAULT_MAP, "FroggerMap", "TestMap", "DefaultMap"]:
            prefix = f"/Game/Maps/{map_name}.{map_name}:PersistentLevel"
            candidates.append(f"{prefix}.UnrealFrogGameMode_0")
            candidates.append(f"{prefix}.UnrealFrogGameMode_C_0")
            # Some UE versions use the AuthorityGameMode sub-object
            candidates.append(f"{prefix}.UnrealFrogGameMode_0.AuthorityGameMode")
        # CDO — always exists for describe/call but state reads return defaults
        candidates.append("/Script/UnrealFrog.Default__UnrealFrogGameMode")
        return candidates

    @staticmethod
    def _frog_candidates():
        """Return all candidate object paths for the FrogCharacter."""
        candidates = []
        for map_name in [_DEFAULT_MAP, "FroggerMap", "TestMap", "DefaultMap"]:
            prefix = f"/Game/Maps/{map_name}.{map_name}:PersistentLevel"
            candidates.append(f"{prefix}.FrogCharacter_0")
            candidates.append(f"{prefix}.FrogCharacter_C_0")
            # Default pawn spawned by GameMode may use a numbered suffix > 0
            candidates.append(f"{prefix}.FrogCharacter_1")
        # CDO
        candidates.append("/Script/UnrealFrog.Default__FrogCharacter")
        return candidates

    def _discover_gm_path(self):
        """Discover the GameMode object path by probing candidates."""
        for path in self._gm_candidates():
            try:
                result = self._describe_object(path)
                if result:
                    return path
            except (CallError, RCConnectionError):
                continue
        return "/Script/UnrealFrog.Default__UnrealFrogGameMode"

    def _discover_frog_path(self):
        """Discover the FrogCharacter object path by probing candidates."""
        for path in self._frog_candidates():
            try:
                result = self._describe_object(path)
                if result:
                    return path
            except (CallError, RCConnectionError):
                continue
        return "/Script/UnrealFrog.Default__FrogCharacter"

    def _verify_live_path(self, path):
        """Check if a path points to a live instance (not CDO).

        Returns True if the path responds to describe and is not a CDO path.
        """
        if "Default__" in path:
            return False
        try:
            result = self._describe_object(path)
            return result is not None
        except (CallError, RCConnectionError):
            return False

    # -- Low-level RC API calls ----------------------------------------------

    def _call_function(self, object_path, function_name, parameters=None):
        """Call a UFUNCTION via Remote Control API.

        Args:
            object_path: UE object path
            function_name: Name of the BlueprintCallable function
            parameters: Dict of parameters (optional)

        Returns:
            Response body as dict
        """
        body = {
            "ObjectPath": object_path,
            "FunctionName": function_name,
        }
        if parameters:
            body["Parameters"] = parameters

        return self._put("/remote/object/call", body)

    def _read_property(self, object_path, property_name):
        """Read a UPROPERTY value via Remote Control API.

        Args:
            object_path: UE object path
            property_name: Name of the property

        Returns:
            The property value (parsed from JSON)
        """
        body = {
            "ObjectPath": object_path,
            "PropertyName": property_name,
        }
        result = self._put("/remote/object/property", body)
        # RC API returns {"PropertyName": value} for property reads
        return result.get(property_name, result)

    def _describe_object(self, object_path):
        """Describe an object (list its properties and functions).

        Args:
            object_path: UE object path

        Returns:
            Description dict or None if object not found
        """
        body = {"ObjectPath": object_path}
        try:
            return self._put("/remote/object/describe", body)
        except CallError:
            return None

    # -- HTTP transport ------------------------------------------------------

    def _get(self, endpoint):
        """Send a GET request to the RC API."""
        url = f"{self.base_url}{endpoint}"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"Cannot reach Remote Control API at {self.base_url}. "
                f"Is the editor running with -RCWebControlEnable? Error: {e}"
            )
        except json.JSONDecodeError:
            return {}

    def _put(self, endpoint, body):
        """Send a PUT request with JSON body to the RC API."""
        url = f"{self.base_url}{endpoint}"
        data = json.dumps(body).encode("utf-8")
        try:
            req = urllib.request.Request(
                url,
                data=data,
                method="PUT",
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_body = resp.read().decode("utf-8")
                if resp_body:
                    return json.loads(resp_body)
                return {}
        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8")
            except Exception:
                pass
            raise CallError(
                f"RC API call failed: {e.code} {e.reason} "
                f"on {endpoint}. Body: {error_body}"
            )
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"Cannot reach Remote Control API at {self.base_url}. "
                f"Is the editor running with -RCWebControlEnable? Error: {e}"
            )
        except json.JSONDecodeError:
            return {}


# -- CLI entrypoint for quick testing ----------------------------------------

if __name__ == "__main__":
    import sys

    pu = PlayUnreal()
    if not pu.is_alive():
        print("ERROR: Remote Control API is not responding on localhost:30010")
        print("       Launch the editor with: run-playunreal.sh")
        sys.exit(1)

    print("Remote Control API is alive.")

    # Quick path discovery
    gm = pu._get_gm_path()
    frog = pu._get_frog_path()
    print(f"GameMode path: {gm}")
    print(f"  (live instance: {'Default__' not in gm})")
    print(f"Frog path: {frog}")
    print(f"  (live instance: {'Default__' not in frog})")
    print()

    try:
        state = pu.get_state()
        print(f"Game state: {json.dumps(state, indent=2)}")
    except PlayUnrealError as e:
        print(f"Could not get state: {e}")
