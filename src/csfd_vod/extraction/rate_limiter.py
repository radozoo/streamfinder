"""Rate limiting with exponential backoff."""

import time
import random
from typing import Optional


class RateLimiter:
    """Manage request rate limiting with exponential backoff and jitter."""

    def __init__(self, delay_ms: int = 500, jitter_ms: int = 200):
        """
        Initialize rate limiter.

        Args:
            delay_ms: Base delay between requests in milliseconds
            jitter_ms: Random jitter to add (0 to jitter_ms)
        """
        self.delay_ms = delay_ms
        self.jitter_ms = jitter_ms
        self.last_request_time: Optional[float] = None

    def wait(self):
        """Wait until it's safe to make the next request."""
        if self.last_request_time is None:
            self.last_request_time = time.time()
            return

        elapsed_ms = (time.time() - self.last_request_time) * 1000
        wait_ms = self.delay_ms + random.uniform(0, self.jitter_ms)

        if elapsed_ms < wait_ms:
            time.sleep((wait_ms - elapsed_ms) / 1000)

        self.last_request_time = time.time()

    def get_backoff(self, attempt: int) -> float:
        """
        Get exponential backoff time for retry attempt.

        Args:
            attempt: Retry attempt number (0-indexed)

        Returns:
            Time to wait in seconds
        """
        # Exponential: 1s, 2s, 4s, 8s, etc. + random jitter
        backoff_sec = (2 ** attempt) + random.uniform(0, 1)
        return backoff_sec

    def reset(self):
        """Reset the rate limiter."""
        self.last_request_time = None
