"""PlayUnreal diagnostic — Thorough probe of the Remote Control API connection.

Designed to be run by the stakeholder after launching the game via
run-playunreal.sh. Outputs a structured report that can be sent back to
agents for remote debugging.

Usage:
    ./Tools/PlayUnreal/run-playunreal.sh diagnose.py

Or with the game already running:
    python3 Tools/PlayUnreal/diagnose.py

Exit codes:
    0 = all critical checks passed
    1 = one or more critical checks failed
    2 = cannot connect to Remote Control API
"""

import json
import os
import sys
import time

# Add script directory to path so we can import client
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from client import PlayUnreal, PlayUnrealError, RCConnectionError, CallError


def log(msg):
    print(f"[Diagnose] {msg}")


def section(title):
    print()
    print(f"{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def check(desc, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {desc}")
    if detail:
        for line in str(detail).split("\n"):
            print(f"         {line}")
    return passed


def main():
    section("PlayUnreal Diagnostic Report")
    log(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"Target: http://localhost:30010")
    print()

    pu = PlayUnreal()
    critical_failures = 0
    warnings = 0

    # =========================================================================
    # PHASE 1: Connection
    # =========================================================================
    section("Phase 1: Connection to Remote Control API")

    if not pu.is_alive():
        check("RC API responding on localhost:30010", False,
              "The editor is not running, or the RemoteControl plugin is not loaded.\n"
              "Launch with: ./Tools/PlayUnreal/run-playunreal.sh diagnose.py\n"
              "Required flags: -RCWebControlEnable -ExecCmds=\"WebControl.EnableServerOnStartup 1\"")
        print()
        log("DIAGNOSTIC ABORTED: Cannot connect to Remote Control API.")
        return 2

    check("RC API responding on localhost:30010", True)

    # Get route list
    try:
        info = pu._get("/remote/info")
        routes = info.get("Routes", info.get("routes", []))
        route_paths = [r.get("Path", r.get("path", "?")) for r in routes]
        check("GET /remote/info returns route list", True,
              f"{len(routes)} routes available")

        # Check for critical routes (warning only — UE 5.7 /remote/info
        # may return 0 routes even when endpoints work fine)
        critical_routes = [
            "/remote/object/call",
            "/remote/object/property",
            "/remote/object/describe",
        ]
        for route in critical_routes:
            found = any(route in rp for rp in route_paths)
            if not found:
                print(f"  [WARN] Route not listed: {route} (may still work)")
                warnings += 1

    except Exception as e:
        check("GET /remote/info", False, str(e))
        critical_failures += 1

    # =========================================================================
    # PHASE 2: Object path discovery
    # =========================================================================
    section("Phase 2: Object Path Discovery (GameMode)")

    gm_candidates = PlayUnreal._gm_candidates()
    log(f"Testing {len(gm_candidates)} candidate paths...")
    print()

    found_gm_live = None
    found_gm_cdo = None

    for path in gm_candidates:
        is_cdo = "Default__" in path
        label = "(CDO)" if is_cdo else "(LIVE)"
        try:
            result = pu._describe_object(path)
            if result:
                funcs = [f.get("Name", "?") for f in result.get("Functions", [])]
                props = [p.get("Name", "?") for p in result.get("Properties", [])]
                check(f"{label} {path}", True,
                      f"{len(funcs)} functions, {len(props)} properties")
                if not is_cdo and found_gm_live is None:
                    found_gm_live = path
                elif is_cdo and found_gm_cdo is None:
                    found_gm_cdo = path
            else:
                print(f"  [ -- ] {label} {path} -> not found")
        except CallError as e:
            err_short = str(e)[:100]
            print(f"  [ -- ] {label} {path} -> {err_short}")
        except RCConnectionError:
            print(f"  [ -- ] {label} {path} -> connection error")

    gm_path = found_gm_live or found_gm_cdo
    print()
    if found_gm_live:
        check("Live GameMode instance found", True, found_gm_live)
    else:
        if not check("Live GameMode instance found", False,
                      "Only CDO found. State reads will return defaults, not live game state.\n"
                      "This means the game may not have loaded a map, or the actor naming\n"
                      "convention differs from what we expected.\n"
                      f"CDO path: {found_gm_cdo}"):
            critical_failures += 1
            warnings += 1

    # =========================================================================
    # PHASE 3: FrogCharacter discovery
    # =========================================================================
    section("Phase 3: Object Path Discovery (FrogCharacter)")

    frog_candidates = PlayUnreal._frog_candidates()
    log(f"Testing {len(frog_candidates)} candidate paths...")
    print()

    found_frog_live = None
    found_frog_cdo = None

    for path in frog_candidates:
        is_cdo = "Default__" in path
        label = "(CDO)" if is_cdo else "(LIVE)"
        try:
            result = pu._describe_object(path)
            if result:
                funcs = [f.get("Name", "?") for f in result.get("Functions", [])]
                check(f"{label} {path}", True, f"{len(funcs)} functions")
                if not is_cdo and found_frog_live is None:
                    found_frog_live = path
                elif is_cdo and found_frog_cdo is None:
                    found_frog_cdo = path
            else:
                print(f"  [ -- ] {label} {path} -> not found")
        except CallError as e:
            err_short = str(e)[:100]
            print(f"  [ -- ] {label} {path} -> {err_short}")
        except RCConnectionError:
            print(f"  [ -- ] {label} {path} -> connection error")

    frog_path = found_frog_live or found_frog_cdo
    print()
    if found_frog_live:
        check("Live FrogCharacter instance found", True, found_frog_live)
    else:
        if not check("Live FrogCharacter instance found", False,
                      "Only CDO found. Hop commands won't affect the live game.\n"
                      f"CDO path: {found_frog_cdo}"):
            critical_failures += 1

    # =========================================================================
    # PHASE 4: GetGameStateJSON
    # =========================================================================
    section("Phase 4: GetGameStateJSON()")

    if gm_path:
        try:
            result = pu._call_function(gm_path, "GetGameStateJSON")
            check("GetGameStateJSON callable", True)

            ret_val = result.get("ReturnValue", "")
            if ret_val:
                check("Return value is non-empty", True, f"Raw: {ret_val[:200]}")
                try:
                    parsed = json.loads(ret_val)
                    check("Return value is valid JSON", True)

                    expected_keys = ["score", "lives", "wave", "frogPos", "gameState",
                                     "timeRemaining", "homeSlotsFilledCount"]
                    for key in expected_keys:
                        if key in parsed:
                            check(f"  Key '{key}' present", True, f"value={parsed[key]}")
                        else:
                            check(f"  Key '{key}' present", False)
                            warnings += 1

                except json.JSONDecodeError as e:
                    check("Return value is valid JSON", False, str(e))
                    critical_failures += 1
            else:
                check("Return value is non-empty", False,
                      f"Full result: {json.dumps(result)}\n"
                      "GetGameStateJSON may return empty on CDO (no live state).")
                if "Default__" in gm_path:
                    log("NOTE: Using CDO path — function runs but has no world context.")
                    log("      This is expected if no live instance was found.")
                else:
                    critical_failures += 1

        except CallError as e:
            check("GetGameStateJSON callable", False, str(e))
            critical_failures += 1
    else:
        check("GetGameStateJSON", False, "No GameMode path available")
        critical_failures += 1

    # =========================================================================
    # PHASE 5: Property reads
    # =========================================================================
    section("Phase 5: UPROPERTY Reads")

    if gm_path:
        log(f"Reading properties from GameMode ({gm_path[:60]}...)")
        for prop in ["CurrentState", "CurrentWave", "RemainingTime",
                      "HomeSlotsFilledCount", "TimePerLevel", "HopDuration"]:
            # Note: HopDuration is on FrogCharacter, not GameMode — include
            # as a negative test to verify error handling
            try:
                val = pu._read_property(gm_path, prop)
                check(f"GM.{prop}", True, f"value={val}")
            except CallError as e:
                err_short = str(e)[:80]
                if prop == "HopDuration":
                    print(f"  [SKIP] GM.{prop} -> expected fail (property is on FrogCharacter)")
                else:
                    check(f"GM.{prop}", False, err_short)
                    warnings += 1

    if frog_path:
        log(f"Reading properties from FrogCharacter ({frog_path[:60]}...)")
        for prop in ["GridPosition", "bIsHopping", "bIsDead", "HopDuration",
                      "GridCellSize", "GridColumns", "GridRows"]:
            try:
                val = pu._read_property(frog_path, prop)
                check(f"Frog.{prop}", True, f"value={val}")
            except CallError as e:
                err_short = str(e)[:80]
                check(f"Frog.{prop}", False, err_short)
                warnings += 1

    # =========================================================================
    # PHASE 6: RequestHop parameter format
    # =========================================================================
    section("Phase 6: RequestHop Parameter Format")

    if found_frog_live:
        log("Testing FVector serialization format for RequestHop...")
        # Try sending a zero-direction hop (game logic rejects it, but RC API
        # should accept the parameter format)
        formats_to_try = [
            ("Object format {X,Y,Z}", {"Direction": {"X": 0.0, "Y": 0.0, "Z": 0.0}}),
            ("String format", {"Direction": "(X=0.0,Y=0.0,Z=0.0)"}),
        ]
        for desc, params in formats_to_try:
            try:
                result = pu._call_function(found_frog_live, "RequestHop", params)
                check(f"RequestHop with {desc}", True, f"result={result}")
            except CallError as e:
                err_short = str(e)[:120]
                check(f"RequestHop with {desc}", False, err_short)

        # Now try an actual hop direction
        log("Testing actual hop (up)...")
        try:
            result = pu._call_function(found_frog_live, "RequestHop", {
                "Direction": {"X": 0.0, "Y": 1.0, "Z": 0.0}
            })
            check("RequestHop(Direction={Y:1})", True, f"result={result}")
            time.sleep(0.3)
            # Read position after hop
            try:
                pos = pu._read_property(found_frog_live, "GridPosition")
                check("Frog position after hop", True, f"GridPosition={pos}")
            except CallError:
                log("  (could not read position after hop)")
        except CallError as e:
            check("RequestHop(Direction={Y:1})", False, str(e)[:120])
            critical_failures += 1
    else:
        log("SKIPPED: No live FrogCharacter instance to test hop on.")
        if found_frog_cdo:
            log(f"  CDO path: {found_frog_cdo}")
            log("  CDO can describe the function but cannot execute gameplay logic.")
        warnings += 1

    # =========================================================================
    # PHASE 7: Full diagnose() via client
    # =========================================================================
    section("Phase 7: Full Client Diagnostic")
    log("Running client.diagnose() method...")

    report = pu.diagnose()

    # Just summarize key findings — full report is too verbose for stdout
    conn = report.get("connection", {})
    check("Client diagnose() connection", conn.get("status") == "OK",
          conn.get("status", "UNKNOWN"))

    gm_disc = report.get("gamemode_discovery", {})
    check("Client diagnose() GM discovery", gm_disc.get("selected") is not None,
          f"selected: {gm_disc.get('selected', 'None')}")

    frog_disc = report.get("frog_discovery", {})
    check("Client diagnose() Frog discovery", frog_disc.get("selected") is not None,
          f"selected: {frog_disc.get('selected', 'None')}")

    gs = report.get("get_game_state", {})
    check("Client diagnose() GetGameStateJSON", gs.get("status") == "OK",
          gs.get("status", "UNKNOWN"))

    # =========================================================================
    # Summary
    # =========================================================================
    section("DIAGNOSTIC SUMMARY")

    print(f"  Critical failures: {critical_failures}")
    print(f"  Warnings:          {warnings}")
    print()

    if gm_path:
        print(f"  GameMode path:     {gm_path}")
        print(f"  (live instance:    {'Default__' not in gm_path})")
    if frog_path:
        print(f"  Frog path:         {frog_path}")
        print(f"  (live instance:    {'Default__' not in frog_path})")

    print()

    # Save full report to file for agent consumption
    report_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "..", "Saved", "PlayUnreal", "diagnostic_report.json"
    )
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    log(f"Full diagnostic report saved to: {report_path}")

    if critical_failures == 0:
        print()
        print("  RESULT: PASS (all critical checks passed)")
        print()
        if warnings > 0:
            print(f"  {warnings} warning(s) — review output above for details.")
        return 0
    else:
        print()
        print(f"  RESULT: FAIL ({critical_failures} critical failure(s))")
        print()
        print("  NEXT STEPS:")
        if not found_gm_live:
            print("  - GameMode live path not found. The actor naming convention")
            print("    may differ from expected. Check UE output log for the actual")
            print("    actor names spawned in the level. Search for 'SpawnActor' or")
            print("    'GameMode' in the log at:")
            print("    ~/Library/Logs/Unreal Engine/UnrealFrogEditor/UnrealFrog.log")
        if not found_frog_live:
            print("  - FrogCharacter live path not found. The default pawn may have")
            print("    a different name. Check the log for 'DefaultPawnClass' or")
            print("    'SpawnDefaultPawnFor'.")
        print()
        print("  Share the diagnostic_report.json file with the DevOps agent for")
        print("  remote debugging.")
        return 1


if __name__ == "__main__":
    try:
        code = main()
        sys.exit(code)
    except RCConnectionError as e:
        log(f"CONNECTION ERROR: {e}")
        sys.exit(2)
    except PlayUnrealError as e:
        log(f"ERROR: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        log("Interrupted.")
        sys.exit(130)
