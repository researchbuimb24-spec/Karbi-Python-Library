"""
Data Models for Karbi Book Library Subsystem (`karbi.books.models`)
===================================================================

Type-annotated models representing books, passages, translation alignments,
vocabulary candidates, and import manifests.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class BookImportStatus(str, Enum):
    """Import lifecycle status for a book in the catalogue."""
    CATALOG_ONLY = "CATALOG_ONLY"
    PARTIALLY_IMPORTED = "PARTIALLY_IMPORTED"
    FULLY_IMPORTED = "FULLY_IMPORTED"


class PassageProvenanceStatus(str, Enum):
    """Provenance and review status for an individual passage."""
    UNVERIFIED = "UNVERIFIED"
    SOURCE_ATTESTED = "SOURCE_ATTESTED"
    COMMUNITY_REVIEWED = "COMMUNITY_REVIEWED"
    VERIFIED = "VERIFIED"


class TranslationType(str, Enum):
    """Provenance category for a translation record."""
    ORIGINAL_SOURCE = "original_source"
    PUBLISHED_TRANSLATION = "published_translation"
    LEXICON_CANDIDATE = "lexicon_candidate"
    MACHINE_DRAFT = "machine_draft"
    UNVERIFIED = "unverified"
    COMMUNITY_REVIEWED = "community_reviewed"
    VERIFIED = "verified"
    CITATION_MISMATCH = "citation_mismatch"


class CandidateStatus(str, Enum):
    """Lifecycle status for a vocabulary candidate extracted from books."""
    EXTRACTED = "EXTRACTED"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass
class BookMetadata:
    """
    Comprehensive bibliographic and rights metadata for a book in the catalogue.
    """
    book_id: str
    canonical_title: str
    alternate_titles: Dict[str, str] = field(default_factory=dict)
    author: Optional[str] = None
    original_language: str = "en"
    original_script: str = "latin"
    translator: Optional[str] = None
    editor: Optional[str] = None
    edition: Optional[str] = None
    publisher: Optional[str] = None
    publication_year: Optional[int] = None
    document_type: str = "prose"  # epic, philosophy, fable, folklore, hymn, poetry, drama, grammar, treatise
    volume: Optional[str] = None
    source_id: Optional[str] = None
    source_title: Optional[str] = None
    source_url: Optional[str] = None
    access_date: Optional[str] = None
    copyright_status: str = "public_domain"  # public_domain, open_access, all_rights_reserved, unknown
    licence: str = "Public Domain"
    permitted_reuse: str = "unrestricted_noncommercial_and_commercial"
    attribution_requirements: str = "Scholarly citation"
    redistribution_restrictions: str = "none"
    import_status: str = BookImportStatus.CATALOG_ONLY.value
    imported_chapters_count: int = 0
    imported_passages_count: int = 0
    content_checksum: Optional[str] = None
    import_timestamp: Optional[str] = None
    text_path: Optional[str] = None
    notes: Optional[str] = None
    missing_sections: List[str] = field(default_factory=list)
    extra_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes metadata to a standard dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BookMetadata:
        """Constructs a BookMetadata object from dictionary data."""
        # Extract known fields, passing extras into extra_metadata
        known_keys = {
            "book_id", "canonical_title", "alternate_titles", "author",
            "original_language", "original_script", "translator", "editor",
            "edition", "publisher", "publication_year", "document_type",
            "volume", "source_id", "source_title", "source_url", "access_date",
            "copyright_status", "licence", "permitted_reuse",
            "attribution_requirements", "redistribution_restrictions",
            "import_status", "imported_chapters_count", "imported_passages_count",
            "content_checksum", "import_timestamp", "text_path", "notes",
            "missing_sections", "extra_metadata",
        }
        filtered = {k: v for k, v in data.items() if k in known_keys}
        extras = {k: v for k, v in data.items() if k not in known_keys}
        if extras and "extra_metadata" not in filtered:
            filtered["extra_metadata"] = extras
        elif extras:
            filtered["extra_metadata"] = {**filtered.get("extra_metadata", {}), **extras}
        return cls(**filtered)


@dataclass
class Passage:
    """
    An individual passage (verse, paragraph, stanza, dialogue turn) within a book.
    """
    passage_id: str
    book_id: str = ""
    language: str = "en"
    sequence_number: int = 1
    text: str = ""
    chapter_number: Optional[int] = None
    chapter_title: Optional[str] = None
    section: Optional[str] = None
    verse: Optional[int] = None
    paragraph: Optional[int] = None
    source_reference: Optional[str] = None
    provenance_status: str = PassageProvenanceStatus.SOURCE_ATTESTED.value
    translation_links: Dict[str, str] = field(default_factory=dict)
    notes: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the passage to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Passage:
        """Constructs a Passage from a dictionary."""
        known_keys = {
            "passage_id", "book_id", "language", "sequence_number", "text",
            "chapter_number", "chapter_title", "section", "verse", "paragraph",
            "source_reference", "provenance_status", "translation_links",
            "notes", "metadata"
        }
        filtered = {k: v for k, v in data.items() if k in known_keys}
        extras = {k: v for k, v in data.items() if k not in known_keys}
        if extras:
            filtered["metadata"] = {**filtered.get("metadata", {}), **extras}
        if "passage_id" not in filtered:
            filtered["passage_id"] = str(filtered.get("sequence_number", 1))
        return cls(**filtered)



@dataclass
class TranslationRecord:
    """
    Passage-level translation alignment record supporting bidirectional translation.
    """
    translation_id: str
    source_passage_id: str
    source_language: str
    target_language: str
    translated_text: str
    target_passage_id: Optional[str] = None
    translation_type: str = TranslationType.PUBLISHED_TRANSLATION.value
    translator: Optional[str] = None
    reviewer_id: Optional[str] = None
    review_status: str = "UNVERIFIED"
    source_citation: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the translation record to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TranslationRecord:
        """Constructs a TranslationRecord from a dictionary."""
        known_keys = {
            "translation_id", "source_passage_id", "source_language",
            "target_language", "translated_text", "target_passage_id",
            "translation_type", "translator", "reviewer_id", "review_status",
            "source_citation", "notes",
        }
        return cls(**{k: v for k, v in data.items() if k in known_keys})


@dataclass
class VocabularyCandidate:
    """
    A vocabulary candidate term extracted from book passages.
    Remains in an unreviewed queue until verified by authorized community reviewers.
    """
    candidate_id: str
    source_passage_id: str
    book_id: str
    source_term: str
    source_language: str
    context_sentence: str
    proposed_karbi_term: Optional[str] = None
    dialect: Optional[str] = None
    status: str = CandidateStatus.EXTRACTED.value
    reviewer_id: Optional[str] = None
    reviewer_notes: Optional[str] = None
    existing_lexicon_entry_id: Optional[str] = None
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the candidate to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VocabularyCandidate:
        """Constructs a VocabularyCandidate from a dictionary."""
        known_keys = {
            "candidate_id", "source_passage_id", "book_id", "source_term",
            "source_language", "context_sentence", "proposed_karbi_term",
            "dialect", "status", "reviewer_id", "reviewer_notes",
            "existing_lexicon_entry_id", "created_at"
        }
        return cls(**{k: v for k, v in data.items() if k in known_keys})


@dataclass
class BookSearchResult:
    """
    Represents a full-text search result within book passages.
    """
    passage_id: str
    book_id: str
    book_title: str
    language: str
    chapter_number: Optional[int]
    chapter_title: Optional[str]
    verse: Optional[int]
    paragraph: Optional[int]
    sequence_number: int
    text: str
    matched_snippet: str
    provenance_status: str
    source_reference: Optional[str] = None
    translations: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the search result to a dictionary."""
        return asdict(self)


@dataclass
class ImportManifest:
    """
    Atomic import manifest recording file provenance, SHA-256 checksum, and statistics.
    """
    book_id: str
    canonical_title: str
    source_file_path: str
    sha256_checksum: str
    total_chapters: int
    total_passages: int
    language: str
    import_timestamp: str
    licence: str
    copyright_status: str
    dry_run: bool = False
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the manifest to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ImportManifest:
        """Constructs an ImportManifest from a dictionary."""
        return cls(**data)
