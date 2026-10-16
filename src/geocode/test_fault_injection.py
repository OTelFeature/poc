"""The value range of geocodeUpstreamFailure: UC-006 BR-002, A1/A2 and A3,
TC-005 item 7 (OTelFeature/poc#75).

The bounds are deterministic (a share at or above 1.0 fails without a draw,
one at or below 0.0 returns before it), so each case runs a batch of calls
and expects all or none to fail. Runs in the image's builder stage:
`docker build --target test src/geocode` (`make unit-test`).
"""

import math
import unittest

from fastapi import HTTPException
from openfeature import api
from openfeature.provider.in_memory_provider import InMemoryFlag, InMemoryProvider

import main

CALLS = 1000


def set_flag(*variants) -> None:
    flags = {}
    if variants:
        flags[main.FAULT_FLAG] = InMemoryFlag("v", {"v": variants[0]})
    api.set_provider(InMemoryProvider(flags))


def failures(test: unittest.TestCase) -> int:
    failed = 0
    for _ in range(CALLS):
        try:
            main.maybe_fail()
        except HTTPException as e:
            # A2 flow step 3: the injected 503 is the only exception.
            test.assertEqual(e.status_code, 503)
            failed += 1
    return failed


class FaultInjectionBounds(unittest.TestCase):
    def tearDown(self) -> None:
        api.clear_providers()

    def test_at_or_above_one_fails_every_request(self) -> None:
        for value in (1.0, 1.5, 100.0, math.inf):
            with self.subTest(value=value):
                set_flag(value)
                self.assertEqual(failures(self), CALLS)

    def test_at_or_below_zero_or_nan_fails_no_request(self) -> None:
        for value in (0.0, -0.0, -0.5, -100.0, -math.inf, math.nan):
            with self.subTest(value=value):
                set_flag(value)
                self.assertEqual(failures(self), 0)

    def test_non_numbers_fail_no_request(self) -> None:
        # A string is a type mismatch (the client returns the default 0.0);
        # a boolean passes the client's float check, since bool is an int,
        # and maybe_fail treats it as 0.0.
        for value in ("1.0", True, False):
            with self.subTest(value=value):
                set_flag(value)
                self.assertEqual(failures(self), 0)

    def test_missing_flag_fails_no_request(self) -> None:
        set_flag()
        self.assertEqual(failures(self), 0)


if __name__ == "__main__":
    unittest.main()
