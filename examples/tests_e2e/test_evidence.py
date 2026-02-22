"""E2E tests: screenshot and evidence capture."""

import os


def test_screenshot_creates_file(pu, playing_game, screenshot_dir):
    """screenshot() should create a PNG file on disk."""
    path = str(screenshot_dir / "test_shot.png")
    result = pu.screenshot(path)
    # On macOS with a visible window, this should succeed.
    # On headless/CI, screencapture may not be available.
    if result:
        assert os.path.exists(path)
        assert os.path.getsize(path) > 0
