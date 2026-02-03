# PlayUnrealAutomation Plugin

Provides a stable automation surface for PlayUnreal.

## Modules

- PlayUnrealAutomation (Runtime)
- PlayUnrealAutomationEditor (Editor helpers)

## Setup

1. Enable Remote Control and Automation Driver plugins.
2. Add PlayUnrealAutomation to your project.
3. Place the PlayUnreal driver actor or subsystem in the map.
4. Start Remote Control server with `WebControl.StartServer`.

## Blueprint Surface (MVP)

- Ping
- ClickById
- TypeText
- PressKey
- ElementExists / IsVisible
- Screenshot
- FindActorByName
