"""Pytest root conftest: ensure project root is on sys.path for imports."""
import sys
from pathlib import Path

import pytest

# Add project root so "pages" and "exceptions" resolve when running tests
_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


@pytest.fixture(autouse=True)
def keep_browser_open(page):
    """Keep the browser open after each test (pass or fail). Close the Inspector or browser when done."""
    yield
    page.pause()