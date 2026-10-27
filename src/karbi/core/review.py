"""
Community Gloss Review Validation Engine (`karbi.core.review`)
==============================================================

Provides validation and audit routines for community-submitted gloss reviews
and corrections (from CSV templates like `docs/community_gloss_review_template.csv`).

Key Features:
- Validates CSV headers and required review fields.
- Verifies entry ID existence against the registered Karbi lexicon.
- Strictly validates decisions ('accepted', 'corrected', 'rejected', 'awaiting_review').
- Enforces explanations on rejected glosses and correction strings on corrected glosses.
- Enforces valid ISO review dates without allowing future dates.
- Privacy-first: explicitly accommodates pseudonyms and anonymous contributions
  without requiring disclosure of real legal names.
- Flags dialect-sensitive and culturally sensitive entries for appropriate community routing.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
import io
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, TextIO, Union

from karbi.core.models import GlossReviewDecision
from karbi.core.resources import get_resource_paths
from karbi.core.loader import load_jsonl_file

# Supported source languages for translation reviews
VALID_REVIEW_LANGUAGES = {"en", "hi", "as", "bn", "mr", "kha"}

# Maximum review date allowed (matches current system time in October 2026)
MAX_REVIEW_DATE = date(2026, 10, 24)

# Dialect identifiers for flagging
DIALECT_KEYWORDS = {"rongkhang", "chinthong", "amri", "dumrali", "nilip", "plains"}

# Cultural sensitivity keywords for advisory routing
CULTURAL_SENSITIVITY_KEYWORDS = {
    "deity", "deities", "ritual", "rituals", "chomangkan", "arnam", "death",
    "sacred", "sacrifice", "funeral", "taboo", "cremation", "divination"
}

RE_ENTRY_ID = re.compile(r"^KB-LEX-[0-9]{7,}$")
RE_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class CommunityReviewRow:
    """A single validated or audited row from a community review submission."""
    entry_id: str
    source_language: str
    source_word: str
    proposed_karbi_form: str
    proposed_gloss: str
    source_evidence: str
    reviewer_name_or_pseudonym: str
    reviewer_consent_or_attribution: str = "pseudonym"
    dialect_or_community: Optional[str] = None
    decision: str = "awaiting_review"
    correction: Optional[str] = None
    notes: Optional[str] = None
    review_date: str = ""
    line_number: int = 0
    is_culturally_sensitive: bool = False
    is_dialect_sensitive: bool = False

    def as_dict(self) -> Dict[str, Any]:
        """Serializes the review submission row to a dictionary."""
        return {
            "entry_id": self.entry_id,
            "source_language": self.source_language,
            "source_word": self.source_word,
            "proposed_karbi_form": self.proposed_karbi_form,
            "proposed_gloss": self.proposed_gloss,
            "source_evidence": self.source_evidence,
            "reviewer_name_or_pseudonym": self.reviewer_name_or_pseudonym,
            "reviewer_consent_or_attribution": self.reviewer_consent_or_attribution,
            "dialect_or_community": self.dialect_or_community,
            "decision": self.decision,
            "correction": self.correction,
            "notes": self.notes,
            "review_date": self.review_date,
            "line_number": self.line_number,
            "is_culturally_sensitive": self.is_culturally_sensitive,
            "is_dialect_sensitive": self.is_dialect_sensitive,
        }


@dataclass
class CommunityReviewValidationResult:
    """Outcome of validating a community review CSV submission."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    submissions_count: int = 0
    accepted_count: int = 0
    corrected_count: int = 0
    rejected_count: int = 0
    awaiting_review_count: int = 0
    anonymous_or_pseudonym_count: int = 0
    culturally_sensitive_count: int = 0
    dialect_sensitive_count: int = 0
    sample_rows_count: int = 0
    is_empty_template: bool = False
    submissions: List[CommunityReviewRow] = field(default_factory=list)

    def summary(self) -> str:
        """Returns a single-line summary of validation results."""
        status = "PASSED" if self.is_valid else "FAILED"
        if self.is_empty_template:
            return (
                f"Community Review Validation {status}: Header-only template (0 submissions), "
                f"{len(self.errors)} error(s), {len(self.warnings)} advisory warning(s)."
            )
        return (
            f"Community Review Validation {status}: {self.submissions_count} submission(s), "
            f"{len(self.errors)} error(s), {len(self.warnings)} advisory warning(s)."
        )

    def as_dict(self) -> Dict[str, Any]:
        """Serializes validation outcome into a structured dictionary."""
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "submissions_count": self.submissions_count,
            "accepted_count": self.accepted_count,
            "corrected_count": self.corrected_count,
            "rejected_count": self.rejected_count,
            "awaiting_review_count": self.awaiting_review_count,
            "anonymous_or_pseudonym_count": self.anonymous_or_pseudonym_count,
            "culturally_sensitive_count": self.culturally_sensitive_count,
            "dialect_sensitive_count": self.dialect_sensitive_count,
            "sample_rows_count": self.sample_rows_count,
            "is_empty_template": self.is_empty_template,
            "submissions": [s.as_dict() for s in self.submissions],
        }

    def report(self, verbose: bool = False) -> str:
        """Formats a human-readable text audit report."""
        status_text = "PASSED [VALID]" if self.is_valid else "FAILED [INVALID]"
        sub_text = f"{self.submissions_count:>5}"
        if self.is_empty_template:
            sub_text += " (Header-only template)"

        lines = [
            "=" * 70,
            "KARBI COMMUNITY REVIEW SUBMISSION AUDIT REPORT",
            "=" * 70,
            f"Overall Status:         {status_text} (Errors: {len(self.errors)})",
            f"Total Submissions:      {sub_text}",
        ]

        if self.sample_rows_count > 0:
            lines.append(f"Sample / Demo Rows:     {self.sample_rows_count:>5} (Excluded from submission counts)")

        lines.extend([
            "",
            "Review Decisions Breakdown:",
            f"  • Accepted:           {self.accepted_count:>5}",
            f"  • Corrected:          {self.corrected_count:>5}",
            f"  • Rejected:           {self.rejected_count:>5}",
            f"  • Awaiting Review:    {self.awaiting_review_count:>5}",
            "",
            "Privacy & Governance Breakdown:",
            f"  • Anonymous/Pseudonym:{self.anonymous_or_pseudonym_count:>5} (No legal name disclosure forced)",
            f"  • Dialect-Sensitive:  {self.dialect_sensitive_count:>5}",
            f"  • Culturally Sensitive: {self.culturally_sensitive_count:>5}",
        ])

        if self.warnings:
            lines.append("")
            lines.append(f"Advisory Notes & Warnings ({len(self.warnings)}):")
            for w in self.warnings[:15]:
                lines.append(f"  [!] {w}")
            if len(self.warnings) > 15:
                lines.append(f"  ... and {len(self.warnings) - 15} additional warnings.")

        if self.errors:
            lines.append("")
            lines.append(f"Validation Errors ({len(self.errors)}):")
            for idx, err in enumerate(self.errors, start=1):
                lines.append(f"  [{idx}] {err}")

        lines.append("=" * 70)
        return "\n".join(lines)


