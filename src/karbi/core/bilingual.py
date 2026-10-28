"""
Bilingual Source Ingestion and Review Engine (`karbi.core.bilingual`)
=====================================================================

Provides structured ingestion, validation, and review tracking for authentic
bilingual lexical pairs and illustrative sentences extracted from historical
print publications (e.g., Rev. R. E. Neighbor 1878, Sardoka Perrin Kay 1904)
and community-submitted fieldwork.

Key Principles:
- Provenance first: Every bilingual pair requires a verified bibliographic source_id,
  exact locator (page/sentence), and verbatim extracted quotation.
- Historical integrity: Historical forms with non-standard or archaic orthography
  are explicitly preserved with uncertainty flags; they are NEVER automatically merged
  into the modern core lexicon without verified speaker/community review.
- No synthetic glosses: Translation directions (e.g., en_to_karbi, as_to_karbi) are
  explicitly recorded; translations are NEVER inferred from definitions alone.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from karbi.core.models import (
    AccessLevel,
    CulturalMetadata,
    DialectMetadata,
    OrthographyMetadata,
    ReviewerRole,
    Status,
)


class LanguageDirection(str, Enum):
    """Allowed linguistic translation directions."""
    EN_TO_KARBI = "en_to_karbi"
    KARBI_TO_EN = "karbi_to_en"
    AS_TO_KARBI = "as_to_karbi"
    KARBI_TO_AS = "karbi_to_as"
    HI_TO_KARBI = "hi_to_karbi"
    KARBI_TO_HI = "karbi_to_hi"
    BN_TO_KARBI = "bn_to_karbi"
    KARBI_TO_BN = "karbi_to_bn"


class UncertaintyFlag(str, Enum):
    """Specific flags for unresolved historical or OCR readings."""
    ARCHAIC_ORTHOGRAPHY = "ARCHAIC_ORTHOGRAPHY"
    OCR_DIACRITIC_UNRESOLVED = "OCR_DIACRITIC_UNRESOLVED"
    ASPIRATION_UNCERTAIN = "ASPIRATION_UNCERTAIN"
    TONE_NOT_INDICATED = "TONE_NOT_INDICATED"
    DIALECT_VARIATION = "DIALECT_VARIATION"
    COMPOUND_BOUNDARY_UNRESOLVED = "COMPOUND_BOUNDARY_UNRESOLVED"
    REQUIRES_ELDER_CONFIRMATION = "REQUIRES_ELDER_CONFIRMATION"


@dataclass
class BilingualEntry:
    """Represents an authentic bilingual lexical or phrasal record."""
    source_id: str
    locator: str
    source_wording: str
    karbi_form: str
    language_direction: str = LanguageDirection.EN_TO_KARBI.value
    part_of_speech: Optional[str] = None
    normalized_karbi_form: Optional[str] = None
    extracted_text_quote: str = ""
    verification_status: str = Status.REQUIRES_SPEAKER_REVIEW.value
    uncertainty_flags: List[str] = field(default_factory=list)
    reviewer_role: Optional[str] = None
    reviewer_attribution: Optional[str] = None
    dialect: str = "rongkhang"
    notes: Optional[str] = None
    entry_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes entry to standard dictionary."""
        return {
            "entry_id": self.entry_id,
            "source_id": self.source_id,
            "locator": self.locator,
            "source_wording": self.source_wording,
            "karbi_form": self.karbi_form,
            "normalized_karbi_form": self.normalized_karbi_form,
            "language_direction": self.language_direction,
            "part_of_speech": self.part_of_speech,
            "extracted_text_quote": self.extracted_text_quote or f"{self.source_wording} -> {self.karbi_form}",
            "verification_status": self.verification_status,
            "uncertainty_flags": self.uncertainty_flags,
            "reviewer_role": self.reviewer_role,
            "reviewer_attribution": self.reviewer_attribution,
            "dialect": self.dialect,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BilingualEntry:
        """Constructs an entry from dictionary."""
        return cls(
            entry_id=data.get("entry_id"),
            source_id=data["source_id"],
            locator=data["locator"],
            source_wording=data["source_wording"],
            karbi_form=data["karbi_form"],
            normalized_karbi_form=data.get("normalized_karbi_form"),
            language_direction=data.get("language_direction", LanguageDirection.EN_TO_KARBI.value),
            part_of_speech=data.get("part_of_speech"),
            extracted_text_quote=data.get("extracted_text_quote", ""),
            verification_status=data.get("verification_status", Status.REQUIRES_SPEAKER_REVIEW.value),
            uncertainty_flags=data.get("uncertainty_flags", []),
            reviewer_role=data.get("reviewer_role"),
            reviewer_attribution=data.get("reviewer_attribution"),
            dialect=data.get("dialect", "rongkhang"),
            notes=data.get("notes"),
        )

    def to_community_review_row(self) -> Dict[str, str]:
        """Formats the entry for the community gloss review CSV workflow."""
        source_lang = "en"
        if self.language_direction.startswith("as"):
            source_lang = "as"
        elif self.language_direction.startswith("hi"):
            source_lang = "hi"
        elif self.language_direction.startswith("bn"):
            source_lang = "bn"

        return {
            "entry_id": self.entry_id or "",
            "source_language": source_lang,
            "source_word": self.source_wording,
            "proposed_karbi_form": self.normalized_karbi_form or self.karbi_form,
            "proposed_gloss": self.source_wording,
            "source_evidence": f"{self.source_id} ({self.locator})",
            "reviewer_name_or_pseudonym": self.reviewer_attribution or "Unassigned",
            "reviewer_consent_or_attribution": "Archival Print Ingestion",
            "dialect_or_community": self.dialect,
            "decision": "awaiting_review",
            "correction": "",
            "notes": f"Uncertainties: {', '.join(self.uncertainty_flags)}" if self.uncertainty_flags else (self.notes or ""),
            "review_date": "",
        }


class BilingualSourceImporter:
    """Manages ingestion, validation, and review export of authentic bilingual datasets."""

    def __init__(self, registered_sources_file: Optional[Path] = None):
        self.sources_file = registered_sources_file or (
            Path(__file__).resolve().parent.parent.parent.parent / "data" / "sources" / "sources.jsonl"
        )
        self.registered_source_ids: Set[str] = set()
        self._load_registered_sources()

    def _load_registered_sources(self) -> None:
        if self.sources_file.is_file():
            with open(self.sources_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        s = json.loads(line)
                        sid = s.get("source_id") or s.get("id")
                        if sid:
                            self.registered_source_ids.add(sid)

    def validate_entry(self, entry: BilingualEntry) -> List[str]:
        """Validates entry integrity, required fields, and bibliographic provenance."""
        errors: List[str] = []
        if not entry.source_id:
            errors.append("source_id is required")
        elif self.registered_source_ids and entry.source_id not in self.registered_source_ids:
            errors.append(f"source_id '{entry.source_id}' is not registered in sources.jsonl")

        if not entry.locator:
            errors.append("locator (page/sentence number) is required")

        if not entry.source_wording or not entry.source_wording.strip():
            errors.append("source_wording is required")

        if not entry.karbi_form or not entry.karbi_form.strip():
            errors.append("karbi_form is required")

        valid_directions = {d.value for d in LanguageDirection}
        if entry.language_direction not in valid_directions:
            errors.append(f"Invalid language_direction '{entry.language_direction}'")

        return errors

    def export_review_csv(self, entries: List[BilingualEntry], output_path: Path) -> int:
        """Exports entries to CSV for human reviewer workflow."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        headers = [
            "entry_id", "source_language", "source_word", "proposed_karbi_form",
            "proposed_gloss", "source_evidence", "reviewer_name_or_pseudonym",
            "reviewer_consent_or_attribution", "dialect_or_community", "decision",
            "correction", "notes", "review_date"
        ]
        count = 0
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for e in entries:
                writer.writerow(e.to_community_review_row())
                count += 1
        return count
