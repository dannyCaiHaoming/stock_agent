from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from product.trading_journal.cli import build_parser, run
from product.trading_journal.common import JournalError
from product.trading_journal.ledger import Ledger
from product.trading_journal.packaging import OVERLAY_ROOTS, prepare_clean_source, verify_installed_source
from product.trading_journal.privacy import private_root, tree_hash

ROOT = Path(__file__).resolve().parents[1]
CSV = ('Execution ID,Trade Time,Symbol,Asset Type,Market,Currency,Side,Quantity,Price,Total Fees\n'
       'f1,2026-09-25T14:00:00-04:00,AAPL,STOCK,US,USD,BUY,2,100,0\n'
       'f2,2026-09-26T14:00:00-04:00,AAPL,STOCK,US,USD,SELL,1,110,0\n')


class JournalCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.registry_patch = patch('product.trading_journal.packaging._registered_install', return_value={'synthetic': True})
        self.registry_patch.start()
        self.addCleanup(self.registry_patch.stop)
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        self.root = self.root.resolve()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        (self.root / '.gitignore').write_text('/product/.private/\n/.codex-local/\n')
        runtime = self.root / 'product/runtime'
        runtime.mkdir(parents=True)
        (runtime / 'common_stock_stage.py').write_text(
            'import shutil\nshutil.copytree(product_root,target,ignore=shutil.ignore_patterns(".private"))\n')
        for relative in OVERLAY_ROOTS:
            shutil.copytree(ROOT / 'product' / relative, self.root / 'product' / relative,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        (self.root / 'product/version-manifest.json').write_text(json.dumps({
            'skills': {'tiger-trade-journal': '1.2.0', 'trading-reflection': '1.2.0'}}))
        registry = self.root / '.agents/plugins'
        registry.mkdir(parents=True)
        (registry / 'marketplace.json').write_text(json.dumps(
            {'plugins': [{'name': 'product', 'source': {'source': 'local', 'path': './product'}}]}))
        baseline = Path(self.temp.name) / 'baseline'
        (baseline / '.codex-plugin').mkdir(parents=True)
        (baseline / '.codex-plugin/plugin.json').write_text('{"name":"product"}')
        (baseline / 'version-manifest.json').write_text('{"skills":{}}')
        prepare_clean_source(self.root, baseline, expected_baseline_hash=tree_hash(baseline),
                             expected_overlay_hashes={key: tree_hash(self.root / 'product' / key) for key in OVERLAY_ROOTS},
                             activate=True)
        installed = Path(self.temp.name).resolve() / 'installed'
        shutil.copytree(self.root / '.codex-local/product-plugin', installed)
        write_root = private_root(self.root, create=True)
        from product.trading_journal.privacy import write_private
        write_private(write_root / 'synthetic-private-isolation-sentinel.txt', 'SYNTHETIC_PRIVATE_ISOLATION_SENTINEL\n')
        with patch('product.trading_journal.packaging._registered_install', return_value={'synthetic': True}):
            verify_installed_source(self.root, installed)
        self.csv = Path(self.temp.name) / 'official.csv'
        self.csv.write_text(CSV)

    def tearDown(self):
        self.temp.cleanup()

    def command(self, *values):
        return run(build_parser().parse_args(['--repo', str(self.root), *map(str, values)]))

    def import_source(self, *extra):
        return self.command('import', '--input', self.csv, '--period', 'custom',
                            '--start', '2026-09-01', '--end', '2026-09-30', *extra)

    def test_manual_import_persists_only_exact_selected_interval(self):
        imported = self.command('import', '--input', self.csv, '--new-account',
                                '--period', 'custom', '--start', '2026-09-25T18:00:00Z',
                                '--end', '2026-09-25T18:00:00Z')
        self.assertEqual(imported['receipt']['inserted'], 1)
        with Ledger(private_root(self.root), read_only=True) as ledger:
            all_saved = ledger.current_records(imported['account_ref'])
        self.assertEqual(len(all_saved), 1)
        self.assertEqual(all_saved[0]['occurred_at'], '2026-09-25T18:00:00Z')

    def test_import_repeat_chart_and_reflection_share_frozen_private_ledger(self):
        imported = self.import_source('--new-account')
        self.assertEqual(imported['receipt']['inserted'], 2)
        repeated = self.import_source('--account-ref', imported['account_ref'])
        self.assertEqual(repeated['receipt']['unchanged'], 2)
        self.assertEqual(repeated['receipt']['inserted'], 0)
        chart = self.command('chart', '--snapshot-id', imported['snapshot_id'])
        self.assertEqual(chart['snapshot_id'], imported['snapshot_id'])
        self.assertTrue(Path(chart['chart_path']).is_relative_to(self.root / 'product/.private/trading-journal'))
        self.assertEqual(Path(chart['chart_path']).stat().st_mode & 0o777, 0o600)
        packet = self.command('prepare-reflection', '--snapshot-id', imported['snapshot_id'],
                              '--chart-ref', imported['snapshot_id'])
        saved = json.loads(Path(packet['packet_path']).read_text())
        self.assertEqual(saved['snapshot']['snapshot_id'], imported['snapshot_id'])
        self.assertEqual(len(saved['snapshot']['records']), 2)
        self.assertEqual(saved['scope']['mode'], 'SNAPSHOT_WINDOW')

    def test_initialize_empty_ledger_then_list_without_account_access(self):
        with patch('product.trading_journal.desktop.TigerDesktopCollector') as collector:
            self.assertEqual(self.command('init')['status'], 'INITIALIZED')
            self.assertEqual(self.command('list'), {'accounts': [], 'snapshots': []})
        collector.assert_not_called()
        self.assertEqual((private_root(self.root) / 'journal.sqlite').stat().st_mode & 0o777, 0o600)

    def test_chart_reader_upgrade_preserves_old_snapshot_page(self):
        imported = self.import_source('--new-account')
        storage = private_root(self.root)
        legacy = storage / 'artifacts' / (imported['snapshot_id'] + '.html')
        legacy.parent.mkdir(mode=0o700, exist_ok=True)
        legacy.write_text('<!doctype html><p>旧版虚构阅读页</p>')
        legacy.chmod(0o600)
        before = (legacy.read_bytes(), legacy.stat().st_mtime_ns)
        with patch('product.trading_journal.desktop.TigerDesktopCollector') as broker, \
             patch('product.trading_journal.market.fetch_market') as market:
            first = self.command('chart', '--snapshot-id', imported['snapshot_id'])
            second = self.command('chart', '--snapshot-id', imported['snapshot_id'])
        broker.assert_not_called()
        market.assert_not_called()
        self.assertNotEqual(first['chart_path'], str(legacy))
        self.assertEqual(first['chart_path'], second['chart_path'])
        self.assertEqual(first['content_hash'], hashlib.sha256(Path(first['chart_path']).read_bytes()).hexdigest())
        self.assertEqual((legacy.read_bytes(), legacy.stat().st_mtime_ns), before)

    def test_saved_reflection_review_reuses_immutable_page_without_account_or_market_access(self):
        from product.trading_journal.reflection import PHASES
        imported = self.import_source('--new-account')
        prepared = self.command('prepare-reflection', '--snapshot-id', imported['snapshot_id'],
                                '--chart-ref', imported['snapshot_id'])
        packet = json.loads(Path(prepared['packet_path']).read_text())
        records = packet['scope']['record_ids']
        episodes = [item['episode_id'] for item in packet['episodes']]
        research = {'findings': [{'finding_id': 'synthetic-review', 'pattern': '合成资料边界',
                     'record_refs': records, 'episode_refs': episodes,
                     'chart_refs': [imported['snapshot_id']],
                     'process_observation': '只能核验记录，原始计划未知。',
                     'result_observation': '费用与窗口边界保留来源状态。',
                     'interpretation': '需要同期记录才能核验执行。',
                     'confidence_limits': '合成传输案例，不是研究质量验收。',
                     'alternative_explanations': [{'text': '也可能存在未保存的合理原始计划。',
                                                   'record_refs': records, 'episode_refs': episodes}]}],
                    'improvement_plan': [{'improvement_id': 'synthetic-practice',
                     'finding_refs': ['synthetic-review'], 'record_refs': records,
                     'exercise': '保留同期计划', 'next_inputs': ['原记录时刻'],
                     'verification': '核对记录先后', 'review_window': '四周', 'status': 'PROPOSED'}],
                    'phase_coverage': {phase: {'status': 'DATA_LIMITED', 'reason': '合成资料限制'}
                                       for phase in PHASES}, 'analyzed_episode_ids': episodes}
        source = Path(self.temp.name) / 'synthetic-research.json'
        source.write_text(json.dumps(research, ensure_ascii=False))
        saved = self.command('save-reflection', '--packet', prepared['packet_path'],
                             '--research', source, '--model-version', 'synthetic-no-call')
        originals = [Path(saved[key]) for key in ('json_path', 'markdown_path', 'packet_path')]
        database = private_root(self.root) / 'journal.sqlite'
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in [database, *originals]}
        with patch('product.trading_journal.desktop.TigerDesktopCollector') as collector, \
             patch('product.trading_journal.market.fetch_market') as fetch:
            first = self.command('review-reflection', '--report-id', saved['report_id'])
            view = Path(first['review_path'])
            view_before = (view.read_bytes(), view.stat().st_mtime_ns)
            repeated = self.command('review-reflection', '--report-id', saved['report_id'])
        collector.assert_not_called()
        fetch.assert_not_called()
        self.assertFalse(first['reused'])
        self.assertTrue(repeated['reused'])
        self.assertEqual(first['review_path'], repeated['review_path'])
        self.assertEqual((view.read_bytes(), view.stat().st_mtime_ns), view_before)
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before})
        self.assertEqual(view.stat().st_mode & 0o777, 0o600)
        self.assertTrue(view.is_relative_to(private_root(self.root) / 'artifacts/reflections'))
        self.assertNotIn(imported['account_ref'], view.read_text())

    def test_missing_period_refuses_before_storage_or_client(self):
        target = self.root / 'product/.private/trading-journal/journal.sqlite'
        with patch('product.trading_journal.desktop.TigerDesktopCollector') as collector:
            with self.assertRaises(JournalError) as failure:
                self.command('collect', '--profile', self.csv, '--new-account')
        self.assertEqual(failure.exception.code, 'TIME_WINDOW_REQUIRED')
        collector.assert_not_called()
        self.assertFalse(target.exists())

    def test_list_is_read_only_and_does_not_contact_account(self):
        self.import_source('--new-account')
        directory = self.root / 'product/.private/trading-journal'
        before = {str(path.relative_to(directory)): (path.read_bytes(), path.stat().st_mtime_ns)
                  for path in directory.rglob('*') if path.is_file()}
        with patch('product.trading_journal.desktop.TigerDesktopCollector') as collector:
            result = self.command('list')
        collector.assert_not_called()
        self.assertEqual(len(result['accounts']), 1)
        after = {str(path.relative_to(directory)): (path.read_bytes(), path.stat().st_mtime_ns)
                 for path in directory.rglob('*') if path.is_file()}
        self.assertEqual(before, after)

    def test_market_refresh_derives_old_snapshot_without_newer_records(self):
        imported = self.import_source('--new-account')
        self.csv.write_text(CSV + 'f3,2026-09-27T14:00:00-04:00,AAPL,STOCK,US,USD,BUY,1,120,0\n')
        self.import_source('--account-ref', imported['account_ref'])
        empty_market = {'symbol': 'AAPL', 'instrument_key': 'synthetic-market', 'candles': [],
                        'events': [], 'gaps': [{'code': 'SYNTHETIC_NO_QUOTES'}],
                        'price_basis': 'PROVIDER_UNVERIFIED', 'exchange_timezone': 'America/New_York',
                        'source_id': 'synthetic-market', 'as_of': '2026-10-01T00:00:00Z',
                        'retrieved_at': '2026-10-01T00:00:00Z'}
        with patch('product.trading_journal.market.fetch_market', return_value=empty_market):
            chart = self.command('chart', '--snapshot-id', imported['snapshot_id'], '--fetch-market')
        with Ledger(private_root(self.root), read_only=True) as ledger:
            child = ledger.load_snapshot(chart['snapshot_id'])
            parent = ledger.load_snapshot(imported['snapshot_id'])
        self.assertEqual(child['records'], parent['records'])
        self.assertEqual(len(child['records']), 2)
        self.assertEqual(child['coverage'], parent['coverage'])
        self.assertEqual(child['parent_snapshot_id'], imported['snapshot_id'])

    def test_account_or_period_cannot_change_frozen_snapshot_selection(self):
        imported = self.import_source('--new-account')
        for extra in (['--account-ref', 'account-other'], ['--period', 'week']):
            with self.subTest(extra=extra), self.assertRaises(JournalError) as failure:
                self.command('chart', '--snapshot-id', imported['snapshot_id'], *extra)
            self.assertEqual(failure.exception.code, 'FROZEN_SNAPSHOT_SELECTION_CONFLICT')

    def test_research_cannot_override_runtime_metadata(self):
        self.import_source('--new-account')
        packet = Path(self.temp.name) / 'packet.json'
        research = Path(self.temp.name) / 'research.json'
        packet.write_text('{}')
        research.write_text('{"model_version":"fabricated"}')
        with self.assertRaises(JournalError) as failure:
            self.command('save-reflection', '--packet', packet, '--research', research, '--model-version', 'synthetic')
        self.assertEqual(failure.exception.code, 'RESEARCH_FIELDS_NOT_ALLOWED')

    def test_ax_headers_fees_and_collection_conversion_lineage_are_persisted(self):
        profile = Path(self.temp.name) / 'profile.json'
        profile.write_text('{"source_timezone":"America/New_York"}')
        capture = {'source_id': 'tiger-desktop:' + 'a' * 64, 'source_hash': 'a' * 64,
                   'as_of': '2026-09-30T23:59:59+08:00', 'retrieved_at': '2026-10-01T00:00:00Z',
                   'rows': [{'execution_id': 'native-fill', 'occurred_at': '2026-09-25 14:00:00',
                             'symbol': 'AAPL', 'side': 'BUY', 'quantity': '2', 'price': '100',
                             'currency': 'USD', 'market': 'US', 'asset_class': 'STOCK',
                             'commission': '1', 'total_fees': '3', 'order_id': 'native-order'}],
                   'pages': [{'page_index': 1, 'page_hash': 'b' * 64, 'row_count': 1, 'end_proven': True}],
                   'actions': [{'action': 'read_history_view', 'at': '2026-10-01T00:00:00Z', 'status': 'SUCCEEDED'}],
                   'gaps': [], 'pagination_end_proven': True}
        with patch('product.trading_journal.desktop.TigerDesktopCollector') as collector:
            collector.return_value.capture.return_value = capture
            result = self.command('collect', '--profile', profile, '--new-account', '--period', 'custom',
                                  '--start', '2026-09-01', '--end', '2026-09-30')
        with Ledger(private_root(self.root), read_only=True) as ledger:
            snapshot = ledger.load_snapshot(result['snapshot_id'])
        record = snapshot['records'][0]
        self.assertEqual(record['fees'], '3')
        self.assertTrue(record['fees_complete'])
        self.assertEqual(record['order_id'], 'native-order')
        self.assertEqual(record['occurred_at'], '2026-09-25T18:00:00Z')
        lineage = result['receipt']['coverage']['collection_receipt']
        self.assertEqual(lineage['original_source_hash'], 'a' * 64)
        path = private_root(self.root) / 'sources' / (lineage['receipt_id'] + '.json')
        stored = json.loads(path.read_text())
        self.assertEqual(stored['actions'][0]['action'], 'read_history_view')
        self.assertEqual(stored['pages'][0]['page_hash'], 'b' * 64)
        self.assertEqual(stored['normalized_csv_hash'], result['receipt']['source_hash'])
        self.assertEqual(snapshot['coverage']['status'], 'PARTIAL')

    def test_repository_and_clean_copy_scripts_bind_same_data_from_any_cwd(self):
        imported = self.import_source('--new-account')
        entries = [self.root / 'product/skills/tiger-trade-journal/scripts/journal.py',
                   self.root / '.codex-local/product-plugin/skills/tiger-trade-journal/scripts/journal.py']
        outputs = []
        for entry in entries:
            result = subprocess.run(['python3', str(entry), '--repo', str(self.root), 'list'],
                                    cwd=Path(self.temp.name), capture_output=True, text=True, check=True)
            outputs.append(json.loads(result.stdout))
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0]['snapshots'][0]['snapshot_id'], imported['snapshot_id'])

    def computer_use_fixture(self, csv_text=CSV, *, period='custom'):
        from product.trading_journal.windows import resolve_window
        storage = private_root(self.root, real=True)
        sources = storage / 'sources'
        source = sources / 'computer-use-export.csv'
        source.write_text(csv_text, encoding='utf-8')
        window = resolve_window(period, start='2026-09-01' if period == 'custom' else None,
                                end='2026-09-30' if period == 'custom' else None,
                                now='2026-10-01T00:00:00Z')
        self.computer_use_period = period
        self.computer_use_start = '2026-09-01' if period == 'custom' else None
        self.computer_use_end = window['end']
        receipt = {'receipt_id': 'computer-use-' + 'a' * 32,
                   'source_id': 'tiger-computer-use:' + 'b' * 32,
                   'as_of': window['end'], 'retrieved_at': '2026-10-01T00:00:00Z',
                   'method': 'CODEX_COMPUTER_USE_EXPORT', 'requested_window': window,
                   'source_timezone': 'America/New_York', 'export_view': 'trade_records',
                   'original_source_hash': hashlib.sha256(source.read_bytes()).hexdigest(),
                   'actions': ['OPEN_APP', 'NAVIGATE_ACCOUNT', 'NAVIGATE_TRADE_HISTORY',
                               'SELECT_TRADE_RECORDS', 'SET_DATE_RANGE', 'EXPORT_CSV', 'SAVE_EXPORT']}
        receipt_path = sources / 'computer-use-receipt.json'
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
        os.chmod(source, 0o600)
        os.chmod(receipt_path, 0o600)
        return storage, source, receipt_path, receipt

    def computer_use_import(self, source, receipt_path, *extra):
        bounds = ['--end', self.computer_use_end]
        if self.computer_use_start:
            bounds.extend(['--start', self.computer_use_start])
        return self.command('import', '--input', source, '--computer-use-receipt', receipt_path,
                            '--period', self.computer_use_period, '--new-account', *bounds, *extra)

    def assert_computer_use_rejected_before_mutation(self, storage, source, receipt_path, *extra):
        from product.trading_journal.privacy import PrivacyError
        before = {str(path.relative_to(storage)): path.read_bytes()
                  for path in storage.rglob('*') if path.is_file() and not path.is_symlink()}
        with patch('product.trading_journal.ledger.Ledger', side_effect=AssertionError('invalid receipt opened ledger')) as ledger, \
                patch('product.trading_journal.cli.write_private', side_effect=AssertionError('invalid receipt wrote a new source')) as write_source, \
                patch('product.trading_journal.computer_use.parse_csv', side_effect=AssertionError('invalid receipt normalized rows')) as parse, \
                self.assertRaises((JournalError, PrivacyError)) as failure:
            self.computer_use_import(source, receipt_path, *extra)
        ledger.assert_not_called()
        write_source.assert_not_called()
        parse.assert_not_called()
        after = {str(path.relative_to(storage)): path.read_bytes()
                 for path in storage.rglob('*') if path.is_file() and not path.is_symlink()}
        self.assertEqual(before, after)
        self.assertFalse((storage / 'journal.sqlite').exists())
        return failure.exception

    def test_computer_use_per_row_timezone_rejects_trade_view_before_mutation(self):
        storage, source, receipt_path, receipt = self.computer_use_fixture()
        receipt['source_timezone'] = 'PER_ROW'
        receipt_path.write_text(json.dumps(receipt), encoding='utf-8')
        error = self.assert_computer_use_rejected_before_mutation(storage, source, receipt_path)
        self.assertEqual(error.code, 'COMPUTER_USE_TIMEZONE_INVALID')

    def test_computer_use_statement_view_requires_actual_statement_format_before_mutation(self):
        storage, source, receipt_path, receipt = self.computer_use_fixture()
        receipt['source_timezone'] = 'PER_ROW'
        receipt['export_view'] = 'account_statement'
        receipt['actions'].extend(['NAVIGATE_STATEMENTS', 'SELECT_FILL_DETAILS'])
        receipt_path.write_text(json.dumps(receipt), encoding='utf-8')
        error = self.assert_computer_use_rejected_before_mutation(storage, source, receipt_path)
        self.assertEqual(error.code, 'COMPUTER_USE_STATEMENT_REQUIRED')

    def test_computer_use_statement_view_requires_fill_detail_selection_before_mutation(self):
        storage, source, receipt_path, receipt = self.computer_use_fixture()
        receipt['source_timezone'] = 'PER_ROW'
        receipt['export_view'] = 'account_statement'
        receipt_path.write_text(json.dumps(receipt), encoding='utf-8')
        error = self.assert_computer_use_rejected_before_mutation(storage, source, receipt_path)
        self.assertEqual(error.code, 'COMPUTER_USE_ACTIONS_INVALID')

    def test_computer_use_statement_saves_mixed_timezones_filters_window_and_repeats(self):
        from tests.test_trading_journal_statement import detail, encode, header, product, PRODUCT_HEADER
        rows = [
            ['账户信息', 'PRIVATE NAME', '99887766', 'PRIVATE ADDRESS'],
            header(),
            detail(code='示例公司 (EXMP)', amount='10', timestamp='2026-09-25 09:47:28, US/Eastern'),
            detail(amount='10', timestamp='2026-09-25 09:47:28, US/Eastern'),
            detail(code='示例港股 (01191)', amount='10', market='HK', currency='HKD', timestamp='2026-09-25 10:00:00, GMT+8'),
            detail(amount='10', market='HK', currency='HKD', timestamp='2026-09-25 10:00:00, GMT+8'),
            detail(code='示例公司 (EXMP)', amount='10', timestamp='2026-10-01 10:00:00, GMT+8'),
            detail(amount='10', timestamp='2026-10-01 10:00:00, GMT+8'),
            header('期权'),
            detail(code='示例期权 (EXMP 20261017 PUT 60.0)', asset='期权', amount='50', price='2', timestamp='2026-09-26 09:47:28, US/Eastern'),
            detail(asset='期权', amount='50', price='2', timestamp='2026-09-26 09:47:28, US/Eastern'),
            PRODUCT_HEADER, product(expiry='2026-10-17', multiplier='25'),
        ]
        storage, source, receipt_path, receipt = self.computer_use_fixture(encode(rows).decode('utf-8-sig'))
        receipt.update(source_timezone='PER_ROW', export_view='account_statement')
        receipt['actions'].extend(['NAVIGATE_STATEMENTS', 'SELECT_FILL_DETAILS'])
        receipt_path.write_text(json.dumps(receipt), encoding='utf-8')
        first = self.computer_use_import(source, receipt_path, '--source-timezone', 'PER_ROW')
        self.assertEqual(first['receipt']['inserted'], 3)
        self.assertEqual(first['receipt']['coverage']['status'], 'PARTIAL')
        with Ledger(storage, read_only=True) as ledger:
            snapshot = ledger.load_snapshot(first['snapshot_id'])
        self.assertEqual(len(snapshot['records']), 3)
        self.assertEqual({item['source_timezone'] for item in snapshot['records']}, {'America/New_York', 'Etc/GMT-8'})
        option = next(item for item in snapshot['records'] if item['instrument']['asset_type'] == 'OPTION')
        self.assertEqual(option['instrument']['multiplier'], '25')
        self.assertNotIn('PRIVATE', json.dumps(snapshot))
        self.assertNotIn('99887766', json.dumps(snapshot))
        second = self.computer_use_import(source, receipt_path, '--account-ref', first['account_ref'])
        self.assertEqual(second['receipt']['inserted'], 0)
        self.assertEqual(second['receipt']['unchanged'], 3)
        self.assertTrue((storage / 'sources' / (receipt['original_source_hash'] + '.csv')).exists())
        self.assertTrue((storage / 'sources' / (receipt['receipt_id'] + '.json')).exists())

    def test_computer_use_export_persists_receipt_lineage_and_distinct_mode_without_coverage_upgrade(self):
        storage, source, receipt_path, original = self.computer_use_fixture(
            CSV.replace('2026-09-25T14:00:00-04:00', '2026-09-25 14:00:00')
               .replace('2026-09-26T14:00:00-04:00', '2026-09-26 14:00:00'))
        original_receipt_bytes = receipt_path.read_bytes()
        os.chmod(source, 0o644)
        os.chmod(receipt_path, 0o644)
        result = self.computer_use_import(source, receipt_path)
        self.assertEqual(result['status'], 'SAVED')
        coverage = result['receipt']['coverage']
        self.assertEqual(coverage['collection_mode'], 'COMPUTER_USE_EXPORT')
        self.assertFalse(coverage['automatic_client_collection'])
        self.assertEqual(coverage['status'], 'PARTIAL')
        lineage = coverage['collection_receipt']
        self.assertEqual(set(lineage), {'receipt_id', 'content_hash', 'source_id', 'as_of',
                                        'retrieved_at', 'original_source_hash', 'normalized_csv_hash'})
        self.assertEqual(lineage['original_source_hash'], original['original_source_hash'])
        self.assertEqual(lineage['normalized_csv_hash'], original['original_source_hash'])
        wrapper = json.loads((storage / 'sources' / (lineage['receipt_id'] + '.json')).read_text())
        self.assertEqual(wrapper['parent_receipt_id'], original['receipt_id'])
        persisted_receipt = storage / 'sources' / (original['receipt_id'] + '.json')
        self.assertEqual(json.loads(persisted_receipt.read_text()), original)
        self.assertEqual(persisted_receipt.read_bytes(), original_receipt_bytes)
        self.assertEqual(wrapper['parent_receipt_hash'], hashlib.sha256(persisted_receipt.read_bytes()).hexdigest())
        self.assertEqual(persisted_receipt.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(receipt_path.read_text()), original)
        self.assertEqual(receipt_path.read_bytes(), original_receipt_bytes)
        self.assertEqual(source.stat().st_mode & 0o777, 0o600)
        self.assertEqual(receipt_path.stat().st_mode & 0o777, 0o600)
        with Ledger(storage, read_only=True) as ledger:
            saved = ledger.load_snapshot(result['snapshot_id'])
        self.assertEqual(saved['records'][0]['source_timezone'], 'America/New_York')
        self.assertEqual(saved['records'][0]['occurred_at'], '2026-09-25T18:00:00Z')
        manual = self.import_source('--new-account')
        self.assertEqual(manual['receipt']['coverage']['collection_mode'], 'USER_ASSISTED')

    def test_computer_use_export_empty_or_all_outside_window_refuses_before_persistent_writes(self):
        from product.trading_journal import computer_use
        cases = [(CSV.replace('2026-09-25', '2026-08-01').replace('2026-09-26', '2026-08-02'),
                  'NO_RECORDS_IN_WINDOW'),
                 (CSV.splitlines()[0] + '\n', 'EMPTY_EXPORT_UNPROVEN')]
        for text, expected_code in cases:
            with self.subTest(code=expected_code):
                storage, source, receipt_path, _ = self.computer_use_fixture(text)
                before = {str(path.relative_to(storage)): path.read_bytes()
                          for path in storage.rglob('*') if path.is_file()}
                with patch('product.trading_journal.ledger.Ledger', side_effect=AssertionError('empty export opened ledger')) as ledger, \
                        patch('product.trading_journal.computer_use.persist_receipt', wraps=computer_use.persist_receipt) as persist, \
                        patch('product.trading_journal.cli.write_private', side_effect=AssertionError('empty export wrote collection wrapper')) as write_source, \
                        self.assertRaises(JournalError) as failure:
                    self.computer_use_import(source, receipt_path)
                self.assertEqual(failure.exception.code, expected_code)
                ledger.assert_not_called()
                persist.assert_not_called()
                write_source.assert_not_called()
                after = {str(path.relative_to(storage)): path.read_bytes()
                         for path in storage.rglob('*') if path.is_file()}
                self.assertEqual(after, before)
                self.assertFalse((storage / 'journal.sqlite').exists())

    def test_computer_use_export_frozen_source_survives_original_overwrite_and_rename(self):
        storage, source, receipt_path, original = self.computer_use_fixture()
        original_bytes = source.read_bytes()
        result = self.computer_use_import(source, receipt_path)
        frozen = storage / 'sources' / (original['original_source_hash'] + '.csv')
        self.assertTrue(frozen.is_file())
        self.assertFalse(frozen.is_symlink())
        self.assertEqual(frozen.stat().st_nlink, 1)
        self.assertEqual(frozen.stat().st_mode & 0o777, 0o600)
        self.assertNotEqual(frozen.stat().st_ino, source.stat().st_ino)
        self.assertEqual(frozen.read_bytes(), original_bytes)
        source.write_bytes(b'SYNTHETIC_OVERWRITTEN_EXPORT\n')
        renamed = source.with_name('renamed-computer-use-export.csv')
        source.rename(renamed)
        renamed.write_bytes(b'SYNTHETIC_OVERWRITTEN_AFTER_RENAME\n')
        self.assertFalse(source.exists())
        self.assertEqual(frozen.read_bytes(), original_bytes)
        self.assertEqual(hashlib.sha256(frozen.read_bytes()).hexdigest(), original['original_source_hash'])
        with Ledger(storage, read_only=True) as ledger:
            snapshot = ledger.load_snapshot(result['snapshot_id'])
        self.assertEqual({row['source_hash'] for row in snapshot['records']}, {original['original_source_hash']})
        self.assertEqual(len(snapshot['records']), 2)

    def test_computer_use_export_existing_frozen_source_conflicts_and_links_refuse_without_overwrite(self):
        from product.trading_journal.privacy import PrivacyError
        storage, source, receipt_path, original = self.computer_use_fixture()
        frozen = storage / 'sources' / (original['original_source_hash'] + '.csv')
        link_target = Path(self.temp.name) / 'synthetic-link-target.csv'
        link_target.write_bytes(source.read_bytes())
        os.chmod(link_target, 0o600)
        for kind, expected_code in (('conflicting_file', 'COMPUTER_USE_HASH_CONFLICT'),
                                    ('symlink', 'JOURNAL_SYMLINK_FORBIDDEN'),
                                    ('hardlink', 'COMPUTER_USE_SOURCE_INVALID')):
            if kind == 'conflicting_file':
                frozen.write_bytes(b'SYNTHETIC_EXISTING_CONFLICT\n')
                os.chmod(frozen, 0o600)
            elif kind == 'symlink':
                frozen.symlink_to(link_target)
            else:
                os.link(link_target, frozen)
            try:
                with self.subTest(kind=kind):
                    before = {str(path.relative_to(storage)): path.read_bytes()
                              for path in storage.rglob('*') if path.is_file() and not path.is_symlink()}
                    target_bytes = link_target.read_bytes()
                    with patch('product.trading_journal.ledger.Ledger', side_effect=AssertionError('source conflict opened ledger')) as ledger, \
                            patch('product.trading_journal.cli.write_private', side_effect=AssertionError('source conflict wrote wrapper')) as wrapper, \
                            self.assertRaises((JournalError, PrivacyError)) as failure:
                        self.computer_use_import(source, receipt_path)
                    self.assertEqual(failure.exception.code, expected_code)
                    ledger.assert_not_called()
                    wrapper.assert_not_called()
                    after = {str(path.relative_to(storage)): path.read_bytes()
                             for path in storage.rglob('*') if path.is_file() and not path.is_symlink()}
                    self.assertEqual(after, before)
                    self.assertEqual(link_target.read_bytes(), target_bytes)
                    self.assertEqual(frozen.is_symlink(), kind == 'symlink')
                    if kind == 'symlink':
                        self.assertEqual(frozen.readlink(), link_target)
                    elif kind == 'conflicting_file':
                        self.assertEqual(frozen.read_bytes(), b'SYNTHETIC_EXISTING_CONFLICT\n')
                    self.assertFalse((storage / 'sources' / (original['receipt_id'] + '.json')).exists())
                    self.assertFalse((storage / 'journal.sqlite').exists())
            finally:
                frozen.unlink()

    def test_computer_use_export_exact_window_filters_boundary_overfetch_before_ledger(self):
        text = CSV + (
            'before,2026-08-31T14:59:59Z,AAPL,STOCK,US,USD,BUY,1,100,0\n'
            'first,2026-08-31T15:00:00Z,AAPL,STOCK,US,USD,BUY,1,100,0\n'
            'last,2026-09-30T14:59:59.999999Z,AAPL,STOCK,US,USD,SELL,1,100,0\n'
            'after,2026-09-30T15:00:00Z,AAPL,STOCK,US,USD,SELL,1,100,0\n')
        storage, source, receipt_path, _ = self.computer_use_fixture(text)
        result = self.computer_use_import(source, receipt_path)
        self.assertEqual(result['receipt']['inserted'], 4)
        with Ledger(storage, read_only=True) as ledger:
            current = ledger.current_records(result['account_ref'])
            snapshot = ledger.load_snapshot(result['snapshot_id'])
        expected = {'f1', 'f2', 'first', 'last'}
        self.assertEqual({row['source_record_id'] for row in current}, expected)
        self.assertEqual({row['source_record_id'] for row in snapshot['records']}, expected)

    def test_computer_use_export_trade_records_view_does_not_reclassify_order_as_fill(self):
        text = ('Symbol,Asset Type,Market,Currency,Side,Quantity,Average Price,Order Time,Order ID,Status\n'
                'AAPL,STOCK,US,USD,BUY,100,99,2026-09-25 14:00:00,order-only,CANCELLED\n')
        storage, source, receipt_path, _ = self.computer_use_fixture(text)
        result = self.computer_use_import(source, receipt_path)
        with Ledger(storage, read_only=True) as ledger:
            snapshot = ledger.load_snapshot(result['snapshot_id'])
        self.assertEqual(len(snapshot['records']), 1)
        self.assertEqual(snapshot['records'][0]['activity_type'], 'ORDER')
        self.assertEqual(snapshot['records'][0]['status'], 'CANCELLED')
        self.assertEqual(snapshot['analysis']['episodes'], [])
        self.assertEqual(result['receipt']['coverage']['status'], 'PARTIAL')

    def test_computer_use_export_rejects_unknown_private_fields_and_invalid_provenance_before_mutation(self):
        import copy
        storage, source, receipt_path, original = self.computer_use_fixture()
        invalid = [
            {**original, 'account_number': 'synthetic-private-account'},
            {**original, 'receipt_id': 'computer-use-' + 'A' * 32},
            {**original, 'source_id': 'tiger-source:' + 'b' * 32},
            {**original, 'method': 'USER_ASSISTED'},
            {**original, 'export_view': 'orders'},
            {**original, 'actions': ['EXPORT_CSV']},
            {**original, 'actions': ['SAVE_EXPORT']},
            {**original, 'actions': []},
            {**original, 'actions': ['EXPORT_CSV', 'SAVE_EXPORT', 'CREATE_ORDER']},
            {**original, 'actions': ['EXPORT_CSV', 'SAVE_EXPORT', {'script': 'arbitrary'}]},
            {**original, 'actions': ['EXPORT_CSV', 'SAVE_EXPORT'] * 17},
            {key: value for key, value in original.items() if key != 'retrieved_at'},
        ]
        for index, receipt in enumerate(invalid):
            with self.subTest(case=index):
                receipt_path.write_text(json.dumps(copy.deepcopy(receipt)))
                failure = self.assert_computer_use_rejected_before_mutation(storage, source, receipt_path)
                self.assertNotIn('synthetic-private-account', str(failure))

    def test_computer_use_export_rejects_time_window_hash_and_timezone_conflicts_before_mutation(self):
        import copy
        storage, source, receipt_path, original = self.computer_use_fixture()
        changed_window = copy.deepcopy(original['requested_window'])
        changed_window['start'] = '2026-09-02T00:00:00+08:00'
        private_window = {**original['requested_window'], 'account_number': 'synthetic-private-account'}
        invalid = [
            {**original, 'as_of': '2026-09-30T23:59:58+08:00'},
            {**original, 'as_of': '2026-09-30T23:59:59.999999'},
            {**original, 'retrieved_at': '2026-09-30T00:00:00Z'},
            {**original, 'retrieved_at': '2099-01-01T00:00:00Z'},
            {**original, 'retrieved_at': '2026-10-01T00:00:00'},
            {**original, 'requested_window': changed_window},
            {**original, 'requested_window': private_window},
            {**original, 'original_source_hash': 'a' * 64},
            {**original, 'original_source_hash': 'not-a-sha256'},
            {**original, 'source_timezone': 'Not/A-Timezone'},
        ]
        for index, receipt in enumerate(invalid):
            with self.subTest(case=index):
                receipt_path.write_text(json.dumps(receipt))
                self.assert_computer_use_rejected_before_mutation(storage, source, receipt_path)
        receipt_path.write_text(json.dumps(original))
        self.assert_computer_use_rejected_before_mutation(storage, source, receipt_path,
                                                          '--source-timezone', 'Asia/Shanghai')

    def test_computer_use_export_requires_absolute_private_direct_children_without_links(self):
        storage, source, receipt_path, _ = self.computer_use_fixture()
        outside_source = Path(self.temp.name) / 'outside-export.csv'
        outside_source.write_bytes(source.read_bytes())
        outside_receipt = Path(self.temp.name) / 'outside-receipt.json'
        outside_receipt.write_bytes(receipt_path.read_bytes())
        nested = storage / 'sources' / 'nested'
        nested.mkdir(mode=0o700)
        nested_source = nested / source.name
        nested_source.write_bytes(source.read_bytes())
        nested_receipt = nested / receipt_path.name
        nested_receipt.write_bytes(receipt_path.read_bytes())
        pairs = [(outside_source, receipt_path), (source, outside_receipt),
                 (Path('product/.private/trading-journal/sources/' + source.name), receipt_path),
                 (source, Path('product/.private/trading-journal/sources/' + receipt_path.name)),
                 (nested_source, receipt_path), (source, nested_receipt)]
        for candidate_source, candidate_receipt in pairs:
            with self.subTest(source=str(candidate_source), receipt=str(candidate_receipt)):
                self.assert_computer_use_rejected_before_mutation(storage, candidate_source, candidate_receipt)
        for candidate, other, is_source in ((source, receipt_path, True), (receipt_path, source, False)):
            for kind in ('symlink', 'hardlink'):
                linked = storage / 'sources' / (kind + '-' + candidate.name)
                if kind == 'symlink':
                    linked.symlink_to(candidate)
                else:
                    os.link(candidate, linked)
                try:
                    with self.subTest(kind=kind, is_source=is_source):
                        source_arg, receipt_arg = (linked, other) if is_source else (other, linked)
                        self.assert_computer_use_rejected_before_mutation(storage, source_arg, receipt_arg)
                finally:
                    linked.unlink()
        os.chmod(storage / 'sources', 0o755)
        try:
            self.assert_computer_use_rejected_before_mutation(storage, source, receipt_path)
        finally:
            os.chmod(storage / 'sources', 0o700)

    def test_computer_use_export_validates_receipt_before_csv_read_and_requires_receipt_file(self):
        from product.trading_journal import computer_use
        storage, source, receipt_path, original = self.computer_use_fixture()
        receipt_path.write_text(json.dumps({**original, 'account_number': 'synthetic-private-account'}))
        with patch('product.trading_journal.computer_use._read_private', wraps=computer_use._read_private) as read:
            failure = self.assert_computer_use_rejected_before_mutation(storage, source, receipt_path)
        self.assertEqual(failure.code, 'COMPUTER_USE_RECEIPT_FIELDS_INVALID')
        read.assert_called_once_with(receipt_path, storage, computer_use.MAX_RECEIPT_BYTES,
                                     missing_code='COMPUTER_USE_RECEIPT_REQUIRED')
        missing = storage / 'sources' / 'missing-receipt.json'
        failure = self.assert_computer_use_rejected_before_mutation(storage, source, missing)
        self.assertEqual(failure.code, 'COMPUTER_USE_RECEIPT_REQUIRED')

    def test_computer_use_export_frozen_rolling_window_survives_clock_changes_and_rejects_unfrozen_end(self):
        storage, source, receipt_path, original = self.computer_use_fixture(period='week')
        snapshots = []
        for current in ('2026-10-01T01:00:00Z', '2026-10-03T01:00:00Z'):
            with self.subTest(clock=current), \
                    patch('product.trading_journal.windows.utc_now', return_value=current), \
                    patch('product.trading_journal.computer_use.utc_now', return_value=current):
                result = self.computer_use_import(source, receipt_path)
            self.assertEqual(result['receipt']['coverage']['request'], original['requested_window'])
            snapshots.append(result['snapshot_id'])
        with Ledger(storage, read_only=True) as ledger:
            windows = [ledger.load_snapshot(identity)['coverage']['requested_window'] for identity in snapshots]
        self.assertEqual(windows, [original['requested_window']] * 2)
        for end in ([], ['--end', '2026-10-01'], ['--end', '2026-10-01T08:00:00']):
            with self.subTest(end=end), \
                    patch('product.trading_journal.cli.private_root', side_effect=AssertionError('unfrozen end reached storage')) as private, \
                    patch('product.trading_journal.ledger.Ledger', side_effect=AssertionError('unfrozen end reached ledger')) as ledger, \
                    self.assertRaises(JournalError) as failure:
                self.command('import', '--input', source, '--computer-use-receipt', receipt_path,
                             '--period', 'week', '--new-account', *end)
            self.assertEqual(failure.exception.code, 'COMPUTER_USE_FROZEN_END_REQUIRED')
            private.assert_not_called()
            ledger.assert_not_called()


