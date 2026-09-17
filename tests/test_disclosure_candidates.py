from __future__ import annotations

from copy import deepcopy
import unittest

from product.runtime.disclosure_candidates import build_candidate_input, build_candidate_output


def disclosure(*, truncated=False):
    return {
        "evidence_id": "ev-sec-text-1", "source_id": "sec-filing",
        "source_locator": "https://www.sec.gov/filing", "as_of": "2026-09-10T00:00:00Z",
        "published_at": "2026-09-10T20:00:00Z", "retrieved_at": "2026-09-11T00:00:00Z",
        "raw_content_hash": "a" * 64,
        "text": "One anonymous customer represented 15% of revenue. Product users reached 10 million.",
        "raw_character_spans": [[0, 84]], "truncated": truncated,
    }


def relationship_claim():
    return {
        "claim_id": "claim-1", "claim_type": "RELATIONSHIP",
        "text": "An anonymous customer represented 15% of revenue.",
        "evidence_id": "ev-sec-text-1", "source_quote": "anonymous customer represented 15% of revenue",
        "relationship_basis": "ANONYMOUS_DISCLOSURE", "anonymity_status": "ANONYMOUS",
        "object_name": None, "limitations": [],
    }


class DisclosureCandidateTests(unittest.TestCase):
    def test_anonymous_relationship_and_kpi_keep_direct_citations(self):
        candidate_input = build_candidate_input(
            [disclosure()], security_id="US:COMMON_STOCK:TEST",
            decision_cutoff="2026-09-12T00:00:00Z", batch_id="batch-1",
        )
        output = build_candidate_output(candidate_input, claims=[relationship_claim(), {
            "claim_id": "claim-2", "claim_type": "KPI", "text": "Users reached 10 million.",
            "evidence_id": "ev-sec-text-1", "source_quote": "Product users reached 10 million",
            "relationship_basis": None, "anonymity_status": "NOT_APPLICABLE",
            "object_name": None, "limitations": [],
        }])
        self.assertEqual(output["claims"][0]["object_name"], None)

    def test_peer_candidate_no_citation_and_named_anonymous_claim_fail(self):
        candidate_input = build_candidate_input(
            [disclosure()], security_id="US:COMMON_STOCK:TEST",
            decision_cutoff="2026-09-12T00:00:00Z", batch_id="batch-1",
        )
        for mutation, message in (
            ({"relationship_basis": "PEER_CANDIDATE_ONLY"}, "RELATIONSHIP_BASIS_INVALID"),
            ({"evidence_id": "missing"}, "CITATION_INVALID"),
            ({"object_name": "Invented Customer"}, "ANONYMITY_VIOLATION"),
        ):
            claim = relationship_claim()
            claim.update(mutation)
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, message):
                build_candidate_output(candidate_input, claims=[claim])

    def test_truncated_source_requires_explicit_limitation(self):
        candidate_input = build_candidate_input(
            [disclosure(truncated=True)], security_id="US:COMMON_STOCK:TEST",
            decision_cutoff="2026-09-12T00:00:00Z", batch_id="batch-1",
        )
        with self.assertRaisesRegex(ValueError, "TRUNCATION_UNACKNOWLEDGED"):
            build_candidate_output(candidate_input, claims=[relationship_claim()])
        claim = deepcopy(relationship_claim())
        claim["limitations"] = ["SOURCE_TRUNCATED"]
        build_candidate_output(candidate_input, claims=[claim])


if __name__ == "__main__":
    unittest.main()
