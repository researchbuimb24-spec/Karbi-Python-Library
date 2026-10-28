"""
Karbi Digital Book Library Subsystem (`karbi.books`)
===================================================

A comprehensive digital book repository for multilingual literature and Karbi
linguistic heritage. Provides structured storage, full-text FTS5 search,
passage streaming, bidirectional translation alignment, and vocabulary candidate
extraction.
"""

from karbi.books.models import (
    BookImportStatus,
    BookMetadata,
    BookSearchResult,
    CandidateStatus,
    ImportManifest,
    Passage,
    PassageProvenanceStatus,
    TranslationRecord,
    TranslationType,
    VocabularyCandidate,
)
from karbi.books.catalog import BookCatalog, get_default_catalog_path
from karbi.books.importer import BookImporter, get_default_books_dir, sync_all_books_to_databases
from karbi.books.reader import BookReader
from karbi.books.search import BookSearchEngine
from karbi.books.audit import BookAuditResult, BookAuditor, LibraryAuditReport
from karbi.books.translation import BOOK_TRANSLATION_LANGUAGES, BookTranslationRepository
from karbi.books.vocabulary import VocabularyCandidateWorkflow

__all__ = [
    # Models
    "BookAuditResult",
    "BookImportStatus",
    "BookMetadata",
    "BookSearchResult",
    "CandidateStatus",
    "ImportManifest",
    "LibraryAuditReport",
    "Passage",
    "PassageProvenanceStatus",
    "TranslationRecord",
    "TranslationType",
    "VocabularyCandidate",
    # Subsystems
    "BookAuditor",
    "BookCatalog",
    "BookImporter",
    "BookReader",
    "BookSearchEngine",
    "BookTranslationRepository",
    "BookValidationResult",
    "VocabularyCandidateWorkflow",
    # Helpers
    "BOOK_TRANSLATION_LANGUAGES",
    "get_default_books_dir",
    "get_default_catalog_path",
    "validate_book",
    "validate_book_catalog",
    "sync_all_books_to_databases",
]
