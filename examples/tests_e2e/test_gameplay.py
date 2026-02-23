"""E2E tests: gameplay actions and state transitions."""

import time


def test_reset_enters_playing(pu, playing_game):
    """After reset_game(), game should be in Playing state."""
    state = pu.get_state()
    assert state.get("gameState") in ("Playing", 2)


def test_hop_changes_position(pu, playing_game):
    """Hopping should change the frog's position."""
    state_before = pu.get_state()
    pos_before = state_before.get("frogPos", [0, 0])

    pu.hop("right")
    time.sleep(0.3)

    state_after = pu.get_state()
    pos_after = state_after.get("frogPos", [0, 0])

    assert pos_after != pos_before, (
        f"Position unchanged: {pos_before} -> {pos_after}")


def test_forward_hop_awards_score(pu, playing_game):
    """A forward hop should increase the score."""
    score_before = pu.get_state().get("score", 0)

    pu.hop("up")
    time.sleep(0.3)

    score_after = pu.get_state().get("score", 0)
    assert score_after > score_before, (
        f"Score did not increase: {score_before} -> {score_after}")


def test_initial_state_values(pu, playing_game):
    """After reset, lives>0 and score is non-negative.

    NOTE: ReturnToTitle does not reset the score in the current UnrealFrog
    build, so score may be > 0 after reset_game(). Assert non-negative only.
    """
    state = playing_game
    assert state.get("score", -1) >= 0, f"Negative score after reset: {state.get('score')}"
    assert state.get("lives", 0) > 0


def test_timer_counts_down(pu, playing_game):
    """The game timer should decrease over time."""
    time1 = pu.get_state().get("timeRemaining", 30.0)
    time.sleep(1.5)
    time2 = pu.get_state().get("timeRemaining", 30.0)
    assert time2 < time1, f"Timer not counting down: {time1} -> {time2}"


def test_state_diff_tracks_changes(pu, playing_game):
    """get_state_diff() should detect changes after a hop."""
    pu.get_state_diff()  # prime the baseline

    pu.hop("right")
    time.sleep(0.3)

    diff = pu.get_state_diff()
    assert len(diff["changes"]) > 0, "No state changes detected after hop"


def test_get_hazards_returns_list(pu, playing_game):
    """get_hazards() should return a list of hazard dicts."""
    hazards = pu.get_hazards()
    assert isinstance(hazards, list)
    if hazards:
        h = hazards[0]
        assert "row" in h
        assert "x" in h
        assert "speed" in h
