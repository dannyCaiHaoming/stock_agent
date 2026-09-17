from __future__ import annotations

import unittest

from product.mcp.live.ownership import parse_ownership_document


FILING = {
    "form": "4", "accession": "0000000001-26-000001",
    "published_at": "2026-09-12T21:30:00Z",
    "document_url": "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/ownership.xml",
}


class OwnershipParserTests(unittest.TestCase):
    def test_form4_preserves_transaction_type_raw_values_and_lag(self):
        raw = b"""<?xml version='1.0'?>
<ownershipDocument>
  <issuer><issuerCik>0000000001</issuerCik></issuer>
  <reportingOwner><reportingOwnerId><rptOwnerCik>0000000002</rptOwnerCik><rptOwnerName>Example Owner</rptOwnerName></reportingOwnerId>
  <reportingOwnerRelationship><isDirector>1</isDirector><isOfficer>0</isOfficer><isTenPercentOwner>0</isTenPercentOwner><isOther>0</isOther></reportingOwnerRelationship></reportingOwner>
  <nonDerivativeTable><nonDerivativeTransaction>
    <securityTitle><value>Common Stock</value></securityTitle>
    <transactionDate><value>2026-09-10</value></transactionDate>
    <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
    <transactionAmounts><transactionShares><value>100</value></transactionShares><transactionPricePerShare><value>25.50</value></transactionPricePerShare><transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts>
    <postTransactionAmounts><sharesOwnedFollowingTransaction><value>1100</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
    <ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
  </nonDerivativeTransaction></nonDerivativeTable>
</ownershipDocument>"""
        result = parse_ownership_document(
            raw, filing=FILING, security_id="US:COMMON_STOCK:TEST",
            retrieved_at="2026-09-13T01:00:00Z",
        )
        fact = result["evidence"][0]
        self.assertEqual(fact["value"]["transaction_code"], "P")
        self.assertEqual(fact["value"]["shares"], "100")
        self.assertEqual(fact["value"]["price_per_share"], "25.50")
        self.assertEqual(fact["as_of"], "2026-09-10T00:00:00Z")
        self.assertEqual(fact["published_at"], "2026-09-12T21:30:00Z")
        self.assertEqual(fact["source_type"], "sec")
        self.assertEqual(fact["source_version"], "sec-ownership-xml/1.1.1")
        self.assertEqual(fact["metadata"]["quantity_basis"], "as_reported/not_split_adjusted")

        raw_url = (
            "https://www.sec.gov/Archives/edgar/data/1/"
            "000000000126000001/form4.xml"
        )
        submitted_url = (
            "https://www.sec.gov/Archives/edgar/data/1/"
            "000000000126000001/xslF345X06/form4.xml"
        )
        resolved = parse_ownership_document(
            raw,
            filing=dict(
                FILING,
                document_url=raw_url,
                submission_document_url=submitted_url,
                document_resolution_version="sec-ownership-document-resolution/1.0.0",
            ),
            security_id="US:COMMON_STOCK:TEST",
            retrieved_at="2026-09-13T01:00:00Z",
        )["evidence"][0]
        self.assertEqual(resolved["source_locator"], raw_url)
        self.assertEqual(resolved["metadata"]["submission_document_url"], submitted_url)
        self.assertEqual(
            resolved["metadata"]["document_resolution_version"],
            "sec-ownership-document-resolution/1.0.0",
        )

    def test_grant_is_not_relabelled_as_purchase_and_empty_form_is_explicit(self):
        raw = b"""<ownershipDocument><reportingOwner><reportingOwnerId><rptOwnerName>Owner</rptOwnerName></reportingOwnerId></reportingOwner>
<nonDerivativeTable><nonDerivativeTransaction><securityTitle><value>Stock Award</value></securityTitle>
<transactionDate><value>2026-09-10</value></transactionDate><transactionCoding><transactionCode>A</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>50</value></transactionShares><transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts>
</nonDerivativeTransaction></nonDerivativeTable></ownershipDocument>"""
        fact = parse_ownership_document(raw, filing=FILING, security_id="TEST", retrieved_at="2026-09-13T00:00:00Z")["evidence"][0]
        self.assertEqual(fact["value"]["transaction_code"], "A")
        self.assertIsNone(fact["value"]["price_per_share"])
        empty = parse_ownership_document(b"<ownershipDocument/>", filing=FILING, security_id="TEST", retrieved_at="2026-09-13T00:00:00Z")
        self.assertEqual(empty["gaps"][0]["reason"], "SEC_OWNERSHIP_NO_TRANSACTIONS")

    def test_exercise_transfer_and_derivative_nature_remain_raw_codes(self):
        raw = b"""<ownershipDocument><reportingOwner><reportingOwnerId><rptOwnerName>Owner</rptOwnerName></reportingOwnerId></reportingOwner>
<nonDerivativeTable>
  <nonDerivativeTransaction><securityTitle><value>Common Stock</value></securityTitle><transactionDate><value>2026-09-10</value></transactionDate>
    <transactionCoding><transactionCode>G</transactionCode></transactionCoding><transactionAmounts><transactionShares><value>10</value></transactionShares><transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode></transactionAmounts>
    <ownershipNature><directOrIndirectOwnership><value>I</value></directOrIndirectOwnership></ownershipNature></nonDerivativeTransaction>
</nonDerivativeTable>
<derivativeTable>
  <derivativeTransaction><securityTitle><value>Option</value></securityTitle><transactionDate><value>2026-09-11</value></transactionDate>
    <transactionCoding><transactionCode>M</transactionCode></transactionCoding><transactionAmounts><transactionShares><value>20</value></transactionShares><transactionPricePerShare><value>5</value></transactionPricePerShare><transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts>
    <ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature></derivativeTransaction>
</derivativeTable></ownershipDocument>"""
        facts = parse_ownership_document(
            raw, filing=FILING, security_id="TEST", retrieved_at="2026-09-13T00:00:00Z"
        )["evidence"]
        self.assertEqual({item["value"]["transaction_code"] for item in facts}, {"G", "M"})
        derivative = next(item for item in facts if item["value"]["transaction_code"] == "M")
        self.assertEqual(derivative["value"]["instrument_type"], "DERIVATIVE")
        transfer = next(item for item in facts if item["value"]["transaction_code"] == "G")
        self.assertEqual(transfer["value"]["ownership_nature"], "I")

    def test_future_publication_and_wrong_form_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "PUBLICATION_AFTER_RETRIEVAL"):
            parse_ownership_document(
                b"<ownershipDocument/>", filing=FILING, security_id="TEST",
                retrieved_at="2026-09-12T20:00:00Z",
            )
        with self.assertRaisesRegex(ValueError, "FORM_UNSUPPORTED"):
            parse_ownership_document(
                b"<ownershipDocument/>", filing=dict(FILING, form="10-K"),
                security_id="TEST", retrieved_at="2026-09-13T00:00:00Z",
            )


if __name__ == "__main__":
    unittest.main()
