import unittest

from product.deterministic import moment_context as mc


def row(ticker, date, **context):
    return {"ticker": ticker, "date": date, "context": context}


class MomentContextTests(unittest.TestCase):
    def test_direction_and_dedupe(self):
        self.assertEqual((mc.direction("uptrend_break"), mc.direction("failed_breakdown"), mc.direction("baseline_days")),
                         ("down", "up", None))
        rows = [row("A", "2024-01-02"), row("A", "2024-01-02"), row("B", "2024-01-02")]
        self.assertEqual(len(mc.dedupe(rows)), 2)

    def test_missing_values_use_the_fitted_median_and_nearest_orders_by_distance(self):
        fit = [row("A", "d", ret_60d=v, sessions_since_earnings=90) for v in (0.0, 0.1, 0.2)]
        scaler = mc.fit_scaler(fit + [row("A", "d", ret_60d=None)])
        index = mc.FEATURES.index("ret_60d")
        self.assertAlmostEqual(mc.vector({}, scaler)[index], mc.vector({"ret_60d": 0.1}, scaler)[index])
        self.assertEqual(mc.raw({"sessions_since_earnings": 90})[mc.FEATURES.index("sessions_since_earnings")], 60.0)
        pool = [(r, mc.vector(r["context"], scaler)) for r in fit]
        near = mc.nearest(mc.vector({"ret_60d": 0.19, "sessions_since_earnings": 90}, scaler), pool, 2)
        self.assertEqual([r["context"]["ret_60d"] for r, _ in near], [0.2, 0.1])

    def test_spearman(self):
        self.assertAlmostEqual(mc.spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)
        self.assertAlmostEqual(mc.spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)


if __name__ == "__main__":
    unittest.main()
