"""The fixtures of the live tests.

The live tests connect to a real stack, so they wait for real. The 2 fixtures
below replace the fixtures of the same name in `tests/conftest.py`: the sleep
stays the sleep of the standard library, and the key guard reads the live key.
"""

import os

import pytest


@pytest.fixture(autouse=True)
def sleeps() -> list[float]:
    """Replace nothing: a live retry waits for real."""
    return []


@pytest.fixture
def guarded_key() -> str:
    """The key that must reach no log line and no exception: the live key."""
    return os.environ.get("ASKPILOT_API_KEY", "")
