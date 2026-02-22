# Sample Project

Minimal reference showing how to set up PlayUnreal automation in an Unreal Engine project.

## Setup Checklist

### 1. Enable Remote Control Plugin

In your `.uproject` file, ensure the RemoteControl plugin is enabled:

```json
{
  "Plugins": [
    {
      "Name": "RemoteControl",
      "Enabled": true
    }
  ]
}
```

### 2. Add BlueprintCallable Functions

Expose game functions to the RC API by marking them `BlueprintCallable`:

```cpp
// MyGameMode.h
UFUNCTION(BlueprintCallable, Category = "PlayUnreal")
FString GetGameStateJSON() const;

UFUNCTION(BlueprintCallable, Category = "PlayUnreal")
void StartGame();

UFUNCTION(BlueprintCallable, Category = "PlayUnreal")
void ReturnToTitle();
```

### 3. Launch with RC API Enabled

```bash
# Editor mode (with Remote Control HTTP server)
UnrealEditor MyGame.uproject \
    -game -windowed -resx=1280 -resy=720 \
    -RCWebControlEnable \
    -ExecCmds="WebControl.EnableServerOnStartup 1"
```

### 4. Connect from Python

```python
from playunreal import PlayUnreal

pu = PlayUnreal()
pu.configure(
    gm_class="MyGameMode",
    module_name="MyGame",
    map_name="MainLevel",
)

if pu.is_alive():
    state = pu.get_state()
    print(f"Game state: {state}")
```

## Key Concepts

### Object Path Discovery

PlayUnreal discovers live actor instances by probing known path patterns:

```
/Game/Maps/{MapName}.{MapName}:PersistentLevel.{ClassName}_0
```

If the live instance is not found, it falls back to the Class Default Object (CDO):

```
/Script/{ModuleName}.Default__{ClassName}
```

The CDO can describe functions/properties but cannot execute gameplay logic.

### State Queries

Implement `GetGameStateJSON()` on your GameMode to expose game state as JSON:

```cpp
FString AMyGameMode::GetGameStateJSON() const
{
    TSharedPtr<FJsonObject> Root = MakeShareable(new FJsonObject());
    Root->SetNumberField("score", Score);
    Root->SetNumberField("lives", Lives);
    Root->SetStringField("gameState", GetStateName());

    FString Output;
    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Output);
    FJsonSerializer::Serialize(Root.ToSharedRef(), Writer);
    return Output;
}
```

### Hazard Queries (Frogger-style games)

For games with moving obstacles, implement `GetLaneHazardsJSON()`:

```cpp
FString AMyGameMode::GetLaneHazardsJSON() const
{
    // Return JSON array of {row, x, speed, width, movesRight, rideable}
    // See UnrealFrog implementation for reference
}
```

## RC API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/remote/info` | GET | List available routes |
| `/remote/object/call` | PUT | Call a UFUNCTION |
| `/remote/object/property` | PUT | Read/write a UPROPERTY |
| `/remote/object/describe` | PUT | Describe object's interface |
