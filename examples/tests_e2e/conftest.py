"""Pytest fixtures for PlayUnreal E2E tests.

Provides session-scoped client connection and per-test game reset.

Usage in tests::

    def test_hop_changes_position(playing_game, pu):
        state_before = pu.get_state()
        pu.hop("up")
        time.sleep(0.3)
        state_after = pu.get_state()
        assert state_after["frogPos"] != state_before["frogPos"]
"""

import os
import sys
import time

import pytest

# Add the python package to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "python"))

from playunreal import PlayUnreal, PlayUnrealError


@pytest.fixture(scope="session")
def pu():
    """Session-scoped PlayUnreal client.

    Connects once at the start of the test session. Skips all tests
    if the Remote Control API is not reachable.
    """
    client = PlayUnreal()
    if not client.is_alive():
        pytest.skip(
            "Remote Control API not responding on localhost:30010. "
            "Launch the editor with: ./Tools/PlayUnreal/run-playunreal.sh"
        )
    return client


@pytest.fixture
def playing_game(pu):
    """Reset game to Playing state before each test.

    Calls reset_game() and waits until gameState is "Playing".
    Yields the initial state dict.
    """
    pu.reset_game()
    try:
        state = pu.wait_for_state("Playing", timeout=10)
    except PlayUnrealError:
        state = pu.get_state()
    yield state


@pytest.fixture
def screenshot_dir(tmp_path):
    """Provide a temporary directory for test screenshots."""
    d = tmp_path / "screenshots"
    d.mkdir()
    return d
