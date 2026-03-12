"""Pytest root conftest: ensure project root is on sys.path for imports."""
import sys
from pathlib import Path

import pytest

# Add project root so "pages" and "exceptions" resolve when running tests
_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Viewport size used when running tests (browser "maximum" size)
VIEWPORT_WIDTH = 1920
VIEWPORT_HEIGHT = 1080


@pytest.fixture(autouse=True)
def set_viewport_max(page):
    """Set browser viewport to maximum size before each test."""
    page.set_viewport_size({"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT})
    yield


@pytest.fixture(autouse=True)
def keep_browser_open(page):
    """Keep the browser open after each test (pass or fail). Close the Inspector or browser when done."""
    yield
    page.pause()