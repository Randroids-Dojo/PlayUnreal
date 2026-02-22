# playunreal

Zero-dependency Python client for driving Unreal Engine games via the Remote Control API.

## Install

```bash
pip install -e python/
```

## Quick Start

```python
from playunreal import PlayUnreal

pu = PlayUnreal()                  # Connect to localhost:30010
pu.reset_game()                    # Reset to title, start new game
pu.hop("up")                       # Send directional command
state = pu.get_state()             # {score, lives, wave, frogPos, gameState}
print(state)
```

## API

### Connection

```python
pu = PlayUnreal(host="localhost", port=30010, timeout=5)
pu.is_alive()                      # True if RC API responds
```

### Game Control

```python
pu.hop("up" | "down" | "left" | "right")
pu.reset_game()                    # ReturnToTitle + StartGame
pu.set_invincible(True)            # Disable death for testing
pu.wait_for_state("Playing", timeout=10)
```

### State Queries

```python
state = pu.get_state()             # Full state dict
diff = pu.get_state_diff()         # State + changes from previous call
hazards = pu.get_hazards()         # Lane hazard positions
config = pu.get_config()           # Game constants (cell size, etc.)
```

### Evidence Capture

```python
pu.screenshot("evidence.png")      # Capture game window (macOS)
```

### Diagnostics

```python
report = pu.diagnose()             # Probe RC API connection
```

### Low-Level API

```python
pu.call_function(object_path, function_name, parameters)
pu.read_property(object_path, property_name)
pu.describe_object(object_path)
```

### Custom Projects

```python
pu = PlayUnreal()
pu.configure(
    gm_class="MyGameMode",
    frog_class="MyCharacter",
    module_name="MyGame",
    map_name="MainLevel",
)
```

## Transport

Remote Control HTTP on port 30010. Start with `-RCWebControlEnable` flag.
