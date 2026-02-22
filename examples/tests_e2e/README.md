# E2E Tests

Pytest examples that drive a running Unreal Engine game via PlayUnreal.

## Prerequisites

- Editor running with Remote Control API enabled
- `pip install -e python/` (or `sys.path` includes `python/`)

## Running

```bash
# Launch game first
./Tools/PlayUnreal/run-playunreal.sh --no-launch

# Then run tests
pytest examples/tests_e2e/ -v

# Or use the full pipeline
./Tools/PlayUnreal/run-playunreal.sh
pytest examples/tests_e2e/ -v
```

## Fixtures

- `pu` — Session-scoped PlayUnreal client (auto-checks connection)
- `playing_game` — Function-scoped: resets game and waits for Playing state
