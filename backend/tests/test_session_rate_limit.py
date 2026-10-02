"""PC-13 A: the opt-in per-client limit on POST /sessions."""

import unittest
from unittest.mock import patch

from backend.tests.test_vertical_slice import HAVE_DEPS, SliceBase

if HAVE_DEPS:
    from backend.app.core.config import get_settings
    from backend.app.services.rate_limit import WINDOW_SECONDS, SessionRateLimiter, session_limiter


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@unittest.skipUnless(HAVE_DEPS, "EXT-001 backend packages not installed (Tier 1 run)")
class TestLimiter(unittest.TestCase):
    def test_zero_means_off(self):
        limiter = SessionRateLimiter()
        self.assertTrue(all(limiter.allow("a", 0) for _ in range(500)))

    def test_limit_applies_per_client_in_a_rolling_hour(self):
        clock = Clock()
        limiter = SessionRateLimiter(clock)
        self.assertTrue(all(limiter.allow("a", 3) for _ in range(3)))
        self.assertFalse(limiter.allow("a", 3))
        self.assertTrue(limiter.allow("b", 3), "another client is unaffected")
        clock.now += WINDOW_SECONDS
        self.assertTrue(limiter.allow("a", 3), "the window rolls")


@unittest.skipUnless(HAVE_DEPS, "EXT-001 backend packages not installed (Tier 1 run)")
class TestCreateSessionLimit(SliceBase):
    def setUp(self):
        session_limiter.reset()
        self.addCleanup(session_limiter.reset)

    def create(self):
        return self.client.post("/sessions", json={"channel": "mobile_chat", "consent": "granted", "lang": "en"})

    def test_off_by_default_keeps_the_frozen_behaviour(self):
        self.assertEqual(get_settings().SESSION_RATE_LIMIT_PER_HOUR, 0)
        self.assertTrue(all(self.create().status_code == 201 for _ in range(5)))

    def test_over_the_limit_is_429_in_the_frozen_error_shape(self):
        with patch.object(get_settings(), "SESSION_RATE_LIMIT_PER_HOUR", 2):
            self.assertEqual([self.create().status_code for _ in range(2)], [201, 201])
            refused = self.create()
        self.assertEqual(refused.status_code, 429)
        self.assertEqual(refused.json(), {"detail": "too many sessions; try again later"})
        self.assertNotIn("testclient", refused.text)


if __name__ == "__main__":
    unittest.main()
