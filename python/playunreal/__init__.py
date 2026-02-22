"""PlayUnreal — Playwright-style automation client for Unreal Engine.

Provides a zero-dependency Python client that drives running Unreal Engine
games via the Remote Control API (HTTP on port 30010).

Quick start::

    from playunreal import PlayUnreal

    pu = PlayUnreal()
    pu.reset_game()
    pu.hop("up")
    state = pu.get_state()
    print(state)

For async usage (planned)::

    from playunreal import Unreal

    async with Unreal.launch(uproject="MyGame.uproject") as ue:
        page = ue.page()
        await page.screenshot("artifacts/screenshot.png")
"""

__version__ = "0.1.0"

from playunreal.client import (
    PlayUnreal,
    PlayUnrealError,
    RCConnectionError,
    CallError,
)

__all__ = [
    "PlayUnreal",
    "PlayUnrealError",
    "RCConnectionError",
    "CallError",
]