class ProductCopyIsolationTests(unittest.TestCase):
    def test_affected_test_fixture_copies_exclude_private_sentinel(self):
        paths = ['test_component_versions.py', 'test_native_decision_contract.py',
                 'test_runtime_promotion.py', 'test_agent_package_demo.py']
        count = 0
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source'
            (source / '.private/trading-journal').mkdir(parents=True)
            (source / '.private/trading-journal/sentinel').write_text('SYNTHETIC_PRIVATE_SENTINEL')
            (source / 'public.py').write_text('public')
            for filename in paths:
                tree = ast.parse((ROOT / 'tests' / filename).read_text())
                bindings = {target.id: assignment.value for assignment in tree.body
                            if isinstance(assignment, ast.Assign) for target in assignment.targets
                            if isinstance(target, ast.Name)}
                for call in ast.walk(tree):
                    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                            and call.func.attr == 'copytree' and call.args):
                        continue
                    first = call.args[0]
                    if isinstance(first, ast.Name) and first.id in bindings:
                        first = bindings[first.id]
                    if (isinstance(first, ast.Call) and isinstance(first.func, ast.Name)
                            and first.func.id == 'str' and len(first.args) == 1):
                        first = first.args[0]
                    if not (isinstance(first, ast.BinOp) and isinstance(first.op, ast.Div)
                            and isinstance(first.left, ast.Name) and first.left.id == 'ROOT'
                            and isinstance(first.right, ast.Constant) and first.right.value == 'product'):
                        continue
                    ignore = next((item.value for item in call.keywords if item.arg == 'ignore'), None)
                    self.assertIsNotNone(ignore, filename)
                    callback = eval(compile(ast.Expression(ignore), '<copy-ignore>', 'eval'),
                                    {'shutil': shutil, '__builtins__': {}})
                    target = Path(temp) / f'copy-{count}'
                    shutil.copytree(source, target, ignore=callback)
                    self.assertFalse((target / '.private').exists(), filename)
                    count += 1
        self.assertGreaterEqual(count, 7)

    def test_runtime_whole_product_copy_uses_actual_ignore_callback(self):
        tree = ast.parse((ROOT / 'product/runtime/common_stock_stage.py').read_text())
        copies = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Attribute) and node.func.attr == 'copytree'
                  and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == 'product_root']
        self.assertTrue(copies)
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source'
            (source / '.private/trading-journal').mkdir(parents=True)
            (source / '.private/trading-journal/sentinel').write_text('SYNTHETIC_PRIVATE_SENTINEL')
            (source / 'public.py').write_text('public')
            for index, call in enumerate(copies):
                expression = next(item.value for item in call.keywords if item.arg == 'ignore')
                # Evaluate just the actual callback expression; never launch Runtime.
                callback = eval(compile(ast.Expression(expression), '<copy-ignore>', 'eval'),
                                {'shutil': shutil, '__builtins__': {}})
                target = Path(temp) / str(index)
                shutil.copytree(source, target, ignore=callback)
                self.assertFalse((target / '.private').exists())
                self.assertEqual((target / 'public.py').read_text(), 'public')


