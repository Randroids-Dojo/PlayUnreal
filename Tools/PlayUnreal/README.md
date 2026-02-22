# PlayUnreal — Programmatic Game Testing for UnrealFrog

PlayUnreal enables agents and humans to launch games, send inputs, read game state, take screenshots, and record video—all via Python. It connects to running games through UE5's Remote Control API over HTTP.

## Key Components

**Core Purpose**: "This is the single most important QA tool in the project. Unit tests verify code structure; PlayUnreal verifies what the player actually sees and experiences."

The architecture consists of:
- `run-playunreal.sh`: Shell launcher managing editor lifecycle
- `client.py`: Python client library with zero pip dependencies
- `verify_visuals.py`: Visual smoke test for checking game appearance
- `diagnose.py`: Deep diagnostic probing of RC API connections
- `qa_checklist.py`: Sprint sign-off verification gate
- `acceptance_test.py`: Full gameplay testing across road and river

## Primary API Methods

**Connection**: `PlayUnreal()` connects to localhost:30010 with 5-second timeout

**Game Control**:
- `hop(direction)` sends directional commands
- `reset_game()` returns to title and starts new game
- `get_state()` returns dictionary with score, lives, position, gameState

**Evidence Capture**:
- `screenshot(path)` captures PNG (0.5s first call, 0.1s cached)
- `record_video(path)` captures 3-second `.mov` file

**Diagnostics**: `diagnose()` probes every aspect of the RC API connection: routes, object paths, function calls, property reads.

**Navigation**:
- `navigate(target_col)` autonomous pathfinding to home slot
- `get_hazards()` retrieves obstacle data for path planning
- `get_config()` fetches game constants for prediction accuracy

## Quick Start

```bash
# Launch editor + run diagnostics
./Tools/PlayUnreal/run-playunreal.sh diagnose.py

# With game already running
python3 Tools/PlayUnreal/diagnose.py

# Run visual verification
./Tools/PlayUnreal/run-playunreal.sh verify_visuals.py

# Run acceptance test
./Tools/PlayUnreal/run-playunreal.sh acceptance_test.py

# QA sign-off checklist
python3 Tools/PlayUnreal/qa_checklist.py

# Full build + test + screenshot pipeline
./Tools/PlayUnreal/build-and-verify.sh
```

## Test Script Pattern

New scripts follow a standard template: import client library, check game alive status, reset to known state, execute test logic, capture evidence via screenshots or video.

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from client import PlayUnreal

pu = PlayUnreal()
if not pu.is_alive():
    print("Game not running!")
    sys.exit(2)

pu.reset_game()
state = pu.get_state()
# ... test logic ...
pu.screenshot("evidence.png")
```

## File Reference

| File | Purpose |
|------|---------|
| `client.py` | Python client library (zero pip deps, stdlib only) |
| `path_planner.py` | Predictive safe-path navigation for Frogger gameplay |
| `diagnose.py` | RC API diagnostic report (7 phases, structured output) |
| `acceptance_test.py` | Full road + river + home slot acceptance test |
| `verify_visuals.py` | VFX/HUD smoke test (11 steps, burst screenshots) |
| `qa_checklist.py` | Sprint sign-off gate (6 checks, pass/fail) |
| `debug_navigation.py` | Per-hop timing diagnostics for navigation tuning |
| `test_crossing.py` | Logged one-hop-at-a-time navigation test |
| `run-playunreal.sh` | Launch editor + RC API + run Python test script |
| `run-tests.sh` | Headless UE automation test runner with categories |
| `build-and-verify.sh` | Full build → test → screenshot pipeline |
| `play-game.sh` | Quick PIE mode launcher for manual play |
| `rc_api_spike.sh` | RC API connectivity spike test (curl-based) |

## Common Issues

- **Black screenshots**: Game window is minimized or missing screen recording permissions.
- **"Default__" in object paths**: Actors weren't spawned after map loading.
- **Editor crashes on macOS**: Use `-windowed` flag and kill stale processes first.
- **RC API not responding**: Ensure `-RCWebControlEnable` flag is set on launch.
