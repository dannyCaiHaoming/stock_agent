from __future__ import annotations

import hashlib
import unittest

from product.mcp.live.sec_segments import parse_segment_facts


class SecSegmentTests(unittest.TestCase):
    def document(self, raw: bytes):
        return {
            "raw_content_hash": hashlib.sha256(raw).hexdigest(),
            "source_id": "sec-filing:0000320193:sample",
            "source_locator": "https://www.sec.gov/Archives/sample.xml",
            "security_id": "US:COMMON_STOCK:AAPL",
            "cik": "0000320193",
            "accession": "0000320193-26-000001",
            "form": "10-K",
            "published_at": "2026-08-01T12:00:00Z",
            "retrieved_at": "2026-08-02T12:00:00Z",
        }

    def test_axis_member_period_and_elimination_are_preserved(self):
        raw = b'''<?xml version="1.0"?>
        <xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
              xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
              xmlns:us-gaap="http://fasb.org/us-gaap/2026"
              xmlns:aapl="http://apple.com/2026">
          <xbrli:unit id="USD"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
          <xbrli:context id="segment-product">
            <xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">320193</xbrli:identifier>
              <xbrli:segment><xbrldi:explicitMember dimension="srt:ProductOrServiceAxis">aapl:IPhoneMember</xbrldi:explicitMember></xbrli:segment>
            </xbrli:entity><xbrli:period><xbrli:startDate>2025-09-29</xbrli:startDate><xbrli:endDate>2026-09-28</xbrli:endDate></xbrli:period>
          </xbrli:context>
          <xbrli:context id="segment-elimination">
            <xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">320193</xbrli:identifier>
              <xbrli:segment><xbrldi:explicitMember dimension="srt:ConsolidationItemsAxis">aapl:EliminationsMember</xbrldi:explicitMember></xbrli:segment>
            </xbrli:entity><xbrli:period><xbrli:startDate>2025-09-29</xbrli:startDate><xbrli:endDate>2026-09-28</xbrli:endDate></xbrli:period>
          </xbrli:context>
          <us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax contextRef="segment-product" unitRef="USD" decimals="-6">1000</us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax>
          <us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax contextRef="segment-elimination" unitRef="USD" decimals="-6">-10</us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax>
        </xbrl>'''
        result = parse_segment_facts(raw, self.document(raw))
        self.assertEqual(len(result["evidence"]), 2)
        self.assertEqual(result["evidence"][0]["aggregation_status"], "REPORTED_CONTEXT_ONLY_NOT_SUMMED")
        self.assertEqual(
            {item["segment_role"] for item in result["evidence"]},
            {"REPORTED_MEMBER", "ELIMINATION_OR_CONSOLIDATION"},
        )
        self.assertEqual(result["evidence"][0]["period_start"], "2025-09-29")

    def test_total_without_dimension_does_not_become_a_segment(self):
        raw = b'''<xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:us-gaap="http://fasb.org/us-gaap/2026">
          <xbrli:context id="total"><xbrli:entity><xbrli:identifier>320193</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-28</xbrli:instant></xbrli:period></xbrli:context>
          <us-gaap:Assets contextRef="total">100</us-gaap:Assets>
        </xbrl>'''
        result = parse_segment_facts(raw, self.document(raw))
        self.assertEqual(result["evidence"], [])
        self.assertEqual(result["gaps"][0]["reason"], "SEC_SEGMENT_DIMENSION_FACTS_NOT_FOUND")

    def test_dimensioned_text_and_invalid_numeric_do_not_abort_valid_facts(self):
        raw = b'''<xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
          xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:us-gaap="http://fasb.org/us-gaap/2026"
          xmlns:aapl="http://apple.com/2026">
          <xbrli:unit id="USD"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
          <xbrli:context id="segment"><xbrli:entity><xbrli:identifier>320193</xbrli:identifier>
            <xbrli:segment><xbrldi:explicitMember dimension="srt:ProductOrServiceAxis">aapl:IPhoneMember</xbrldi:explicitMember></xbrli:segment>
          </xbrli:entity><xbrli:period><xbrli:startDate>2025-09-29</xbrli:startDate><xbrli:endDate>2026-09-28</xbrli:endDate></xbrli:period></xbrli:context>
          <aapl:SegmentDescription contextRef="segment">iPhone</aapl:SegmentDescription>
          <us-gaap:Revenue contextRef="segment" unitRef="USD">not-a-number</us-gaap:Revenue>
          <us-gaap:OperatingIncome contextRef="segment" unitRef="USD">42</us-gaap:OperatingIncome>
        </xbrl>'''
        result = parse_segment_facts(raw, self.document(raw))
        self.assertEqual(len(result["evidence"]), 1)
        self.assertEqual(result["evidence"][0]["value"], "42")
        self.assertEqual(result["gaps"][0]["reason"], "SEC_SEGMENT_NUMERIC_FACT_INVALID")
        self.assertEqual(result["gaps"][0]["invalid_count"], 1)

    def test_identical_hidden_and_rendered_fact_is_deduplicated(self):
        raw = b'''<xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
          xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:us-gaap="http://fasb.org/us-gaap/2026"
          xmlns:aapl="http://apple.com/2026">
          <xbrli:unit id="USD"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
          <xbrli:context id="segment"><xbrli:entity><xbrli:identifier>320193</xbrli:identifier>
            <xbrli:segment><xbrldi:explicitMember dimension="srt:ProductOrServiceAxis">aapl:IPhoneMember</xbrldi:explicitMember></xbrli:segment>
          </xbrli:entity><xbrli:period><xbrli:startDate>2025-09-29</xbrli:startDate><xbrli:endDate>2026-09-28</xbrli:endDate></xbrli:period></xbrli:context>
          <us-gaap:Revenue contextRef="segment" unitRef="USD">42</us-gaap:Revenue>
          <us-gaap:Revenue contextRef="segment" unitRef="USD">42</us-gaap:Revenue>
        </xbrl>'''
        result = parse_segment_facts(raw, self.document(raw))
        self.assertEqual(len(result["evidence"]), 1)
        self.assertEqual(result["gaps"][0]["reason"], "SEC_SEGMENT_DUPLICATE_FACT_DEDUPLICATED")
        self.assertEqual(result["gaps"][0]["duplicate_count"], 1)

    def test_wrong_cik_and_hash_fail_closed(self):
        raw = b'''<xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"><xbrli:context id="x"><xbrli:entity><xbrli:identifier>789</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-01-01</xbrli:instant></xbrli:period></xbrli:context></xbrl>'''
        with self.assertRaisesRegex(ValueError, "CIK_MISMATCH"):
            parse_segment_facts(raw, self.document(raw))
        document = self.document(raw)
        document["raw_content_hash"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "HASH_OR_SIZE_INVALID"):
            parse_segment_facts(raw, document)


if __name__ == "__main__":
    unittest.main()
