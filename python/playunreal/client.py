"""PlayUnreal client — Python interface to Unreal Engine via Remote Control API.

Uses only urllib.request (no pip dependencies). Requires the editor running
with RemoteControl plugin enabled on localhost:30010.

Usage::

    from playunreal import PlayUnreal

    pu = PlayUnreal()
    pu.reset_game()
    pu.hop("up")
    state = pu.get_state()
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


class PlayUnreal:
    """Client for controlling Unreal Engine games via Remote Control API.

    Connects to a running Unreal Editor or packaged game that has the
    RemoteControl plugin enabled. Provides methods for game control,
    state queries, evidence capture, and diagnostics.

    Args:
        host: RC API host (default localhost)
        port: RC API port (default 30010)
        timeout: HTTP request timeout in seconds (default 5)
        map_name: Default map name for object path discovery (default "FroggerMain")
    """

    def __init__(self, host="localhost", port=30010, timeout=5, map_name="FroggerMain"):
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout
        self._map_name = map_name
        self._gm_path = None
        self._frog_path = None
        self._prev_state = None
        self._gm_class = "UnrealFrogGameMode"
        self._frog_class = "FrogCharacter"
        self._module_name = "UnrealFrog"

    # -- Configuration -------------------------------------------------------

    def configure(self, *, gm_class=None, frog_class=None, module_name=None,
                  map_name=None):
        """Override default class/module names for object path discovery.

        Call this before any API calls if your project uses different naming.

        Args:
            gm_class: GameMode class name (e.g., "MyGameMode")
            frog_class: Player character class name (e.g., "MyCharacter")
            module_name: UE module name (e.g., "MyGame")
            map_name: Map name for object path resolution
        """
        if gm_class:
            self._gm_class = gm_class
        if frog_class:
            self._frog_class = frog_class
        if module_name:
            self._module_name = module_name
        if map_name:
            self._map_name = map_name
        # Clear cached paths so they'll be re-discovered
        self._gm_path = None
        self._frog_path = None

    # -- Public API ----------------------------------------------------------

    def is_alive(self):
        """Check if the Remote Control API is responding.

        Returns:
            True if the API responds, False otherwise.
        """
        try:
            self._get("/remote/info")
            return True
        except RCConnectionError:
            return False

    def hop(self, direction):
        """Send a hop command to the frog.

        Args:
            direction: "up", "down", "left", or "right"
        """
        if direction not in _DIRECTIONS:
            raise ValueError(
                f"Invalid direction '{direction}'. Use: up, down, left, right")
        frog_path = self._get_frog_path()
        self._call_function(frog_path, "RequestHop", {
            "Direction": _DIRECTIONS[direction]
        })

    def set_invincible(self, enabled):
        """Enable or disable frog invincibility.

        Args:
            enabled: True to enable invincibility, False to disable.
        """
        frog_path = self._get_frog_path()
        self._call_function(frog_path, "SetInvincible", {
            "bEnable": bool(enabled)
        })

    def get_state(self):
        """Get current game state as a dict.

        Returns:
            dict with keys: score, lives, wave, frogPos, gameState,
            timeRemaining, homeSlotsFilledCount

        If GetGameStateJSON() exists on the GameMode, uses that (single call).
        Otherwise falls back to reading individual properties.
        """
        gm_path = self._get_gm_path()

        # Try GetGameStateJSON first
        try:
            result = self._call_function(gm_path, "GetGameStateJSON")
            ret_val = result.get("ReturnValue", "")
            if ret_val:
                return json.loads(ret_val)
        except (CallError, json.JSONDecodeError):
            pass

        # Fallback: read individual properties
        state = {}
        try:
            state["gameState"] = self._read_property(gm_path, "CurrentState")
            state["wave"] = self._read_property(gm_path, "CurrentWave")
            state["homeSlotsFilledCount"] = self._read_property(
                gm_path, "HomeSlotsFilledCount")
            state["timeRemaining"] = self._read_property(
                gm_path, "RemainingTime")
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

        Returns:
            dict with keys like cellSize, capsuleRadius, gridCols, etc.
            Empty dict on failure.
        """
        if PlayUnreal._cached_config is not None:
            return PlayUnreal._cached_config

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

        return {}

    def reset_game(self):
        """Reset the game to title screen and start a new game.

        ReturnToTitle starts a transition (fade/level reset) but gameState
        stays in its previous value throughout — Title is not a stable
        observable state. Sleep gives the transition time to clear score
        and state, then wait_for_state("Playing") confirms the game is
        truly ready before returning.
        """
        gm_path = self._get_gm_path()
        # Retry ReturnToTitle until Title is confirmed. From GameOver the
        # command is ignored until the GameOver screen auto-dismisses, which
        # can take several seconds. From Playing it resolves in < 0.5s.
        for _ in range(10):
            self._call_function(gm_path, "ReturnToTitle")
            try:
                self.wait_for_state("Title", timeout=4)
                break
            except PlayUnrealError:
                time.sleep(1.0)
        self._call_function(gm_path, "StartGame")
        self.wait_for_state("Playing", timeout=15)

    def wait_for_state(self, target_state, timeout=10):
        """Poll get_state() until gameState matches target.

        Args:
            target_state: Target game state string (e.g., "Playing")
            timeout: Max seconds to wait

        Returns:
            The matching state dict

        Raises:
            PlayUnrealError: If timeout reached
        """
        start = time.time()
        state = {}
        while time.time() - start < timeout:
            state = self.get_state()
            current = state.get("gameState", "")
            if isinstance(current, str) and target_state.lower() in current.lower():
                return state
            if isinstance(current, int):
                state_map = {0: "Title", 1: "Spawning", 2: "Playing",
                             3: "Paused", 4: "Dying", 5: "RoundComplete",
                             6: "GameOver"}
                if state_map.get(current, "").lower() == target_state.lower():
                    return state
            time.sleep(0.2)
        raise PlayUnrealError(
            f"Timed out waiting for state '{target_state}' after {timeout}s. "
            f"Last state: {state.get('gameState', 'unknown')}")

    def screenshot(self, path=None):
        """Take a screenshot of the game window.

        Uses macOS screencapture. Caches window ID after first lookup
        so subsequent calls are fast.

        Args:
            path: File path for the screenshot. Defaults to Saved/Screenshots/.

        Returns:
            True if the screenshot was saved successfully.
        """
        import subprocess

        if path is None:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "Saved", "Screenshots",
                                "screenshot.png")

        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

        try:
            subprocess.run(["screencapture", "-x", path], timeout=5)
            return os.path.exists(path)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def navigate(self, target_col=6, max_deaths=8):
        """Navigate frog to a home slot using predictive path planning.

        Uses one-hop-at-a-time strategy with fresh hazard data per hop.

        Args:
            target_col: home slot column (1, 4, 6, 8, 11)
            max_deaths: give up after this many deaths

        Returns:
            dict with success, total_hops, deaths, elapsed, state
        """
        try:
            from path_planner import navigate_to_home_slot
        except ImportError:
            raise PlayUnrealError(
                "path_planner module not found. Navigation requires "
                "Tools/PlayUnreal/path_planner.py on sys.path.")
        return navigate_to_home_slot(self, target_col=target_col,
                                     max_deaths=max_deaths)

    def call_function(self, object_path, function_name, parameters=None):
        """Call a UFUNCTION via Remote Control API.

        This is the public API for calling arbitrary functions on UE objects.

        Args:
            object_path: UE object path
            function_name: Name of the BlueprintCallable function
            parameters: Dict of parameters (optional)

        Returns:
            Response body as dict
        """
        return self._call_function(object_path, function_name, parameters)

    def read_property(self, object_path, property_name):
        """Read a UPROPERTY value via Remote Control API.

        This is the public API for reading arbitrary properties from UE objects.

        Args:
            object_path: UE object path
            property_name: Name of the property

        Returns:
            The property value
        """
        return self._read_property(object_path, property_name)

    def describe_object(self, object_path):
        """Describe an object (list its properties and functions).

        Args:
            object_path: UE object path

        Returns:
            Description dict or None if object not found
        """
        return self._describe_object(object_path)

    def diagnose(self):
        """Run a diagnostic probe of the RC API connection.

        Returns a dict with detailed diagnostic information.
        """
        report = {
            "connection": {},
            "gamemode": {},
            "character": {},
            "state": {},
        }

        try:
            info = self._get("/remote/info")
            report["connection"] = {"status": "OK", "url": self.base_url}
        except RCConnectionError as e:
            report["connection"] = {"status": "FAILED", "error": str(e)}
            return report

        gm_path = self._get_gm_path()
        report["gamemode"] = {
            "path": gm_path,
            "is_live": "Default__" not in gm_path,
        }

        frog_path = self._get_frog_path()
        report["character"] = {
            "path": frog_path,
            "is_live": "Default__" not in frog_path,
        }

        try:
            state = self.get_state()
            report["state"] = {"status": "OK", "data": state}
        except PlayUnrealError as e:
            report["state"] = {"status": "FAILED", "error": str(e)}

        return report

    # -- Object path discovery -----------------------------------------------

    def _get_gm_path(self):
        if self._gm_path:
            return self._gm_path
        self._gm_path = self._discover_path(self._gm_class)
        return self._gm_path

    def _get_frog_path(self):
        if self._frog_path:
            return self._frog_path
        self._frog_path = self._discover_path(self._frog_class)
        return self._frog_path

    def _discover_path(self, class_name):
        """Discover a live object path by probing candidates."""
        candidates = self._build_candidates(class_name)
        for path in candidates:
            try:
                result = self._describe_object(path)
                if result:
                    return path
            except (CallError, RCConnectionError):
                continue
        return f"/Script/{self._module_name}.Default__{class_name}"

    def _build_candidates(self, class_name):
        """Build candidate object paths for a given class."""
        candidates = []
        for map_name in [self._map_name, "FroggerMap", "TestMap", "DefaultMap"]:
            prefix = f"/Game/Maps/{map_name}.{map_name}:PersistentLevel"
            candidates.append(f"{prefix}.{class_name}_0")
            candidates.append(f"{prefix}.{class_name}_C_0")
            candidates.append(f"{prefix}.{class_name}_1")
        candidates.append(
            f"/Script/{self._module_name}.Default__{class_name}")
        return candidates

    # -- Low-level RC API calls ----------------------------------------------

    def _call_function(self, object_path, function_name, parameters=None):
        body = {
            "ObjectPath": object_path,
            "FunctionName": function_name,
        }
        if parameters:
            body["Parameters"] = parameters
        return self._put("/remote/object/call", body)

    def _read_property(self, object_path, property_name):
        body = {
            "ObjectPath": object_path,
            "PropertyName": property_name,
        }
        result = self._put("/remote/object/property", body)
        return result.get(property_name, result)

    def _describe_object(self, object_path):
        body = {"ObjectPath": object_path}
        try:
            return self._put("/remote/object/describe", body)
        except CallError:
            return None

    # -- HTTP transport ------------------------------------------------------

    def _get(self, endpoint):
        url = f"{self.base_url}{endpoint}"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise RCConnectionError(
                f"Cannot reach Remote Control API at {self.base_url}. "
                f"Is the editor running with -RCWebControlEnable? Error: {e}")
        except json.JSONDecodeError:
            return {}

    def _put(self, endpoint, body):
        url = f"{self.base_url}{endpoint}"
        data = json.dumps(body).encode("utf-8")
        try:
            req = urllib.request.Request(
                url, data=data, method="PUT",
                headers={"Content-Type": "application/json"})
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
                f"on {endpoint}. Body: {error_body}")
        except urllib.error.URLError as e:
            raise RCConnectionError(
                f"Cannot reach Remote Control API at {self.base_url}. "
                f"Is the editor running with -RCWebControlEnable? Error: {e}")
        except json.JSONDecodeError:
            return {}
