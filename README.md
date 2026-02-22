# PlayUnreal

PlayUnreal is a Playwright-style automation framework for Unreal Engine. External
scripts drive a running editor or packaged game via Automation Driver and the
Remote Control API.

## Goals

- External control (Python/TS) with locators, auto-waits, and artifacts.
- Transport-agnostic protocol (Remote Control first, custom WS later).
- CI-friendly, process-isolated automation.

## Repo Layout

- `Tools/PlayUnreal/`: **Primary tooling** — Python client, test scripts, shell launchers.
  - `client.py`: Zero-dependency Python client for RC API (hop, screenshot, state, diagnose).
  - `path_planner.py`: Predictive navigation for Frogger-style gameplay.
  - `diagnose.py`: 7-phase RC API diagnostic report.
  - `acceptance_test.py`: Full road + river + home slot acceptance test.
  - `verify_visuals.py`: VFX/HUD visual smoke test (11 steps).
  - `qa_checklist.py`: Sprint sign-off verification gate.
  - `debug_navigation.py`: Per-hop timing diagnostics.
  - `test_crossing.py`: Logged navigation test.
  - `run-playunreal.sh`: Editor lifecycle + test runner.
  - `run-tests.sh`: Headless UE automation test runner.
  - `build-and-verify.sh`: Full build + test + screenshot pipeline.
  - `play-game.sh`: Quick PIE mode launcher.
  - `rc_api_spike.sh`: RC API connectivity spike test.
- `unreal-plugin/PlayUnrealAutomation`: Unreal Engine plugin (runtime + editor).
- `python/playunreal`: Python client library (planned Playwright-style wrapper).
- `protocol/playunreal-api.md`: JSON-RPC-like API spec.
- `scripts/`: Launch + wait + run helpers (legacy).
- `examples/sample_project`: Minimal UE project (planned).
- `examples/tests_e2e`: Pytest examples (planned).

## Quick Start

```bash
# Launch editor with Remote Control API + run diagnostics
./Tools/PlayUnreal/run-playunreal.sh diagnose.py

# Run visual verification (VFX, HUD, gameplay)
./Tools/PlayUnreal/run-playunreal.sh verify_visuals.py

# Run acceptance test (hop across road + river)
./Tools/PlayUnreal/run-playunreal.sh acceptance_test.py

# QA sign-off (with game already running)
python3 Tools/PlayUnreal/qa_checklist.py

# Full pipeline: build, test, screenshot
./Tools/PlayUnreal/build-and-verify.sh

# Run headless UE automation tests
./Tools/PlayUnreal/run-tests.sh --all
```

## Python Client API

```python
from client import PlayUnreal

pu = PlayUnreal()           # Connect to localhost:30010
pu.reset_game()             # Reset to title, start new game
pu.hop("up")                # Send directional command
state = pu.get_state()      # {score, lives, wave, frogPos, gameState, ...}
pu.screenshot("shot.png")   # Capture game window
pu.record_video("clip.mov") # Record 3-second video
pu.navigate(target_col=6)   # Autonomous pathfinding to home slot
report = pu.diagnose()      # Full RC API diagnostic report
```

## MVP Transport

- Remote Control HTTP on port 30010.
- Start server with `WebControl.StartServer` or `-ExecCmds="WebControl.EnableServerOnStartup 1"`.
- Game mode requires `-RCWebControlEnable` flag.
- Key endpoints:
  - `GET /remote/info` — List routes
  - `PUT /remote/object/call` — Call UFUNCTION
  - `PUT /remote/object/property` — Read/write UPROPERTY
  - `PUT /remote/object/describe` — Describe object
