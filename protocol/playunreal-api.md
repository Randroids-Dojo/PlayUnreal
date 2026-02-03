# PlayUnreal API (draft)

PlayUnreal exposes a stable automation surface through the PlayUnrealAutomation
plugin. The API is transport-agnostic and can be tunneled over Unreal Remote
Control HTTP for the MVP.

## Transport (Remote Control MVP)

`PUT http://127.0.0.1:30010/remote/object/call`

```json
{
  "objectPath": "/Game/Maps/Main.Main:PersistentLevel.PlayUnrealDriver_1",
  "functionName": "ClickById",
  "parameters": {
    "Id": "StartButton"
  }
}
```

## Method Conventions

- `id=...` selectors map to Automation Driver `By::Id`.
- `path=...` selectors map to `By::Path`.
- Functions return success plus optional data.

## Methods

### Ping

Parameters: none

Returns:

```json
{ "version": "0.1.0", "session": "..." }
```

### ClickById

Parameters:

```json
{ "Id": "StartButton" }
```

### TypeText

Parameters:

```json
{ "Text": "Hello" }
```

### PressKey

Parameters:

```json
{ "KeyChord": "ctrl+s" }
```

### ElementExists

Parameters:

```json
{ "Id": "StartButton" }
```

Returns:

```json
{ "exists": true }
```

### IsVisible

Parameters:

```json
{ "Id": "StartButton" }
```

Returns:

```json
{ "visible": true }
```

### WaitForSeconds

Parameters:

```json
{ "Seconds": 1.0 }
```

### Screenshot

Parameters:

```json
{ "Path": "artifacts/menu.png" }
```

Returns:

```json
{ "path": "artifacts/menu.png" }
```

### FindActorByName

Parameters:

```json
{ "Name": "Player" }
```

Returns:

```json
{ "ObjectPath": "/Game/Maps/Main.Main:PersistentLevel.Player" }
```

### CallFunction

Parameters:

```json
{
  "ObjectPath": "/Game/Maps/Main.Main:PersistentLevel.Player",
  "Function": "Reset",
  "Parameters": {}
}
```

## Errors

- Errors should include a stable code and message.
- Transport errors should map to non-200 status codes.
