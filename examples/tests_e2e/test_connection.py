"""E2E tests: connection and basic API verification."""

import time


def test_rc_api_alive(pu):
    """RC API should respond to health check."""
    assert pu.is_alive()


def test_get_state_returns_dict(pu):
    """get_state() should return a dict with expected keys."""
    state = pu.get_state()
    assert isinstance(state, dict)
    assert len(state) > 0


def test_get_state_has_game_state(pu):
    """State dict should include a gameState field."""
    state = pu.get_state()
    assert "gameState" in state


def test_diagnose_reports_connection(pu):
    """diagnose() should report successful connection."""
    report = pu.diagnose()
    assert report["connection"]["status"] == "OK"
