import unittest

from product.deterministic import key_moments as km


def series(tail: list[float], n: int = 320) -> tuple[list[str], list[float]]:
    """A flat, mildly noisy history (99.4 / 100.6) followed by `tail`."""
    closes = [100 + (0.6 if i % 2 else -0.6) for i in range(n)] + tail
    return [f"d{i:04d}" for i in range(len(closes))], closes


class KeyMomentTests(unittest.TestCase):
    def moments(self, tail):
        dates, closes = series(tail)
        return [(m["moment"], m["index"] - 320) for m in km.detect(dates, closes) if m["index"] >= 320]

    def test_break_below_a_tight_range_is_a_breakdown_and_recovery_is_a_failed_breakdown(self):
        found = self.moments([98.0, 99.0, 100.3])
        self.assertIn(("platform_breakdown", 0), found)
        self.assertIn(("failed_breakdown", 2), found)

    def test_break_above_a_tight_range_at_a_new_high(self):
        found = self.moments([102.0])
        self.assertIn(("platform_breakout", 0), found)
        self.assertIn(("platform_breakout_new_high", 0), found)

    def test_nothing_is_flagged_inside_the_range(self):
        self.assertEqual(self.moments([100.0, 100.5, 99.5]), [])

    def test_detection_uses_no_later_data(self):
        dates, closes = series([98.0, 99.0, 100.3])
        full = [m for m in km.detect(dates, closes) if m["index"] <= 320]
        cut = km.detect(dates[:321], closes[:321])
        self.assertEqual(full, cut)

    def test_outcome_and_summary_math(self):
        dates, closes = [f"d{i}" for i in range(70)], [100.0] * 2 + [110.0] * 68
        closes[1] = 100.0
        out = km.outcome(dates, closes, {d: 1.0 for d in dates}, 0)
        self.assertEqual(out["5"]["ret"], 0.1)
        self.assertEqual(out["5"]["excess"], 0.1)
        rows = [{"5": {"ret": r, "excess": r, "worst": min(r, 0.0), "exit_date": "x"}} for r in (0.10, 0.20, -0.10, -0.30)]
        s = km.summarize(rows, 5)
        self.assertEqual((s["n"], s["p_up"], s["avg_gain_pct"], s["avg_loss_pct"], s["expectancy_pct"]),
                         (4, 0.5, 15.0, -20.0, -2.5))


if __name__ == "__main__":
    unittest.main()
