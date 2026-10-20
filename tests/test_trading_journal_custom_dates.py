"""Explicit date boundaries use a frozen clock and never call an account."""
import unittest
from pathlib import Path
from unittest.mock import patch

from product.trading_journal.cli import build_parser, run
from product.trading_journal.common import JournalError
from product.trading_journal.windows import record_in_window, resolve_window, window_membership


class CustomDateWindowTests(unittest.TestCase):
    def test_cross_year_inclusive_local_dates_filter_exact_instants(self):
        window = resolve_window('custom', start='2025-12-31', end='2026-01-02',
                                now='2026-02-01T00:00:00Z')
        self.assertEqual(window['timezone'], 'Asia/Tokyo')
        self.assertEqual(window['start'], '2025-12-31T00:00:00+09:00')
        self.assertEqual(window['end'], '2026-01-02T23:59:59.999999+09:00')
        for instant, expected in [('2025-12-30T14:59:59.999999Z', False),
                                  ('2025-12-30T15:00:00Z', True),
                                  ('2026-01-02T14:59:59.999999Z', True),
                                  ('2026-01-02T15:00:00Z', False)]:
            self.assertEqual(record_in_window({'occurred_at': instant, 'time_precision': 'SECOND'}, window), expected)

    def test_future_end_is_frozen_and_date_only_boundary_stays_uncertain(self):
        window = resolve_window('custom', start='2026-01-01', end='2026-12-31',
                                now='2026-01-02T03:04:05Z')
        self.assertEqual(window['end'], '2026-01-02T12:04:05+09:00')
        self.assertFalse(record_in_window({'occurred_at': '2026-01-02T03:04:05.000001Z'}, window))
        row = {'occurred_at': '2026-01-02', 'time_precision': 'DATE', 'source_timezone': 'Asia/Shanghai'}
        self.assertEqual(window_membership(row, window), 'BOUNDARY_UNCERTAIN')

    def test_missing_reversed_and_invalid_dates_are_rejected(self):
        for start, end in [(None, '2026-01-01'), ('2026-01-01', None),
                           ('2026-01-02', '2026-01-01'), ('2026-02-30', '2026-03-01')]:
            with self.subTest(start=start, end=end), self.assertRaises(JournalError):
                resolve_window('custom', start=start, end=end, now='2026-04-01T00:00:00Z')

    def test_cli_window_parses_custom_range_without_storage_or_broker_calls(self):
        args = build_parser().parse_args(['--repo', str(Path(__file__).resolve().parents[1]), 'window',
                                         '--period', 'custom', '--start', '2025-12-31', '--end', '2026-01-02'])
        with patch('product.trading_journal.windows.utc_now', return_value='2026-02-01T00:00:00Z'), \
             patch('product.trading_journal.cli.private_root') as storage, \
             patch('product.trading_journal.desktop.TigerDesktopCollector') as broker:
            result = run(args)
        self.assertEqual(result['timezone'], 'Asia/Tokyo')
        self.assertEqual(result['query_start_date'], '2025-12-31')
        self.assertEqual(result['query_end_date'], '2026-01-02')
        storage.assert_not_called()
        broker.assert_not_called()

    def test_legacy_lifetime_still_resolves_without_inventing_start(self):
        self.assertIsNone(resolve_window('lifetime', now='2026-01-02T03:04:05Z')['start'])


if __name__ == '__main__':
    unittest.main()
