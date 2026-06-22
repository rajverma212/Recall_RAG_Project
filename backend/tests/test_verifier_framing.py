"""Tests for boilerplate/framing filtering in claim verification.

Ensures pure framing sentences ("Based on the provided context:") are excluded
from verification (no false unsupported claims) while substantive claims —
including uncited ones — are still verified, so detection strength is preserved.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _cite(marker: int, text: str):
    from app.schemas.ask import Citation

    return Citation(
        marker=marker,
        chunk_id=f"c{marker}",
        document_id="doc-1",
        source_file="test.pdf",
        page_number=1,
        section_title=None,
        quote="q",
        text=text,
    )


class TestFramingDetection:
    def test_framing_intro_with_colon_is_framing(self):
        from app.verification.verifier import _is_framing

        assert _is_framing("Based on the provided context:")
        assert _is_framing("Based on the provided context, here are the activities:")
        assert _is_framing("According to the documents:")
        assert _is_framing("Here are the key points:")
        assert _is_framing("In summary:")

    def test_substantive_sentences_are_not_framing(self):
        from app.verification.verifier import _is_framing

        # Long sentence with real factual content (no colon) — must NOT be framing,
        # even if it opens with a framing phrase: it still asserts facts.
        assert not _is_framing(
            "Based on the provided context, the four process activities are "
            "specification, development, validation, and evolution"
        )
        assert not _is_framing("Software validation checks that the system is correct")
        assert not _is_framing("The 401(k) employer match is six percent")


class TestVerifyFiltersFraming:
    def test_framing_claim_excluded_from_verifications(self):
        from app.verification.verifier import verify

        # Framing as its own sentence (period-terminated, as the splitter sees it).
        answer = (
            "Based on the provided context. "
            "The four activities are specification and development [1]."
        )
        cit = _cite(1, "The four process activities are specification and development.")
        verifications, accuracy = verify(answer, [cit])

        claims = [v.claim for v in verifications]
        # The framing intro must not appear as a verified claim.
        assert not any(c.lower().startswith("based on the provided context") for c in claims)
        # The real, cited claim is still verified (and is the only one).
        assert len(verifications) == 1
        assert "[1]" in verifications[0].claim
        assert 0.0 <= accuracy <= 1.0

    def test_uncited_factual_claim_still_unsupported(self):
        """Verification strength preserved: a real uncited claim is still flagged."""
        from app.verification.verifier import verify

        answer = "The system uses a proprietary GPU cluster for training."
        cit = _cite(1, "unrelated text about leave policy")
        verifications, _ = verify(answer, [cit])

        assert len(verifications) == 1
        assert verifications[0].status == "unsupported"

    def test_list_items_keep_their_citations(self):
        """A lead sentence + markdown list must not lose citations to splitting.

        Reproduces the real bug: '...evolution. [1]\\n- item. [1]\\n- item.' —
        the splitter detaches each '[1]' onto the next fragment. After the fix
        every factual claim should retain a citation and be verified (not a
        false 'unsupported' / 'No citation markers' fragment).
        """
        from app.verification.verifier import verify

        answer = (
            "The four activities are specification, development, validation, and evolution. [1]\n"
            "- Specification defines what the system should do. [1]\n"
            "- Development designs and programs the system. [1]\n"
            "- Validation checks the system is correct. [1]"
        )
        cit = _cite(
            1,
            "The four process activities are specification, development, validation, "
            "and evolution. Specification defines what the system should do. Development "
            "designs and programs the system. Validation checks the system is correct.",
        )
        verifications, accuracy = verify(answer, [cit])

        # No claim should be dropped for 'No citation markers'.
        no_cite = [v for v in verifications if not v.cited_markers]
        assert no_cite == [], f"claims lost their citation: {[v.claim for v in no_cite]}"
        # No bare marker/number fragments leaked through as claims.
        assert all(v.claim.strip() not in ("[1]", "-", "[1].") for v in verifications)
        assert accuracy > 0.5

    def test_list_lead_in_not_flagged(self):
        """An uncited colon lead-in ('The activities are:') is not a claim."""
        from app.verification.verifier import _is_lead_in, verify

        assert _is_lead_in("The four activities are:")
        assert _is_lead_in("The four activities are:\n\n1.")  # stray list number
        assert not _is_lead_in("The four activities are specification and evolution.")

        answer = (
            "The four activities are:\n"
            "1. Specification defines the system. [1]\n"
            "2. Validation checks the system. [1]"
        )
        cit = _cite(1, "Specification defines the system. Validation checks the system.")
        verifications, _ = verify(answer, [cit])
        assert not any(v.claim.rstrip().endswith(":") for v in verifications)
        assert not any(not v.cited_markers for v in verifications)

    def test_framing_only_answer_is_vacuously_accurate(self):
        from app.verification.verifier import verify

        answer = "Based on the provided context:"
        verifications, accuracy = verify(answer, [_cite(1, "text")])
        assert verifications == []
        assert accuracy == 1.0
