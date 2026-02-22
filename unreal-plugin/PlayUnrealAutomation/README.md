# PlayUnrealAutomation Plugin

Unreal Engine plugin providing a stable automation surface for PlayUnreal.

## Modules

- **PlayUnrealAutomation** (Runtime) — Core automation driver and widget helpers.

## Classes

### APlayUnrealDriver

Central automation actor. Place one in your level to expose BlueprintCallable
functions via the Remote Control API.

**Methods:**

| Function | Category | Description |
|----------|----------|-------------|
| `Ping()` | Lifecycle | Returns version + session JSON |
| `ClickById(Id)` | Input | Click a UMG widget by automation ID |
| `TypeText(Text)` | Input | Type text into focused widget |
| `PressKey(KeyChord)` | Input | Simulate key press |
| `ElementExists(Id)` | Query | Check if widget exists |
| `IsVisible(Id)` | Query | Check if widget is visible |
| `Screenshot(Path)` | Evidence | Capture screenshot to Saved/ |
| `FindActorByName(Name)` | World | Find actor by name, return path |
| `CallFunction(ObjectPath, FunctionName, ParamsJSON)` | World | Call arbitrary UFUNCTION |
| `WaitForSeconds(Seconds)` | Timing | Game-time delay |

### UPlayUnrealStatics

Blueprint function library for tagging widgets with automation IDs.

| Function | Description |
|----------|-------------|
| `SetAutomationId(Widget, Id)` | Tag a UMG widget with a test-visible ID |
| `GetAutomationId(Widget)` | Retrieve the automation ID from a widget |

## Setup

1. Copy `PlayUnrealAutomation/` into your project's `Plugins/` directory.
2. Enable `RemoteControl` plugin in your `.uproject`.
3. Add `-RCWebControlEnable` to your launch flags.
4. Place an `APlayUnrealDriver` actor in your level.
5. Tag widgets with `UPlayUnrealStatics::SetAutomationId()`.

## Usage from Python

```python
from playunreal import PlayUnreal

pu = PlayUnreal()
# Call driver methods via RC API
result = pu.call_function(
    "/Game/Maps/Main.Main:PersistentLevel.PlayUnrealDriver_0",
    "Ping"
)
```

## Implementation Status

- `Ping`, `Screenshot`, `FindActorByName`: Implemented
- `ClickById`, `TypeText`, `PressKey`: Stub (requires Automation Driver wiring)
- `ElementExists`, `IsVisible`: Stub (requires widget tree traversal)
- `SetAutomationId`/`GetAutomationId`: Implemented via static map