class DesktopNavigationCliTests(unittest.TestCase):
    """The metadata navigation entrypoint must bypass financial CLI setup."""

    def failure_output(self, failure, command='desktop-navigate'):
        from contextlib import redirect_stdout
        from io import StringIO
        from product.trading_journal.cli import main
        output = StringIO()
        args = ['--repo', '/synthetic-repo', command]
        if command == 'desktop-navigate':
            args += ['--target', 'account_nav', '--nav-proof', '/synthetic-proof.json']
        with patch('product.trading_journal.cli.run', side_effect=failure), redirect_stdout(output):
            status = main(args)
        self.assertEqual(status, 2)
        self.assertNotIn('private-not-a-real-account', output.getvalue())
        return json.loads(output.getvalue())

    def test_navigation_cli_failure_retains_only_valid_fixed_audit(self):
        for stage, issued in [('SIDEBAR_GEOMETRY_CHECK', False), ('POST_LAYOUT_READ', True)]:
            audit = {'stage': stage, 'app_activation_requested': True, 'navigation_action_issued': issued}
            failure = JournalError('NAVIGATION_HIT_UNCONFIRMED', 'private-not-a-real-account',
                                   details={'nav_audit': audit, 'account_number': 'private-not-a-real-account',
                                            'layout': {'untrusted': 'private-not-a-real-account'}})
            with self.subTest(stage=stage):
                self.assertEqual(self.failure_output(failure),
                    {'status': 'BLOCKED', 'code': 'NAVIGATION_HIT_UNCONFIRMED', 'nav_audit': audit})

    def test_navigation_cli_missing_or_invalid_audit_does_not_invent_action_state(self):
        audit = {'stage': 'SIDEBAR_GEOMETRY_CHECK', 'app_activation_requested': False,
                 'navigation_action_issued': False}
        invalid = [None, {}, {**audit, 'account_number': 'private-not-a-real-account'},
                   {**audit, 'stage': 'private-not-a-real-account'}, {**audit, 'navigation_action_issued': True},
                   {**audit, 'navigation_action_issued': 0}]
        failures = [JournalError('ACTION_TIMEOUT', 'private-not-a-real-account'),
                    JournalError('ACTION_TIMEOUT', 'private-not-a-real-account',
                                 details={'other': 'private-not-a-real-account'})]
        failures += [JournalError('ACTION_TIMEOUT', 'private-not-a-real-account', details={'nav_audit': item})
                     for item in invalid]
        for failure in failures:
            with self.subTest(details=failure.details):
                result = self.failure_output(failure)
                self.assertEqual(result, {'status': 'BLOCKED', 'code': 'ACTION_TIMEOUT'})
                self.assertNotIn('navigation_action_issued', result)

    def test_other_cli_failure_does_not_forward_navigation_or_arbitrary_details(self):
        failure = JournalError('SYNTHETIC_FAILURE', 'private-not-a-real-account', details={
            'nav_audit': {'stage': 'POST_LAYOUT_READ', 'app_activation_requested': True, 'navigation_action_issued': True},
            'other': 'private-not-a-real-account'})
        self.assertEqual(self.failure_output(failure, 'desktop-probe'),
                         {'status': 'BLOCKED', 'code': 'SYNTHETIC_FAILURE'})

    def test_desktop_navigation_needs_no_period_and_does_not_create_ledger_or_private_root(self):
        from contextlib import ExitStack
        from product.trading_journal.desktop import TigerDesktopCollector

        proof = {'bundle_id': 'com.itiger.TigerTrade-Mac', 'version': '9.27.2',
                 'build': 'synthetic-build', 'identity_hash': 'a' * 64}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            proof_path = root / 'navigation-proof.json'
            proof_path.write_text(json.dumps(proof))
            for target in ('account_nav', 'history', 'statement_nav'):
                with self.subTest(target=target), ExitStack() as stack:
                    repository = stack.enter_context(patch('product.trading_journal.cli.repository_root', return_value=root))
                    private = stack.enter_context(patch('product.trading_journal.cli.private_root', side_effect=AssertionError('no storage')))
                    ledger = stack.enter_context(patch('product.trading_journal.ledger.Ledger', side_effect=AssertionError('no ledger')))
                    window = stack.enter_context(patch('product.trading_journal.windows.resolve_window', side_effect=AssertionError('no period')))
                    guard = stack.enter_context(patch('product.trading_journal.privacy.assert_real_write_ready', side_effect=AssertionError('no financial guard')))
                    parser = stack.enter_context(patch('product.trading_journal.normalization.parse_csv', side_effect=AssertionError('no financial rows')))
                    constructor = stack.enter_context(patch('product.trading_journal.desktop.TigerDesktopCollector', spec=TigerDesktopCollector))
                    expected = {'navigation_target': target, 'source_id': 'synthetic-navigation',
                                'as_of': '2026-10-01T00:00:00Z', 'retrieved_at': '2026-10-01T00:00:00Z'}
                    constructor.return_value.navigate_history.return_value = expected
                    args = build_parser().parse_args(['--repo', str(root), 'desktop-navigate',
                                                      '--target', target, '--nav-proof', str(proof_path)])
                    self.assertFalse(hasattr(args, 'period'))
                    self.assertEqual(run(args), expected)
                    repository.assert_called_once_with(root)
                    constructor.assert_called_once_with()
                    constructor.return_value.navigate_history.assert_called_once_with(target, proof)
                    constructor.return_value.capture.assert_not_called()
                    constructor.return_value.probe.assert_not_called()
                    constructor.return_value.open_app.assert_not_called()
                    constructor.return_value.inspect_layout.assert_not_called()
                    for forbidden in (private, ledger, window, guard, parser):
                        forbidden.assert_not_called()
                self.assertFalse((root / 'product/.private').exists())
                self.assertFalse((root / 'journal.sqlite').exists())

    def test_navigation_cli_rejects_financial_or_generic_targets_before_run(self):
        import contextlib
        import io

        with patch('product.trading_journal.desktop.TigerDesktopCollector') as collector:
            for target in ('buy', 'sell', 'query', 'next_page', 'export', 'selector'):
                with self.subTest(target=target), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
                    build_parser().parse_args(['--repo', '/synthetic-repo', 'desktop-navigate',
                                               '--target', target, '--nav-proof', '/synthetic-proof.json'])
                self.assertEqual(failure.exception.code, 2)
        collector.assert_not_called()

    def test_navigation_cli_malformed_proof_reaches_validation_before_transport_or_storage(self):
        from unittest.mock import Mock
        from product.trading_journal.desktop import TigerDesktopCollector

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            proof_path = root / 'navigation-proof.json'
            proof_path.write_text(json.dumps({'bundle_id': 'com.itiger.TigerTrade-Mac', 'version': '9.27.2',
                                             'build': 'synthetic-build', 'identity_hash': 'a' * 64,
                                             'script': 'arbitrary'}))
            transport = Mock()
            collector = TigerDesktopCollector(transport=transport)
            args = build_parser().parse_args(['--repo', str(root), 'desktop-navigate',
                                              '--target', 'history', '--nav-proof', str(proof_path)])
            with patch('product.trading_journal.cli.repository_root', return_value=root), \
                    patch('product.trading_journal.desktop.TigerDesktopCollector', return_value=collector), \
                    patch('product.trading_journal.cli.private_root', side_effect=AssertionError('no storage')) as private, \
                    patch('product.trading_journal.ledger.Ledger', side_effect=AssertionError('no ledger')) as ledger, \
                    self.assertRaises(JournalError):
                run(args)
            transport.call.assert_not_called()
            private.assert_not_called()
            ledger.assert_not_called()
            self.assertFalse((root / 'product/.private').exists())


if __name__ == '__main__':
    unittest.main()
