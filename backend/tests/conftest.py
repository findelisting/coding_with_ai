import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rate_limit import location_rate_limiter  # noqa: E402


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    location_rate_limiter.reset()
    yield
    location_rate_limiter.reset()
