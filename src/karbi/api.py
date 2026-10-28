"""
High-Level Public Python API for Karbi Language Library (`karbi.api`)
======================================================================

Provides clean, structured, and reusable Python interfaces for:
- Looking up Karbi words and spelling variants.
- Multilingual-to-Karbi translation (English, Hindi, Assamese, Bengali).
- Unified search returning structured SearchResult objects.
- Filtering unverified translations.
- Convenient batch lookups and translations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Sequence, Union
import unicodedata

from karbi.core.dataset import DatasetValidationResult, validate_dataset_files
from karbi.core.db import DEFAULT_DB_PATH, ensure_database_ready, get_db_connection
from karbi.core.resources import get_resource_paths
from karbi.core.review import (
    CommunityReviewRow,
    CommunityReviewValidationResult,
    validate_community_review_csv,
)
from karbi.dictionary import DictionaryEntry, batch_lookup, lookup, lookup_all
from karbi.translator import (
    SUPPORTED_LANGUAGES,
    TranslationMatch,
    batch_translate,
    get_supported_languages,
    translate,
)


@dataclass
class SearchResult:
    """
    A unified, rich, structured result returned by the Karbi search API.

    Attributes:
        query: The input query string.
        query_type: 'karbi_headword', 'spelling_variant', or 'translation'.
        karbi_lemma: Canonical Karbi headword/lemma.
        part_of_speech: Grammatical category (e.g., 'noun', 'verb').
        meanings: Dictionary mapping language codes to definitions {'en': [...], 'hi': [...], ...}.
        status: Verification status ('SOURCE_ATTESTED', 'VERIFIED', 'unverified', etc.).
        is_verified: True if verified or source-attested, False if unverified.
        phonetics_ipa: IPA pronunciation notation if available.
        source_citation: Primary bibliographic source citation string.
        source_citations: List of all bibliographic evidence citations.
        dialect: Dialect variety (defaults to 'rongkhang').
        spelling_variants: List of known contemporary spelling variants.
        examples: List of usage examples with Karbi text and translations.
        cultural_notes: Cultural context or notes if documented.
        entry_id: Identifier in core lexicon (e.g. 'KB-LEX-0000001').
        matched_language: Language code matched ('karbi', 'en', 'hi', 'as', 'bn').
        raw_entry: Underlying DictionaryEntry if matched from dictionary.
        raw_match: Underlying TranslationMatch if matched from translator.
    """
    query: str
    query_type: str
    karbi_lemma: str
    part_of_speech: str
    meanings: Dict[str, List[str]]
    status: str
    is_verified: bool
    phonetics_ipa: Optional[str] = None
    source_citation: Optional[str] = None
    source_citations: List[str] = field(default_factory=list)
    dialect: str = "rongkhang"
    spelling_variants: List[str] = field(default_factory=list)
    examples: List[Dict[str, Any]] = field(default_factory=list)
    cultural_notes: Optional[str] = None
    entry_id: Optional[str] = None
    matched_language: Optional[str] = None
    provenance: Optional[Dict[str, Any]] = None
    raw_entry: Optional[DictionaryEntry] = None
    raw_match: Optional[TranslationMatch] = None

    def get_meanings(self, lang: str = "en") -> List[str]:
        """Returns definitions for a specific language code."""
        return self.meanings.get(lang, [])

    def as_dict(self) -> Dict[str, Any]:
        """Serializes the search result into a clean Python dictionary."""
        return {
            "query": self.query,
            "query_type": self.query_type,
            "karbi_lemma": self.karbi_lemma,
            "part_of_speech": self.part_of_speech,
            "meanings": self.meanings,
            "status": self.status,
            "is_verified": self.is_verified,
            "phonetics_ipa": self.phonetics_ipa,
            "source_citation": self.source_citation,
            "source_citations": self.source_citations,
            "dialect": self.dialect,
            "spelling_variants": self.spelling_variants,
            "examples": self.examples,
            "cultural_notes": self.cultural_notes,
            "entry_id": self.entry_id,
            "matched_language": self.matched_language,
            "provenance": self.provenance,
        }


def _entry_to_search_result(
    entry: DictionaryEntry,
    query: str,
    verified_only: bool = False,
) -> SearchResult:
    """Converts a DictionaryEntry into a unified SearchResult."""
    variants = entry.get_spelling_variants()
    q_norm = query.strip().lower()

    if q_norm == entry.lemma.strip().lower():
        q_type = "karbi_headword"
    elif any(q_norm == v.lower() for v in variants):
        q_type = "spelling_variant"
    else:
        q_type = "karbi_headword"

    meanings = {
        lang: entry.get_meanings(lang, verified_only=verified_only)
        for lang in ("en", "hi", "as", "bn")
    }

    # Extract part of speech, cultural notes, and examples
    pos = entry.senses[0].get("part_of_speech", "") if entry.senses else ""
    cultural_notes = None
    examples: List[Dict[str, Any]] = []
    for s in entry.senses:
        if not cultural_notes:
            cultural_notes = s.get("cultural_metadata", {}).get("cultural_notes")
        examples.extend(s.get("examples", []))

    is_verified = entry.status in ("SOURCE_ATTESTED", "VERIFIED", "CONFIRMED_FROM_SOURCE")

    return SearchResult(
        query=query,
        query_type=q_type,
        karbi_lemma=entry.lemma,
        part_of_speech=pos,
        meanings=meanings,
        status=entry.status,
        is_verified=is_verified,
        phonetics_ipa=entry.phonetics_ipa,
        source_citation=entry.source_citation,
        source_citations=entry.source_citations,
        dialect=entry.dialect,
        spelling_variants=variants,
        examples=examples,
        cultural_notes=cultural_notes,
        entry_id=entry.entry_id,
        matched_language="karbi",
        provenance=entry.provenance,
        raw_entry=entry,
    )


def _match_to_search_result(
    match: TranslationMatch,
    query: str,
    verified_only: bool = False,
) -> SearchResult:
    """Converts a TranslationMatch into a unified SearchResult."""
    meanings = {
        lang: match.get_definitions(lang, verified_only=verified_only)
        for lang in ("en", "hi", "as", "bn")
    }

    return SearchResult(
        query=query,
        query_type="translation",
        karbi_lemma=match.karbi_lemma,
        part_of_speech=match.part_of_speech,
        meanings=meanings,
        status=match.status,
        is_verified=match.is_verified,
        phonetics_ipa=match.phonetics_ipa,
        source_citation=match.source_citation,
        source_citations=match.source_citations,
        dialect=match.dialect,
        examples=match.examples,
        cultural_notes=match.cultural_notes,
        entry_id=match.entry_id,
        matched_language=match.source_language,
        raw_match=match,
    )


def search(
    query: str,
    lang: str = "auto",
    verified_only: bool = False,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> List[SearchResult]:
    """
    Unified, structured search across the Karbi dictionary and translation indices.

    Supports:
    - Direct Karbi headword lookup (e.g. 'arlèng', 'làng', 'hèm').
    - Modern spelling variants (e.g. 'hem', 'arleng', 'lang').
    - Multilingual translation from English ('en'), Hindi ('hi'), Assamese ('as'), Bengali ('bn').
    - Auto-detection across all languages when lang='auto'.
    - Filtering unverified translations with verified_only=True.

    Args:
        query: Word or phrase to look up.
        lang: Language of the query: 'auto', 'karbi', 'en', 'hi', 'as', 'bn'.
        verified_only: If True, only returns verified entries and glosses.
        db_path: Optional custom path to SQLite database.
        conn: Optional active sqlite3.Connection to reuse.

    Returns:
        List of structured SearchResult objects.
    """
    if query is None or not isinstance(query, str):
        return []
    clean_query = unicodedata.normalize("NFC", query.strip())
    if not clean_query:
        return []

    lang_code = (lang or "auto").strip().lower()

    should_close = False
    if conn is None:
        target_db = ensure_database_ready(db_path)
        conn = get_db_connection(target_db)
        should_close = True

    try:
        results: List[SearchResult] = []
        seen_lemmas: set[str] = set()

        # 1. Explicit Karbi word lookup
        if lang_code == "karbi":
            for entry in lookup_all(clean_query, db_path=db_path, conn=conn):
                if not verified_only or entry.status in ("SOURCE_ATTESTED", "VERIFIED", "CONFIRMED_FROM_SOURCE"):
                    results.append(_entry_to_search_result(entry, clean_query, verified_only=verified_only))
            return results

        # 2. Specific source language translation
        if lang_code in ("en", "hi", "as", "bn"):
            matches = translate(clean_query, from_lang=lang_code, verified_only=verified_only, db_path=db_path, conn=conn)
            for m in matches:
                results.append(_match_to_search_result(m, clean_query, verified_only=verified_only))
            return results

        # 3. Auto-detection / Unified Search
        if lang_code == "auto":
            # Check Karbi dictionary first (if not searching verified-only or if entry is verified)
            for entry in lookup_all(clean_query, db_path=db_path, conn=conn):
                if not verified_only or entry.status in ("SOURCE_ATTESTED", "VERIFIED", "CONFIRMED_FROM_SOURCE"):
                    res = _entry_to_search_result(entry, clean_query, verified_only=verified_only)
                    results.append(res)
                    seen_lemmas.add(entry.lemma.lower())

            # Check translations across active languages
            candidate_langs = ["en", "as", "hi", "bn"]
            for code in candidate_langs:
                matches = translate(clean_query, from_lang=code, verified_only=verified_only, db_path=db_path, conn=conn)
                for m in matches:
                    if m.karbi_lemma.lower() not in seen_lemmas:
                        results.append(_match_to_search_result(m, clean_query, verified_only=verified_only))
                        seen_lemmas.add(m.karbi_lemma.lower())

            return results

        # Unsupported or unknown language code requested
        return []
    finally:
        if should_close:
            try:
                conn.close()
            except Exception:
                pass


def batch_search(
    queries: Sequence[str],
    lang: str = "auto",
    verified_only: bool = False,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, List[SearchResult]]:
    """
    Performs unified search for multiple queries in batch, reusing a single database connection.

    Args:
        queries: Iterable of words or phrases to search.
        lang: Language of the query: 'auto', 'karbi', 'en', 'hi', 'as', 'bn'.
        verified_only: If True, only returns verified entries and glosses.
        db_path: Optional custom path to SQLite database.
        conn: Optional active sqlite3.Connection to reuse.

    Returns:
        Dictionary mapping each query string to its list of SearchResult objects.
    """
    should_close = False
    if conn is None:
        target_db = ensure_database_ready(db_path)
        conn = get_db_connection(target_db)
        should_close = True

    try:
        return {
            q: search(q, lang=lang, verified_only=verified_only, db_path=db_path, conn=conn)
            for q in queries
        }
    finally:
        if should_close:
            try:
                conn.close()
            except Exception:
                pass


def validate_dataset(
    lexicon_path: Optional[Union[str, Path, Sequence[Union[str, Path]]]] = None,
    sources_path: Optional[Union[str, Path, Sequence[Union[str, Path]]]] = None,
    strict: bool = False,
) -> DatasetValidationResult:
    """
    Validates Karbi JSONL dataset files for schema conformity, unique IDs,
    bibliographic source references, and cross-references without silently modifying data.

    Args:
        lexicon_path: Path or sequence of paths to lexicon JSONL file(s).
                      Defaults to the authoritative repository or packaged core lexicon.
        sources_path: Path or sequence of paths to source registry JSONL file(s).
                      Defaults to the authoritative repository or packaged source registry.
        strict: If True, treats unverified glosses as validation errors.

    Returns:
        DatasetValidationResult containing validation status, error messages, and audit metrics.
    """
    default_lex, default_src = get_resource_paths()

    if lexicon_path is None:
        lex_paths = default_lex
    elif isinstance(lexicon_path, (str, Path)):
        lex_paths = [Path(lexicon_path)]
    else:
        lex_paths = [Path(p) for p in lexicon_path]

    if sources_path is None:
        src_paths = default_src
    elif isinstance(sources_path, (str, Path)):
        src_paths = [Path(sources_path)]
    else:
        src_paths = [Path(p) for p in sources_path]

    res = validate_dataset_files(lex_paths, src_paths)
    if strict and res.unverified_glosses_count > 0:
        from karbi.core.dataset import DatasetError

        for lang, count in res.unverified_glosses_by_lang.items():
            res.errors.append(
                DatasetError(
                    message=f"[STRICT] Found {count} unverified gloss(es) in language '{lang}'."
                )
            )
        res.is_valid = False
    return res


# =========================================================================
# Digital Book Library Public API
# =========================================================================

def list_books(
    import_status: Optional[str] = None,
    language: Optional[str] = None,
    document_type: Optional[str] = None,
) -> List[Any]:
    """
    Lists digital books registered in the library catalogue.

    Args:
        import_status: Filter by 'CATALOG_ONLY', 'PARTIALLY_IMPORTED', or 'FULLY_IMPORTED'.
        language: Filter by original language code (e.g. 'sa', 'mjw', 'en').
        document_type: Filter by category (e.g. 'epic', 'philosophy', 'fable', 'folklore').

    Returns:
        List of BookMetadata objects sorted by book_id.
    """
    from karbi.books.catalog import BookCatalog

    cat = BookCatalog()
    return cat.list_books(
        import_status=import_status,
        language=language,
        document_type=document_type,
    )


def get_book(book_id: str) -> Optional[Any]:
    """
    Retrieves full catalogue metadata for a book by its book_id.
    """
    from karbi.books.catalog import BookCatalog

    return BookCatalog().get_book(book_id)


def get_book_metadata(book_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves dictionary-formatted metadata for a book.
    """
    b = get_book(book_id)
    return b.to_dict() if b else None


