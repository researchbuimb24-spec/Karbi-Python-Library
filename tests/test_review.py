"""
Tests for Community Review Validation Utility (`karbi.core.review`)
===================================================================

Verifies:
1. Valid submission formats (accepted, corrected, rejected).
2. Enforcement of mandatory headers and columns.
3. Verification of entry IDs against registered lexicon entries.
4. Language code and decision validation rules.
5. Mandatory correction string on 'corrected' decisions.
6. Mandatory explanatory notes on 'rejected' decisions.
7. ISO date validation and rejection of future review dates.
8. Privacy preservation (anonymous/pseudonym attributions supported without legal names).
9. Advisory flagging for dialect-sensitive and culturally sensitive contributions.
10. Handling of empty or missing review files.
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path
import unittest

from karbi.core.review import (
    CommunityReviewRow,
    CommunityReviewValidationResult,
    validate_community_review_csv,
)


class TestCommunityReviewValidation(unittest.TestCase):
    """Test suite for community review CSV validation."""

    def test_canonical_template_passes(self):
        """The distributed template docs/community_gloss_review_template.csv is header-only and valid."""
        template_path = Path(__file__).resolve().parent.parent / "docs" / "community_gloss_review_template.csv"
        res = validate_community_review_csv(template_path)
        self.assertTrue(res.is_valid, f"Expected valid template, got errors: {res.errors}")
        self.assertEqual(res.submissions_count, 0)
        self.assertEqual(res.accepted_count, 0)
        self.assertEqual(res.corrected_count, 0)
        self.assertEqual(res.rejected_count, 0)
        self.assertEqual(len(res.errors), 0)
        self.assertTrue(res.is_empty_template)
        report_text = res.report()
        self.assertIn("PASSED [VALID]", report_text)
        self.assertIn("Total Submissions:          0 (Header-only template)", report_text)

    def test_header_only_empty_template_distinguished(self):
        """Header-only template is valid, has 0 submissions, and is flagged as empty template."""
        csv_data = io.StringIO(
            "entry_id,source_language,source_word,proposed_karbi_form,proposed_gloss,source_evidence,reviewer_name_or_pseudonym,reviewer_consent_or_attribution,dialect_or_community,decision,correction,notes,review_date\n"
        )
        res = validate_community_review_csv(csv_data)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.submissions_count, 0)
        self.assertTrue(res.is_empty_template)
        self.assertIn("Header-only template (0 submissions)", res.summary())

    def test_sample_and_comment_rows_excluded_from_submission_totals(self):
        """Rows marked as samples or prefixed by # are excluded from actual submission totals."""
        csv_data = io.StringIO(
            "# Documentation comments before header\n"
            "entry_id,source_language,source_word,proposed_karbi_form,proposed_gloss,source_evidence,reviewer_name_or_pseudonym,reviewer_consent_or_attribution,dialect_or_community,decision,correction,notes,review_date\n"
            "# Line-level comment\n"
            "#KB-LEX-0000001,hi,मनुष्य,arlèng,मनुष्य,Usage,Reviewer Pseudonym,Pseudonym,Rongkhang,accepted,,,2026-10-23\n"
            "[SAMPLE] KB-LEX-0000001,as,মানুহ,arlèng,মানুহ,Usage,Community Elder,Anonymous,Chinthong,accepted,,,2026-10-23\n"
            "KB-LEX-0000001,en,man,arlèng,man,Oral usage,Rongkhang Speaker,Pseudonym,Rongkhang,accepted,,,2026-10-24\n"
        )
        res = validate_community_review_csv(csv_data, known_entry_ids={"KB-LEX-0000001"})
        self.assertTrue(res.is_valid)
        # Only the 1 genuine submission row is counted
        self.assertEqual(res.submissions_count, 1)
        self.assertEqual(res.accepted_count, 1)
        self.assertEqual(res.sample_rows_count, 3)  # 3 comment/sample rows detected and excluded
        self.assertFalse(res.is_empty_template)
        report = res.report()
        self.assertIn("Total Submissions:          1", report)
        self.assertIn("Sample / Demo Rows:         3 (Excluded from submission counts)", report)

    def test_descriptive_notes_containing_sample_words_not_discarded(self):
        """Legitimate submissions whose notes or evidence contain 'sample:' or 'example' are not discarded."""
        csv_data = io.StringIO(
            "entry_id,source_language,source_word,proposed_karbi_form,proposed_gloss,source_evidence,reviewer_name_or_pseudonym,reviewer_consent_or_attribution,dialect_or_community,decision,correction,notes,review_date\n"
            "KB-LEX-0000001,en,man,arlèng,man,Field recorded example sentence,Speaker A,Pseudonym,Rongkhang,accepted,,Audio sample: Speaker from Rongkhang tape 4,2026-10-24\n"
            "KB-LEX-0000001,hi,मनुष्य,arlèng,मनुष्य,Recorded [sample] from village elder,Speaker B,Anonymous,Chinthong,accepted,,Sample: oral evidence confirmed,2026-10-24\n"
        )
        res = validate_community_review_csv(csv_data, known_entry_ids={"KB-LEX-0000001"})
        self.assertTrue(res.is_valid)
        self.assertEqual(res.submissions_count, 2)
        self.assertEqual(res.sample_rows_count, 0)
        self.assertEqual(res.accepted_count, 2)
        self.assertEqual(len(res.submissions), 2)
        self.assertEqual(res.submissions[0].notes, "Audio sample: Speaker from Rongkhang tape 4")

    def test_explicit_sample_marker_in_entry_id_excluded(self):
        """Rows with explicit sample markers in entry_id column are excluded from submissions and counted as samples."""
        csv_data = io.StringIO(
            "entry_id,source_language,source_word,proposed_karbi_form,proposed_gloss,source_evidence,reviewer_name_or_pseudonym,reviewer_consent_or_attribution,dialect_or_community,decision,correction,notes,review_date\n"
            "[SAMPLE] KB-LEX-0000001,en,man,arlèng,man,Evidence,Reviewer,Pseudonym,Rongkhang,accepted,,,2026-10-24\n"
            "SAMPLE: KB-LEX-0000001,hi,मनुष्य,arlèng,मनुष्य,Evidence,Reviewer,Pseudonym,Rongkhang,accepted,,,2026-10-24\n"
            "EXAMPLE,as,মানুহ,arlèng,মানুহ,Evidence,Reviewer,Pseudonym,Rongkhang,accepted,,,2026-10-24\n"
            "KB-LEX-0000001,en,man,arlèng,man,Legitimate submission,Speaker C,Pseudonym,Rongkhang,accepted,,,2026-10-24\n"
        )
        res = validate_community_review_csv(csv_data, known_entry_ids={"KB-LEX-0000001"})
        self.assertTrue(res.is_valid)
        self.assertEqual(res.submissions_count, 1)
        self.assertEqual(res.sample_rows_count, 3)
        self.assertEqual(res.submissions[0].reviewer_name_or_pseudonym, "Speaker C")

    def test_valid_custom_csv_stream(self):
        """A valid CSV stream with various decisions passes validation."""
        csv_data = io.StringIO(
            "entry_id,source_language,source_word,proposed_karbi_form,proposed_gloss,source_evidence,reviewer_name_or_pseudonym,reviewer_consent_or_attribution,dialect_or_community,decision,correction,notes,review_date\n"
            "KB-LEX-0000001,en,man,arlèng,man,Historical and oral consensus,AnonElder,Anonymous,Rongkhang,accepted,,,2026-10-20\n"
            "KB-LEX-0000002,hi,घर,hèm,घर,Oral usage,Reviewer01,Pseudonym consented,Central,accepted,,,2026-10-22\n"
            "KB-LEX-0000003,as,পানী,làng,পানী,Community usage,SpeakerB,Anonymous,Rongkhang,rejected,,Inaccurate regional context,2026-10-21\n"
        )
        res = validate_community_review_csv(csv_data)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.submissions_count, 3)
        self.assertEqual(res.accepted_count, 2)
        self.assertEqual(res.rejected_count, 1)
        self.assertEqual(res.anonymous_or_pseudonym_count, 3)

    def test_missing_mandatory_headers_fails(self):
        """CSV missing mandatory header columns is immediately rejected."""
        csv_data = io.StringIO("source_language,decision\nen,accepted\n")
        res = validate_community_review_csv(csv_data)
        self.assertFalse(res.is_valid)
        self.assertTrue(any("missing mandatory column" in err.lower() for err in res.errors))

    def test_invalid_entry_id_format_and_unknown_id(self):
        """Entry IDs with invalid syntax or non-existent in the lexicon are rejected."""
        # Bad syntax
        csv_bad_syntax = io.StringIO(
            "entry_id,source_language,decision,review_date\n"
            "INVALID-ID-123,en,accepted,2026-10-20\n"
        )
        res_syntax = validate_community_review_csv(csv_bad_syntax, known_entry_ids={"KB-LEX-0000001"})
        self.assertFalse(res_syntax.is_valid)
        self.assertTrue(any("invalid entry_id format" in err for err in res_syntax.errors))

        # Unknown ID
        csv_unknown = io.StringIO(
            "entry_id,source_language,decision,review_date\n"
            "KB-LEX-9999999,en,accepted,2026-10-20\n"
        )
        res_unknown = validate_community_review_csv(csv_unknown, known_entry_ids={"KB-LEX-0000001"})
        self.assertFalse(res_unknown.is_valid)
        self.assertTrue(any("does not exist in the registered lexicon" in err for err in res_unknown.errors))

    def test_unsupported_source_language_rejected(self):
        """Unsupported language codes are rejected."""
        csv_data = io.StringIO(
            "entry_id,source_language,decision,review_date\n"
            "KB-LEX-0000001,zz,accepted,2026-10-20\n"
        )
        res = validate_community_review_csv(csv_data, known_entry_ids={"KB-LEX-0000001"})
        self.assertFalse(res.is_valid)
        self.assertTrue(any("unsupported source_language" in err for err in res.errors))

    def test_invalid_decision_rejected(self):
        """Decisions not in allowed lifecycle states are rejected."""
        csv_data = io.StringIO(
            "entry_id,source_language,decision,review_date\n"
            "KB-LEX-0000001,en,conjectured,2026-10-20\n"
        )
        res = validate_community_review_csv(csv_data, known_entry_ids={"KB-LEX-0000001"})
        self.assertFalse(res.is_valid)
        self.assertTrue(any("invalid decision" in err for err in res.errors))

    def test_corrected_decision_requires_correction_text(self):
        """A decision of 'corrected' without correction text fails validation."""
        csv_data = io.StringIO(
            "entry_id,source_language,decision,correction,review_date\n"
            "KB-LEX-0000001,en,corrected,,2026-10-20\n"
        )
        res = validate_community_review_csv(csv_data, known_entry_ids={"KB-LEX-0000001"})
        self.assertFalse(res.is_valid)
        self.assertTrue(any("decision is 'corrected' but 'correction' column is empty" in err for err in res.errors))

    def test_rejected_decision_requires_explanatory_notes(self):
        """A decision of 'rejected' without notes explaining the rejection fails validation."""
        csv_data = io.StringIO(
            "entry_id,source_language,decision,notes,review_date\n"
            "KB-LEX-0000001,en,rejected,,2026-10-20\n"
        )
        res = validate_community_review_csv(csv_data, known_entry_ids={"KB-LEX-0000001"})
        self.assertFalse(res.is_valid)
        self.assertTrue(any("decision is 'rejected' but 'notes' column is empty" in err for err in res.errors))

    def test_future_review_date_rejected(self):
        """Reviews with dates in the future are rejected."""
        csv_data = io.StringIO(
            "entry_id,source_language,decision,review_date\n"
            "KB-LEX-0000001,en,accepted,2029-01-01\n"
        )
        res = validate_community_review_csv(
            csv_data,
            known_entry_ids={"KB-LEX-0000001"},
            max_date=date(2026, 10, 24),
        )
        self.assertFalse(res.is_valid)
        self.assertTrue(any("is in the future" in err for err in res.errors))

    def test_invalid_date_format_rejected(self):
        """Dates not in YYYY-MM-DD ISO format are rejected."""
        csv_data = io.StringIO(
            "entry_id,source_language,decision,review_date\n"
            "KB-LEX-0000001,en,accepted,24/10/2026\n"
        )
        res = validate_community_review_csv(csv_data, known_entry_ids={"KB-LEX-0000001"})
        self.assertFalse(res.is_valid)
        self.assertTrue(any("invalid review_date format" in err for err in res.errors))

    def test_cultural_and_dialect_sensitivity_flagging(self):
        """Reviews with cultural terms or dialect variations generate warnings."""
        csv_data = io.StringIO(
            "entry_id,source_language,proposed_gloss,notes,dialect_or_community,decision,review_date\n"
            "KB-LEX-0000001,en,deity sacrificial sacred ceremony,Chomangkan traditional ritual,Amri,accepted,2026-10-20\n"
        )
        res = validate_community_review_csv(csv_data, known_entry_ids={"KB-LEX-0000001"})
        self.assertTrue(res.is_valid)
        self.assertEqual(res.culturally_sensitive_count, 1)
        self.assertEqual(res.dialect_sensitive_count, 1)
        self.assertTrue(any("Culturally sensitive term detected" in w for w in res.warnings))
        self.assertTrue(any("Dialect-sensitive contribution" in w for w in res.warnings))

    def test_nonexistent_file_handling(self):
        """Passing non-existent file path produces a clean error result."""
        res = validate_community_review_csv(Path("nonexistent_path/fake_review.csv"))
        self.assertFalse(res.is_valid)
        self.assertTrue(any("not found" in err.lower() for err in res.errors))

    def test_empty_file_handling(self):
        """Empty file produces an error."""
        csv_data = io.StringIO("")
        res = validate_community_review_csv(csv_data)
        self.assertFalse(res.is_valid)
        self.assertTrue(any("completely empty" in err.lower() for err in res.errors))


if __name__ == "__main__":
    unittest.main()
