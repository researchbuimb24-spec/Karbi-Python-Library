"""
Batch Dataset Validation for Karbi Language Library (`karbi.core.dataset`)
==========================================================================

Coordinates batch loading and comprehensive validation of lexicon entries
and source records across multiple JSONL files.

Features:
- Global duplicate ID detection (entries, sources, examples, reviews).
- Referential integrity auditing (sources, cross-references).
- Complete error aggregation (discovers all issues in one run without early exit).
- Strict verification and test-fixture rejection enforcement.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from karbi.core.loader import LoadedRecord, load_jsonl_file
from karbi.core.models import ReviewerRegistration, SourceRecord
from karbi.core.validator import LexiconValidator


@dataclass
class DatasetError:
    """Structured error representing a data or schema violation within a dataset."""
    message: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    record_id: Optional[str] = None

    def __str__(self) -> str:
        loc_parts = []
        if self.file_path:
            loc_parts.append(self.file_path)
            if self.line_number is not None:
                loc_parts.append(str(self.line_number))
        loc_str = ":".join(loc_parts)

        prefix = f"[{loc_str}]" if loc_str else "[Dataset]"
        id_str = f" (Record: {self.record_id})" if self.record_id else ""
        return f"{prefix}{id_str} {self.message}"


@dataclass
class DatasetValidationResult:
    """The outcome of a batch dataset validation run."""
    is_valid: bool
    errors: List[DatasetError] = field(default_factory=list)
    lexicon_entries_count: int = 0
    sources_count: int = 0
    files_scanned: List[str] = field(default_factory=list)
    status_counts: Dict[str, int] = field(default_factory=dict)
    missing_citation_entries: List[str] = field(default_factory=list)
    ai_candidate_entries: List[str] = field(default_factory=list)
    unverified_glosses_count: int = 0
    unverified_glosses_by_lang: Dict[str, int] = field(default_factory=dict)
    verified_glosses_count: int = 0
    verified_glosses_by_lang: Dict[str, int] = field(default_factory=dict)
    total_glosses_count: int = 0
    total_glosses_by_lang: Dict[str, int] = field(default_factory=dict)
    citation_mismatch_entries: List[str] = field(default_factory=list)

    def summary(self) -> str:
        status_text = "PASSED" if self.is_valid else "FAILED"
        return (
            f"Dataset Validation {status_text}: "
            f"{self.lexicon_entries_count} entries, {self.sources_count} sources "
            f"across {len(self.files_scanned)} files. Errors: {len(self.errors)}."
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": [
                {
                    "message": e.message,
                    "file_path": e.file_path,
                    "line_number": e.line_number,
                    "record_id": e.record_id,
                }
                for e in self.errors
            ],
            "lexicon_entries_count": self.lexicon_entries_count,
            "sources_count": self.sources_count,
            "files_scanned": self.files_scanned,
            "status_counts": self.status_counts,
            "missing_citation_entries": self.missing_citation_entries,
            "citation_mismatch_entries": self.citation_mismatch_entries,
            "ai_candidate_entries": self.ai_candidate_entries,
            "unverified_glosses_count": self.unverified_glosses_count,
            "unverified_glosses_by_lang": self.unverified_glosses_by_lang,
            "verified_glosses_count": self.verified_glosses_count,
            "verified_glosses_by_lang": self.verified_glosses_by_lang,
            "total_glosses_count": self.total_glosses_count,
            "total_glosses_by_lang": self.total_glosses_by_lang,
        }

    def report(self, verbose: bool = False) -> str:
        lines = [
            "=" * 70,
            "KARBI DATASET VALIDATION & CONTRIBUTOR AUDIT REPORT",
            "=" * 70,
            f"Overall Status:        {'PASSED [VALID]' if self.is_valid else 'FAILED [INVALID]'} (Errors: {len(self.errors)})",
            f"Files Scanned:         {len(self.files_scanned)}",
            f"Sources Registered:    {self.sources_count}",
            f"Lexicon Entries:       {self.lexicon_entries_count}",
            "",
            "Lifecycle Status Breakdown:",
        ]
        for st, count in sorted(self.status_counts.items()):
            lines.append(f"  • {st:<22}: {count:>5} entries")

        lines.append("")
        lines.append("Evidence & Citations:")
        cited_count = self.lexicon_entries_count - len(self.missing_citation_entries)
        pct = (cited_count / self.lexicon_entries_count * 100) if self.lexicon_entries_count > 0 else 0
        lines.append(f"  • Entries with citations:     {cited_count:>5} / {self.lexicon_entries_count} ({pct:.1f}%)")
        lines.append(f"  • Entries missing citations:  {len(self.missing_citation_entries):>5}")
        if self.missing_citation_entries and verbose:
            lines.append(f"    Missing IDs: {', '.join(self.missing_citation_entries[:10])}")

        if self.citation_mismatch_entries:
            lines.append(f"  • Citation-mismatch entries:  {len(self.citation_mismatch_entries):>5}")
            if verbose:
                lines.append(f"    Mismatch IDs: {', '.join(self.citation_mismatch_entries)}")

        lines.append("")
        lines.append("Translation Verification Audit:")
        if self.total_glosses_count > 0:
            lines.append(f"  • Total Definitions/Glosses:  {self.total_glosses_count:>5}")
            ver_pct = (self.verified_glosses_count / self.total_glosses_count * 100)
            lines.append(f"  • Verified Glosses:           {self.verified_glosses_count:>5} ({ver_pct:.1f}%)")
            for l_code in sorted(self.total_glosses_by_lang.keys()):
                v_cnt = self.verified_glosses_by_lang.get(l_code, 0)
                t_cnt = self.total_glosses_by_lang.get(l_code, 0)
                l_pct = (v_cnt / t_cnt * 100) if t_cnt > 0 else 0
                lines.append(f"    - Language '{l_code}':       {v_cnt:>5} / {t_cnt:>5} verified ({l_pct:.1f}%)")
        lines.append(f"  • Total Unverified Glosses:   {self.unverified_glosses_count:>5}")
        for l_code, count in sorted(self.unverified_glosses_by_lang.items()):
            lines.append(f"    - Language '{l_code}':       {count:>5} unverified glosses")

        if self.ai_candidate_entries:
            lines.append("")
            lines.append(f"AI Candidate Entries ({len(self.ai_candidate_entries)}):")
            lines.append(f"  [!] Identified AI candidate entries: {', '.join(self.ai_candidate_entries)}")
            lines.append("  [!] Note: AI candidate entries must remain explicitly unverified until reviewed.")

        if self.errors:
            lines.append("")
            lines.append(f"Validation Errors ({len(self.errors)}):")
            for idx, err in enumerate(self.errors, start=1):
                lines.append(f"  [{idx}] {err}")

        lines.append("=" * 70)
        return "\n".join(lines)


class DatasetValidator:
    """
    Validates collections of JSONL source and lexicon files.
    Gathers all syntax, structural, referential, and verification errors.
    """

    def __init__(
        self,
        reviewer_registry: Optional[Dict[str, ReviewerRegistration]] = None,
    ):
        # Reviewer registry: if None or empty, verification fails closed
        self.reviewer_registry = reviewer_registry

    def validate(
        self,
        lexicon_paths: List[Union[str, Path]],
        source_paths: List[Union[str, Path]],
    ) -> DatasetValidationResult:
        """
        Executes a full batch validation across all specified source and lexicon files.

        All errors are aggregated into the returned result without halting early.
        """
        errors: List[DatasetError] = []
        files_scanned: List[str] = []

        sources_registry: Dict[str, SourceRecord] = {}
        source_id_locations: Dict[str, Tuple[str, int]] = {}

        entry_id_locations: Dict[str, Tuple[str, int]] = {}
        example_id_locations: Dict[str, Tuple[str, int, str]] = {}
        review_id_locations: Dict[str, Tuple[str, int, str]] = {}

        lexicon_records: List[LoadedRecord] = []
        all_entry_ids: Set[str] = set()

        # ---------------------------------------------------------
        # Phase 1: Load and Validate Source Files
        # ---------------------------------------------------------
        for src_path in source_paths:
            path_str = str(src_path)
            files_scanned.append(path_str)

            loaded_src_records, load_errors = load_jsonl_file(src_path, raise_on_error=False)
            for le in load_errors:
                errors.append(DatasetError(message=le, file_path=path_str))

            for rec in loaded_src_records:
                src_data = rec.data
                source_id = src_data.get("source_id")

                # Check duplicate source IDs across files
                if source_id:
                    if source_id in source_id_locations:
                        prev_file, prev_line = source_id_locations[source_id]
                        errors.append(
                            DatasetError(
                                message=(
                                    f"Duplicate source_id '{source_id}' detected. "
                                    f"First defined at {prev_file}:{prev_line}."
                                ),
                                file_path=rec.file_path,
                                line_number=rec.line_number,
                                record_id=source_id,
                            )
                        )
                    else:
                        source_id_locations[source_id] = (rec.file_path, rec.line_number)

                # Validate source record structure
                temp_validator = LexiconValidator()
                src_val_errors = temp_validator.validate_source_record(src_data)
                for sve in src_val_errors:
                    errors.append(
                        DatasetError(
                            message=sve,
                            file_path=rec.file_path,
                            line_number=rec.line_number,
                            record_id=source_id,
                        )
                    )

                if not src_val_errors and source_id:
                    coerced_src = temp_validator._coerce_source(src_data)
                    sources_registry[source_id] = coerced_src

        # ---------------------------------------------------------
        # Phase 2: Load Lexicon Files and Index Entry IDs
        # ---------------------------------------------------------
        for lex_path in lexicon_paths:
            path_str = str(lex_path)
            files_scanned.append(path_str)

            loaded_lex_records, load_errors = load_jsonl_file(lex_path, raise_on_error=False)
            for le in load_errors:
                errors.append(DatasetError(message=le, file_path=path_str))

            for rec in loaded_lex_records:
                lexicon_records.append(rec)
                entry_id = rec.data.get("id")

                if entry_id:
                    if entry_id in entry_id_locations:
                        prev_file, prev_line = entry_id_locations[entry_id]
                        errors.append(
                            DatasetError(
                                message=(
                                    f"Duplicate entry ID '{entry_id}' detected across files. "
                                    f"First defined at {prev_file}:{prev_line}."
                                ),
                                file_path=rec.file_path,
                                line_number=rec.line_number,
                                record_id=entry_id,
                            )
                        )
                    else:
                        entry_id_locations[entry_id] = (rec.file_path, rec.line_number)
                        all_entry_ids.add(entry_id)

        # ---------------------------------------------------------
        # Phase 3: Validate Entries, Examples, Reviews & Evidence
        # ---------------------------------------------------------
        # Instantiate validator with gathered sources and reviewer registry
        validator = LexiconValidator(
            sources_registry=sources_registry,
            reviewer_registry=self.reviewer_registry,
        )

        status_counts: Dict[str, int] = {}
        missing_citation_entries: List[str] = []
        citation_mismatch_entries: List[str] = []
        ai_candidate_entries: List[str] = []
        unverified_glosses_by_lang: Dict[str, int] = {}
        unverified_glosses_count = 0
        verified_glosses_by_lang: Dict[str, int] = {}
        verified_glosses_count = 0
        total_glosses_by_lang: Dict[str, int] = {}
        total_glosses_count = 0

        for rec in lexicon_records:
            entry_data = rec.data
            entry_id = entry_data.get("id") or ""
            status = entry_data.get("status", "DRAFT")
            status_counts[status] = status_counts.get(status, 0) + 1

            if status == "AI_CANDIDATE":
                ai_candidate_entries.append(entry_id)
            elif status == "CITATION_MISMATCH":
                citation_mismatch_entries.append(entry_id)

            prov = entry_data.get("provenance", {})
            evidence = prov.get("evidence_records", []) if isinstance(prov, dict) else []
            if not evidence:
                missing_citation_entries.append(entry_id)

            # Audit definition glosses for verification status
            for sense in entry_data.get("senses", []):
                if isinstance(sense, dict):
                    defs = sense.get("definitions", {})
                    gloss_prov = sense.get("gloss_provenance", {}) or {}
                    for lang_code, items in defs.items():
                        prov_label = str(gloss_prov.get(lang_code, "")).lower()
                        if isinstance(items, list):
                            for item in items:
                                total_glosses_count += 1
                                total_glosses_by_lang[lang_code] = total_glosses_by_lang.get(lang_code, 0) + 1
                                is_ver = False
                                if isinstance(item, dict):
                                    is_ver = item.get("verified", False) is True
                                elif isinstance(item, str):
                                    is_ver = prov_label in ("source_attested", "verified", "peer_reviewed")
                                if is_ver:
                                    verified_glosses_count += 1
                                    verified_glosses_by_lang[lang_code] = verified_glosses_by_lang.get(lang_code, 0) + 1
                                else:
                                    unverified_glosses_count += 1
                                    unverified_glosses_by_lang[lang_code] = unverified_glosses_by_lang.get(lang_code, 0) + 1


        for rec in lexicon_records:
            entry_data = rec.data
            entry_id = entry_data.get("id")

            # Check example ID uniqueness across files
            for s_idx, sense in enumerate(entry_data.get("senses", []), start=1):
                if isinstance(sense, dict):
                    for ex in sense.get("examples", []):
                        if isinstance(ex, dict) and ex.get("example_id"):
                            ex_id = ex["example_id"]
                            if ex_id in example_id_locations:
                                prev_file, prev_line, prev_entry = example_id_locations[ex_id]
                                errors.append(
                                    DatasetError(
                                        message=(
                                            f"Duplicate example_id '{ex_id}' detected. "
                                            f"First defined at {prev_file}:{prev_line} in entry '{prev_entry}'."
                                        ),
                                        file_path=rec.file_path,
                                        line_number=rec.line_number,
                                        record_id=entry_id,
                                    )
                                )
                            else:
                                example_id_locations[ex_id] = (rec.file_path, rec.line_number, entry_id or "")

            # Check review ID uniqueness across files
            prov = entry_data.get("provenance", {})
            if isinstance(prov, dict):
                for rev in prov.get("reviews", []):
                    if isinstance(rev, dict) and rev.get("review_id"):
                        rev_id = rev["review_id"]
                        if rev_id in review_id_locations:
                            prev_file, prev_line, prev_entry = review_id_locations[rev_id]
                            errors.append(
                                DatasetError(
                                    message=(
                                        f"Duplicate review_id '{rev_id}' detected. "
                                        f"First defined at {prev_file}:{prev_line} in entry '{prev_entry}'."
                                    ),
                                    file_path=rec.file_path,
                                    line_number=rec.line_number,
                                    record_id=entry_id,
                                )
                            )
                        else:
                            review_id_locations[rev_id] = (rec.file_path, rec.line_number, entry_id or "")

            # Validate entry structure, schema, enums, verification, fixture rejection
            entry_errors = validator.validate_entry(entry_data, check_cross_refs=False)
            for ee in entry_errors:
                # Avoid re-adding duplicate entry_id error since Phase 2 already reported it with location
                if "Duplicate entry ID detected across dataset" in ee:
                    continue
                errors.append(
                    DatasetError(
                        message=ee,
                        file_path=rec.file_path,
                        line_number=rec.line_number,
                        record_id=entry_id,
                    )
                )

        # ---------------------------------------------------------
        # Phase 4: Referential Integrity for Cross-References
        # ---------------------------------------------------------
        for rec in lexicon_records:
            entry_data = rec.data
            entry_id = entry_data.get("id")
            for xref in entry_data.get("cross_references", []):
                if not isinstance(xref, dict):
                    errors.append(
                        DatasetError(
                            message=f"Cross-reference record must be an object (dict), found '{type(xref).__name__}'.",
                            file_path=rec.file_path,
                            line_number=rec.line_number,
                            record_id=entry_id,
                        )
                    )
                    continue

                raw_target = xref.get("target_entry_id") or xref.get("entry_id")
                if raw_target is None or not str(raw_target).strip():
                    errors.append(
                        DatasetError(
                            message="Cross-reference target ID cannot be empty or missing.",
                            file_path=rec.file_path,
                            line_number=rec.line_number,
                            record_id=entry_id,
                        )
                    )
                else:
                    target_id = str(raw_target).strip()
                    if target_id not in all_entry_ids:
                        errors.append(
                            DatasetError(
                                message=(
                                    f"Cross-reference target '{target_id}' does not exist "
                                    f"anywhere in the dataset."
                                ),
                                file_path=rec.file_path,
                                line_number=rec.line_number,
                                record_id=entry_id,
                            )
                        )

        is_valid = len(errors) == 0
        return DatasetValidationResult(
            is_valid=is_valid,
            errors=errors,
            lexicon_entries_count=len(lexicon_records),
            sources_count=len(sources_registry),
            files_scanned=files_scanned,
            status_counts=status_counts,
            missing_citation_entries=missing_citation_entries,
            citation_mismatch_entries=citation_mismatch_entries,
            ai_candidate_entries=ai_candidate_entries,
            unverified_glosses_count=unverified_glosses_count,
            unverified_glosses_by_lang=unverified_glosses_by_lang,
            verified_glosses_count=verified_glosses_count,
            verified_glosses_by_lang=verified_glosses_by_lang,
            total_glosses_count=total_glosses_count,
            total_glosses_by_lang=total_glosses_by_lang,
        )


def validate_dataset_files(
    lexicon_paths: List[Union[str, Path]],
    source_paths: List[Union[str, Path]],
    reviewer_registry: Optional[Dict[str, ReviewerRegistration]] = None,
) -> DatasetValidationResult:
    """Convenience functional interface to validate dataset files."""
    validator = DatasetValidator(reviewer_registry=reviewer_registry)
    return validator.validate(lexicon_paths=lexicon_paths, source_paths=source_paths)
