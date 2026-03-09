"""
Retry helpers for flaky operations (e.g. address autocomplete options not appearing).
Use for actions that may timeout due to API/network timing or dynamic option text.
"""
import time
from typing import Callable, TypeVar

from playwright._impl._errors import TimeoutError as PlaywrightTimeoutError

T = TypeVar("T")


def retry_on_timeout(
    fn: Callable[[], T],
    max_attempts: int = 3,
    delay_seconds: float = 2.0,
    timeout_errors: tuple = (PlaywrightTimeoutError,),
) -> T:
    """
    Run fn(); on timeout (or other specified errors), wait delay_seconds and retry up to max_attempts.
    Raises the last exception if all attempts fail.
    """
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except timeout_errors as e:
            last_error = e
            if attempt < max_attempts:
                time.sleep(delay_seconds)
            else:
                raise last_error from e
    raise last_error