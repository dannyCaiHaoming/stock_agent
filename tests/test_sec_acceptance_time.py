"""acceptanceDateTime 的含义：真正的 UTC；转纽约时间必须与 EDGAR 索引页 “Accepted” 一致。样本取自真实申报，不联网。"""
import json
import unittest
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from product.mcp.live.sec import parse_index_accepted, parse_submission_page, parse_submissions
from product.mcp.provenance import parse_timestamp

NY = ZoneInfo("America/New_York")
INDEX_HTML = """<div class="formGrouping">
         <div class="infoHead">Filing Date</div>
         <div class="info">2026-07-30</div>
         <div class="infoHead">Accepted</div>
         <div class="info">2026-07-30 16:30:28</div>
         <div class="infoHead">Documents</div>
         <div class="info">14</div></div>"""
# (accession, form, JSON acceptanceDateTime, 索引页 Accepted)：夏令时、冬令时、盘前、盘后
REAL = [
    ("0000320193-26-000018", "8-K", "2026-07-30T20:30:28.000Z", "2026-07-30 16:30:28"),
    ("0000320193-20-000010", "10-Q", "2020-01-28T23:02:44.000Z", "2020-01-28 18:02:44"),
    ("0000019617-26-000231", "8-K", "2026-07-14T10:30:38.000Z", "2026-07-14 06:30:38"),
    ("0001193125-18-134732", "8-K", "2018-04-26T20:04:03.000Z", "2018-04-26 16:04:03"),
]


def page(rows):
    return {
        "accessionNumber": [r[0] for r in rows], "acceptanceDateTime": [r[2] for r in rows],
        "form": [r[1] for r in rows], "primaryDocument": ["d.htm"] * len(rows), "reportDate": [""] * len(rows),
    }


class AcceptanceTimeTests(unittest.TestCase):
    def ny_clock(self, published):
        return parse_timestamp(published).astimezone(NY).strftime("%Y-%m-%d %H:%M:%S")

    def test_recent_array_is_true_utc(self):
        raw = json.dumps({"cik": 320193, "filings": {"recent": page(REAL)}}).encode()
        filings = parse_submissions(raw, cik="320193", retrieved_at="2026-10-27T00:00:00Z")
        for accession, _form, _json, index in REAL:
            self.assertEqual(self.ny_clock(filings[accession]["published_at"]), index)

    def test_history_page_is_true_utc(self):
        raw = json.dumps(page(REAL)).encode()
        filings = parse_submission_page(raw, cik="320193", name="CIK0000320193-submissions-001.json",
                                        retrieved_at="2026-10-27T00:00:00Z")
        for accession, _form, _json, index in REAL:
            self.assertEqual(self.ny_clock(filings[accession]["published_at"]), index)

    def test_index_page_accepted_is_new_york_clock(self):
        self.assertEqual(parse_index_accepted(INDEX_HTML), datetime(2026, 7, 30, 20, 30, 28, tzinfo=UTC))
        self.assertEqual(parse_index_accepted(INDEX_HTML.encode()), datetime(2026, 7, 30, 20, 30, 28, tzinfo=UTC))
        with self.assertRaisesRegex(ValueError, "SEC_INDEX_ACCEPTED_MISSING"):
            parse_index_accepted("<html></html>")

    def test_double_offset_response_is_detectable_against_index(self):
        # 2026-10 中旬的错误响应：夏令时多 4 小时、冬令时多 5 小时，字符串形式仍合法，JSON 自身无法识别。
        shifted = {"0000320193-26-000018": "2026-07-31T00:30:28.000Z", "0000320193-20-000010": "2020-01-29T04:02:44.000Z"}
        for accession, _form, good, index in REAL[:2]:
            wrong = parse_timestamp(shifted[accession]) - parse_index_accepted(f'Accepted</div><div class="info">{index}</div>')
            self.assertEqual(wrong.total_seconds(), 4 * 3600 if "-07-" in good else 5 * 3600)
            self.assertNotEqual(self.ny_clock(shifted[accession]), index)


if __name__ == "__main__":
    unittest.main()
