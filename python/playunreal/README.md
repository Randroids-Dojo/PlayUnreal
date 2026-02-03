# playunreal (Python)

Planned Playwright-style client for PlayUnreal.

## Example (target API)

```python
from playunreal import Unreal

async with Unreal.launch(
    uproject="MyGame.uproject",
    map="/Game/Maps/MainMenu",
    remote_control=True,
) as ue:
    page = ue.page()
    await page.locator("id=StartButton").click()
    await page.locator("id=HUDRoot").wait_for_visible()
    await page.screenshot("artifacts/started.png")
```

## Transport

Remote Control HTTP (default 30010) calling PlayUnrealAutomation functions.
