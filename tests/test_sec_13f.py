from __future__ import annotations

import hashlib
import unittest

from product.mcp.live.sec_13f import (
    assemble_13f_period,
    compare_13f_periods,
    parse_13f_information_table,
    select_13f_information_tables,
)


def xml(cusip="037833100", shares="100"):
    return f'''<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
      <infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass>
      <cusip>{cusip}</cusip><value>15000</value><shrsOrPrnAmt><sshPrnamt>{shares}</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
      <investmentDiscretion>SOLE</investmentDiscretion><votingAuthority><Sole>{shares}</Sole><Shared>0</Shared><None>0</None></votingAuthority></infoTable>
    </informationTable>'''.encode()


def filing(period, accession, **extra):
    return {
        "form": "13F-HR", "manager_cik": "0000000001", "manager_name": "Example Manager",
        "report_period": period, "published_at": f"{period}T20:00:00Z",
        "accession": accession, "document_url": f"https://www.sec.gov/{accession}.xml", **extra,
    }


class Sec13FTests(unittest.TestCase):
    def parse(self, period="2026-06-30", accession="a", **kwargs):
        raw = xml(shares=kwargs.pop("shares", "100"))
        return parse_13f_information_table(
            raw, filing=filing(period, accession, **kwargs),
            cusip_map={"037833100": "US:COMMON_STOCK:AAPL"},
            retrieved_at="2026-09-15T12:00:00Z",
        )

    def test_units_manager_coverage_and_amendment_are_preserved(self):
        part = self.parse(
            accession="amendment", form="13F-HR/A", amendment_type="RESTATEMENT",
            amendment_number=1,
        )
        fact = part["evidence"][0]
        self.assertEqual(fact["value"]["reported_value_thousands_usd"], "15000")
        self.assertEqual(fact["value"]["shares_or_principal_type"], "SH")
        self.assertEqual(fact["value"]["amendment_type"], "RESTATEMENT")
        period = assemble_13f_period([part])
        self.assertEqual(period["coverage"], "COMPLETE_FOR_LISTED_MANAGER_ACCESSION_PARTS")

    def test_unmapped_cusip_and_incomplete_parts_are_explicit(self):
        raw = xml(cusip="000000000")
        part = parse_13f_information_table(
            raw, filing=filing("2026-06-30", "a"), cusip_map={},
            retrieved_at="2026-09-15T12:00:00Z", part_index=1, part_count=2,
        )
        self.assertEqual(part["gaps"][0]["reason"], "SEC_13F_CUSIP_UNMAPPED")
        with self.assertRaisesRegex(ValueError, "COVERAGE_INCOMPLETE"):
            assemble_13f_period([part])

    def test_two_period_comparison_does_not_silently_split_adjust(self):
        current = assemble_13f_period([self.parse("2026-06-30", "current", shares="200")])
        prior = assemble_13f_period([self.parse("2026-03-31", "prior", shares="100")])
        comparison = compare_13f_periods(current, prior)
        self.assertEqual(comparison["rows"][0]["comparison_status"], "RAW_REPORTED_NOT_SPLIT_ADJUSTED")
        adjusted = compare_13f_periods(current, prior, split_adjustments={
            "US:COMMON_STOCK:AAPL": {
                "factor": "2", "source_id": "issuer-action", "as_of": "2026-05-01T00:00:00Z",
                "retrieved_at": "2026-09-15T12:00:00Z",
            }
        })
        self.assertEqual(adjusted["rows"][0]["comparison_status"], "ADJUSTMENT_AVAILABLE_REQUIRES_EXPLICIT_CALCULATION")

    def test_repeated_cusip_rows_are_preserved_and_summed_when_types_match(self):
        repeated = xml(shares="100").replace(b"</informationTable>", xml(shares="200").split(b">", 1)[1])
        part = parse_13f_information_table(
            repeated, filing=filing("2026-06-30", "current"),
            cusip_map={"037833100": "US:COMMON_STOCK:AAPL"},
            retrieved_at="2026-09-15T12:00:00Z",
        )
        self.assertEqual(len(part["evidence"]), 2)
        current = assemble_13f_period([part])
        prior = assemble_13f_period([self.parse("2026-03-31", "prior", shares="100")])
        row = compare_13f_periods(current, prior)["rows"][0]
        self.assertEqual(row["current_reported_position"], "300")
        self.assertEqual(len(row["current_evidence_ids"]), 2)

    def test_filing_index_selector_is_accession_bound_and_information_table_only(self):
        raw = b'''<html><table>
          <tr><td>1</td><td><a href="cover.xml">cover.xml</a></td><td>13F-HR</td></tr>
          <tr><td>2</td><td><a href="infotable.xml">infotable.xml</a></td><td>INFORMATION TABLE</td></tr>
        </table></html>'''
        selected = select_13f_information_tables(
            raw, filing={
                "form": "13F-HR", "cik": "0001067983",
                "accession": "0001067983-26-000001",
            }, index_record={"raw_content_hash": hashlib.sha256(raw).hexdigest()},
        )
        self.assertEqual(len(selected["selected"]), 1)
        self.assertTrue(selected["selected"][0]["document_url"].endswith("/infotable.xml"))
        malicious = raw.replace(b"infotable.xml", b"https://evil.test/infotable.xml")
        with self.assertRaisesRegex(ValueError, "BINDING_MISMATCH"):
            select_13f_information_tables(
                malicious, filing={
                    "form": "13F-HR", "cik": "0001067983",
                    "accession": "0001067983-26-000001",
                }, index_record={"raw_content_hash": hashlib.sha256(malicious).hexdigest()},
            )

    def test_filing_index_selector_resolves_sec_xsl_display_path_to_raw_xml(self):
        raw = b'''<html><table><tr><td>2</td><td>
          <a href="xslForm13F_X02/infotable.xml">infotable.xml</a>
          </td><td>INFORMATION TABLE</td></tr></table></html>'''
        selected = select_13f_information_tables(
            raw, filing={
                "form": "13F-HR", "cik": "0001067983",
                "accession": "0001067983-26-000001",
            }, index_record={"raw_content_hash": hashlib.sha256(raw).hexdigest()},
        )["selected"][0]
        self.assertTrue(selected["document_url"].endswith("/infotable.xml"))
        self.assertTrue(selected["submission_document_url"].endswith("/xslForm13F_X02/infotable.xml"))


if __name__ == "__main__":
    unittest.main()