def get_book_chapters(book_id: str) -> List[Dict[str, Any]]:
    """
    Retrieves chapter list and verse/passage counts for an imported book.
    """
    from karbi.books.reader import BookReader

    return BookReader().get_book_chapters(book_id)


def get_passage(passage_id: str) -> Optional[Any]:
    """
    Retrieves an individual passage by its unique ID (e.g. 'bhagavad_gita:1:1').
    """
    from karbi.books.reader import BookReader

    return BookReader().get_passage(passage_id)


def get_book_passages(
    book_id: str,
    chapter: Optional[int] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> List[Any]:
    """
    Retrieves passages for an imported book with optional chapter filter and pagination.
    """
    from karbi.books.reader import BookReader

    return BookReader().get_book_passages(
        book_id=book_id,
        chapter=chapter,
        limit=limit,
        offset=offset,
    )


def search_books(query: str) -> List[Any]:
    """
    Searches the book catalogue metadata by title, author, translator, or subject.
    """
    from karbi.books.search import BookSearchEngine

    return BookSearchEngine().search_books(query)


def search_book_text(
    query: str,
    book_id: Optional[str] = None,
    language: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> List[Any]:
    """
    Performs full-text search across book passages using SQLite FTS5.

    Args:
        query: Search term or phrase.
        book_id: Optional filter for a specific book ID.
        language: Optional language code filter ('en', 'mjw', 'sa', etc.).
        limit: Max results to return (default: 20).
        offset: Result offset for pagination.

    Returns:
        List of BookSearchResult objects containing snippet, chapter, verse, and text.
    """
    from karbi.books.search import BookSearchEngine

    return BookSearchEngine().search_book_text(
        query=query,
        book_id=book_id,
        language=language,
        limit=limit,
        offset=offset,
    )


def import_book(
    file_path: Union[str, Path],
    metadata: Optional[Any] = None,
    book_id: Optional[str] = None,
    language: str = "en",
    dry_run: bool = False,
    overwrite: bool = False,
) -> Any:
    """
    Imports a book text file (.jsonl, .json, .txt, .md) into the digital library.
    """
    from karbi.books.importer import BookImporter

    importer = BookImporter()
    return importer.import_file(
        file_path=file_path,
        metadata=metadata,
        book_id=book_id,
        language=language,
        dry_run=dry_run,
        overwrite=overwrite,
    )


def validate_book(book_id: str) -> Any:
    """
    Validates integrity, passage sequence, unique IDs, and licensing for a book.
    """
    from karbi.books.validation import validate_book as _vb

    return _vb(book_id)


def get_book_statistics(book_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Retrieves statistical metrics for the book library or a specific book.
    """
    from karbi.books.catalog import BookCatalog

    cat = BookCatalog()
    if book_id:
        b = cat.get_book(book_id)
        if not b:
            return {}
        return {
            "book_id": b.book_id,
            "title": b.canonical_title,
            "status": b.import_status,
            "chapters": b.imported_chapters_count,
            "passages": b.imported_passages_count,
            "checksum": b.content_checksum,
            "licence": b.licence,
        }
    return cat.get_stats()


__all__ = [
    "SearchResult",
    "DatasetValidationResult",
    "search",
    "batch_search",
    "batch_lookup",
    "batch_translate",
    "validate_dataset",
]


def sync_book_databases(
    db_paths: Optional[List[Union[str, Path]]] = None,
    books_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """
    Synchronizes all imported book JSONL text files on disk into SQLite databases and FTS5 indexes.
    Default targets: canonical repo root karbi.db and data/karbi.db.
    """
    from karbi.books.importer import sync_all_books_to_databases
    return sync_all_books_to_databases(db_paths=db_paths, books_dir=books_dir)
