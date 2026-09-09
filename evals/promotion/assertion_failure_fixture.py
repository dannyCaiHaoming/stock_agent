"""Not-discovered-by-default fixture for proving assertion-failure gating."""

from __future__ import annotations

import unittest


class IntentionalPromotionAssertionFailure(unittest.TestCase):
    def test_intentional_assertion_failure(self) -> None:
        self.fail("intentional Promotion Gate negative fixture")