def _load_canonical_entry_ids() -> Set[str]:
    """Helper to load all known entry IDs from canonical or packaged lexicon files."""
    entry_ids: Set[str] = set()
    try:
        lex_paths, _ = get_resource_paths()
        for lp in lex_paths:
            records, _ = load_jsonl_file(lp, raise_on_error=False)
            for rec in records:
                eid = rec.data.get("id")
                if eid:
                    entry_ids.add(eid)
    except Exception:
        pass
    return entry_ids


def validate_community_review_csv(
    csv_source: Union[str, Path, TextIO],
    known_entry_ids: Optional[Set[str]] = None,
    max_date: Optional[date] = None,
) -> CommunityReviewValidationResult:
    """
    Validates a community gloss review CSV file against the required review schema.

    Args:
        csv_source: Path to CSV file, or an opened TextIO stream.
        known_entry_ids: Optional set of valid lexicon entry IDs. If None,
                         attempts to load them automatically from discovered datasets.
        max_date: Upper bound for review dates (defaults to 2026-10-24).

    Returns:
        CommunityReviewValidationResult containing validation status, errors, warnings,
        and processed review rows.
    """
    errors: List[str] = []
    warnings: List[str] = []
    submissions: List[CommunityReviewRow] = []

    cutoff_date = max_date or MAX_REVIEW_DATE
    valid_ids = known_entry_ids if known_entry_ids is not None else _load_canonical_entry_ids()

    # Open file if path was provided
    f_handle: TextIO
    should_close = False
    if isinstance(csv_source, (str, Path)):
        p = Path(csv_source)
        if not p.is_file():
            return CommunityReviewValidationResult(
                is_valid=False,
                errors=[f"Review CSV file not found: '{csv_source}'"],
            )
        try:
            f_handle = open(p, "r", encoding="utf-8-sig", newline="")
            should_close = True
        except Exception as e:
            return CommunityReviewValidationResult(
                is_valid=False,
                errors=[f"Cannot open review CSV file '{csv_source}': {e}"],
            )
    else:
        f_handle = csv_source

    try:
        reader = csv.reader(f_handle)
        # Find header row, skipping any comment lines or empty rows before it
        header_row = None
        for candidate_header in reader:
            if candidate_header and any(h.strip() for h in candidate_header):
                if candidate_header[0].strip().startswith("#"):
                    continue
                header_row = candidate_header
                break

        if header_row is None:
            return CommunityReviewValidationResult(
                is_valid=False,
                errors=["Review CSV file is completely empty."],
            )

        headers = [h.strip().lower() for h in header_row]

        # Check required columns
        required_cols = {"entry_id", "source_language", "decision", "review_date"}
        missing_cols = required_cols - set(headers)
        if missing_cols:
            return CommunityReviewValidationResult(
                is_valid=False,
                errors=[f"Review CSV missing mandatory column(s): {', '.join(sorted(missing_cols))}"],
            )

        col_map = {name: idx for idx, name in enumerate(headers)}

        accepted_cnt = 0
        corrected_cnt = 0
        rejected_cnt = 0
        awaiting_cnt = 0
        anon_cnt = 0
        cult_cnt = 0
        dial_cnt = 0
        sample_cnt = 0

        for line_num, row in enumerate(reader, start=2):
            if not row or not any(field.strip() for field in row):
                continue

            first_cell = row[0].strip() if row else ""
            # Check if this row is an illustrative sample or commented out demonstration.
            # Restricted strictly to the first column (entry_id) so descriptive text
            # in notes or evidence (e.g. 'Audio sample: Speaker from Rongkhang') is not discarded.
            first_upper = first_cell.upper()
            is_sample = (
                first_cell.startswith("#")
                or first_upper.startswith("[SAMPLE]")
                or first_upper.startswith("SAMPLE:")
                or first_upper in ("SAMPLE", "[SAMPLE]", "EXAMPLE", "DEMO")
            )
            if is_sample:
                sample_cnt += 1
                continue

            def get_col(col_name: str, default: str = "") -> str:
                idx = col_map.get(col_name)
                if idx is not None and idx < len(row):
                    return row[idx].strip()
                return default

            entry_id = get_col("entry_id")
            src_lang = get_col("source_language").lower()
            src_word = get_col("source_word")
            karbi_form = get_col("proposed_karbi_form")
            gloss = get_col("proposed_gloss")
            evidence = get_col("source_evidence")
            reviewer = get_col("reviewer_name_or_pseudonym")
            attribution = get_col("reviewer_consent_or_attribution") or get_col("attribution_preference") or "pseudonym"
            dialect = get_col("dialect_or_community")
            decision = get_col("decision").lower()
            correction = get_col("correction")
            notes = get_col("notes")
            rev_date = get_col("review_date")

            # 1. Entry ID Validation
            if not entry_id:
                errors.append(f"Line {line_num}: missing mandatory 'entry_id'.")
            elif not RE_ENTRY_ID.match(entry_id):
                errors.append(f"Line {line_num}: invalid entry_id format '{entry_id}'. Expected pattern '^KB-LEX-[0-9]{{7,}}$'.")
            elif valid_ids and entry_id not in valid_ids:
                errors.append(f"Line {line_num}: entry_id '{entry_id}' does not exist in the registered lexicon.")

            # 2. Source Language Validation
            if not src_lang:
                errors.append(f"Line {line_num}: missing mandatory 'source_language'.")
            elif src_lang not in VALID_REVIEW_LANGUAGES:
                errors.append(
                    f"Line {line_num}: unsupported source_language '{src_lang}'. "
                    f"Allowed: {', '.join(sorted(VALID_REVIEW_LANGUAGES))}."
                )

            # 3. Decision Validation
            allowed_decisions = {d.value for d in GlossReviewDecision}
            if not decision:
                errors.append(f"Line {line_num}: missing 'decision'.")
            elif decision not in allowed_decisions:
                errors.append(
                    f"Line {line_num}: invalid decision '{decision}'. "
                    f"Allowed: {', '.join(sorted(allowed_decisions))}."
                )

            if decision == GlossReviewDecision.CORRECTED.value:
                corrected_cnt += 1
                if not correction:
                    errors.append(f"Line {line_num}: decision is 'corrected' but 'correction' column is empty.")
            elif decision == GlossReviewDecision.REJECTED.value:
                rejected_cnt += 1
                if not notes:
                    errors.append(f"Line {line_num}: decision is 'rejected' but 'notes' column is empty. Must provide reasoning.")
            elif decision == GlossReviewDecision.ACCEPTED.value:
                accepted_cnt += 1
            elif decision == GlossReviewDecision.AWAITING_REVIEW.value:
                awaiting_cnt += 1

            # 4. Review Date Validation
            if not rev_date:
                errors.append(f"Line {line_num}: missing mandatory 'review_date'.")
            elif not RE_ISO_DATE.match(rev_date):
                errors.append(f"Line {line_num}: invalid review_date format '{rev_date}'. Must be ISO-8601 (YYYY-MM-DD).")
            else:
                try:
                    parts = [int(p) for p in rev_date.split("-")]
                    parsed_date = date(parts[0], parts[1], parts[2])
                    if parsed_date > cutoff_date:
                        errors.append(f"Line {line_num}: review_date '{rev_date}' is in the future (max allowed: {cutoff_date}).")
                except ValueError as ve:
                    errors.append(f"Line {line_num}: malformed calendar date '{rev_date}': {ve}")

            # 5. Privacy and Attribution Verification
            lower_attr = attribution.lower()
            lower_rev = reviewer.lower()
            is_anon = any(k in lower_attr or k in lower_rev for k in ("anon", "pseudonym", "elder", "community"))
            if is_anon or not reviewer:
                anon_cnt += 1

            # 6. Dialect and Cultural Sensitivity Flagging
            is_dial = False
            if dialect:
                is_dial = True
            elif any(k in (notes or "").lower() or k in (evidence or "").lower() for k in DIALECT_KEYWORDS):
                is_dial = True

            if is_dial:
                dial_cnt += 1
                warnings.append(
                    f"Line {line_num} (Entry '{entry_id}'): Dialect-sensitive contribution ({dialect or 'regional variation'}). "
                    f"Ensure maintainers record variety label in dialect metadata."
                )

            is_cult = False
            combined_text = f"{gloss} {notes} {evidence}".lower()
            if any(k in combined_text for k in CULTURAL_SENSITIVITY_KEYWORDS):
                is_cult = True
                cult_cnt += 1
                warnings.append(
                    f"Line {line_num} (Entry '{entry_id}'): Culturally sensitive term detected. "
                    f"Maintainers should verify community consultation protocols."
                )

            submissions.append(
                CommunityReviewRow(
                    entry_id=entry_id,
                    source_language=src_lang,
                    source_word=src_word,
                    proposed_karbi_form=karbi_form,
                    proposed_gloss=gloss,
                    source_evidence=evidence,
                    reviewer_name_or_pseudonym=reviewer,
                    reviewer_consent_or_attribution=attribution,
                    dialect_or_community=dialect or None,
                    decision=decision,
                    correction=correction or None,
                    notes=notes or None,
                    review_date=rev_date,
                    line_number=line_num,
                    is_culturally_sensitive=is_cult,
                    is_dialect_sensitive=is_dial,
                )
            )

        is_valid = len(errors) == 0
        is_empty_template = is_valid and (len(submissions) == 0)
        return CommunityReviewValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            submissions_count=len(submissions),
            accepted_count=accepted_cnt,
            corrected_count=corrected_cnt,
            rejected_count=rejected_cnt,
            awaiting_review_count=awaiting_cnt,
            anonymous_or_pseudonym_count=anon_cnt,
            culturally_sensitive_count=cult_cnt,
            dialect_sensitive_count=dial_cnt,
            sample_rows_count=sample_cnt,
            is_empty_template=is_empty_template,
            submissions=submissions,
        )
    finally:
        if should_close:
            try:
                f_handle.close()
            except Exception:
                pass


__all__ = [
    "CommunityReviewRow",
    "CommunityReviewValidationResult",
    "validate_community_review_csv",
]
