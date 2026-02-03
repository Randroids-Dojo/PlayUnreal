# PlayUnreal

PlayUnreal is a Playwright-style automation framework for Unreal Engine. External
scripts drive a running editor or packaged game via Automation Driver and the
Remote Control API.

Status: scaffold for MVP.

## Goals

- External control (Python/TS) with locators, auto-waits, and artifacts.
- Transport-agnostic protocol (Remote Control first, custom WS later).
- CI-friendly, process-isolated automation.

## Repo Layout

- `unreal-plugin/PlayUnrealAutomation`: Unreal Engine plugin (runtime + editor).
- `python/playunreal`: Python client library (planned).
- `protocol/playunreal-api.md`: JSON-RPC-like API spec.
- `scripts`: launch + wait + run helpers.
- `examples/sample_project`: minimal UE project (planned).
- `examples/tests_e2e`: pytest examples (planned).

## MVP Transport

- Remote Control HTTP on port 30010.
- Start server with `WebControl.StartServer`.
- Packaged builds require `-RCWebControlEnable -RCWebInterfaceEnable`.

## Next Steps

- Implement Ping, ClickById, TypeText, and Screenshot in the plugin.
- Implement Python client calls to `/remote/object/call`.
