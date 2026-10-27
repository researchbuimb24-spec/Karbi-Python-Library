"""
Full-Text Search Engine for Book Library (`karbi.books.search`)
==============================================================

Provides Unicode-safe full-text search across book passages and metadata
using SQLite FTS5 with graceful relational fallback.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional, Union
import unicodedata

from karbi.books.catalog import BookCatalog
from karbi.books.importer import get_default_books_dir
from karbi.books.models import BookMetadata, BookSearchResult, Passage
from karbi.core.db import get_db_connection, get_default_db_path


class BookSearchEngine:
    """
    Search engine for book metadata and passage text.
    """

    def __init__(
        self,
        db_path: Optional[Union[str, Path]] = None,
        books_dir: Optional[Union[str, Path]] = None,
        catalog: Optional[BookCatalog] = None,
    ):
        self.db_path = Path(db_path) if db_path is not None else get_default_db_path()
        self.books_dir = Path(books_dir) if books_dir is not None else get_default_books_dir()
        self.catalog = catalog or BookCatalog()

    def search_books(self, query: str) -> List[BookMetadata]:
        """
        Searches book metadata in the catalogue by title, author, translator, or ID.
        """
        clean_q = unicodedata.normalize("NFC", query.strip().lower())
        results: List[BookMetadata] = []
        for book in self.catalog.list_books():
            haystack = [
                book.book_id.lower(),
                book.canonical_title.lower(),
                (book.author or "").lower(),
                (book.translator or "").lower(),
                (book.editor or "").lower(),
                (book.notes or "").lower(),
                book.document_type.lower(),
            ]
            for alt in book.alternate_titles.values():
                haystack.append(alt.lower())

            if any(clean_q in text for text in haystack):
                results.append(book)
        return results

    def search_book_text(
        self,
        query: str,
        book_id: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[BookSearchResult]:
        """
        Performs full-text search across book passages.
        Uses FTS5 virtual table where available, with relational fallback.
        """
        clean_q = unicodedata.normalize("NFC", query.strip())
        if not clean_q:
            return []

        results: List[BookSearchResult] = []

        if self.db_path.is_file():
            try:
                conn = get_db_connection(self.db_path)
                cur = conn.cursor()

                # Try FTS5 first
                fts_query = """
                    SELECT p.passage_id, p.book_id, b.canonical_title, p.language,
                           p.chapter_number, p.chapter_title, p.verse, p.paragraph,
                           p.sequence_number, p.text, p.source_reference,
                           p.provenance_status, p.translation_links_json
                    FROM fts_passages f
                    JOIN book_passages p ON f.passage_id = p.passage_id
                    JOIN books b ON p.book_id = b.book_id
                    WHERE fts_passages MATCH ?
                """
                params: List[Any] = [self._sanitize_fts_query(clean_q)]

                if book_id:
                    fts_query += " AND p.book_id = ?"
                    params.append(book_id)
                if language:
                    fts_query += " AND p.language = ?"
                    params.append(language)

                fts_query += " ORDER BY rank LIMIT ? OFFSET ?"
                params.extend([limit, offset])

                cur.execute(fts_query, params)
                rows = cur.fetchall()

                for r in rows:
                    trans_map = {}
                    if r["translation_links_json"]:
                        try:
                            trans_map = json.loads(r["translation_links_json"])
                        except Exception:
                            pass
                    results.append(
                        BookSearchResult(
                            passage_id=r["passage_id"],
                            book_id=r["book_id"],
                            book_title=r["canonical_title"],
                            language=r["language"],
                            chapter_number=r["chapter_number"],
                            chapter_title=r["chapter_title"],
                            verse=r["verse"],
                            paragraph=r["paragraph"],
                            sequence_number=r["sequence_number"],
                            text=r["text"],
                            matched_snippet=self._extract_snippet(r["text"], clean_q),
                            provenance_status=r["provenance_status"],
                            source_reference=r["source_reference"],
                            translations=trans_map,
                        )
                    )
                conn.close()
                if results:
                    return results

            except sqlite3.OperationalError:
                # FTS query syntax error or FTS5 disabled; fallback to LIKE
                pass
            except Exception:
                pass

        # Relational / JSONL fallback
        return self._search_fallback(clean_q, book_id=book_id, language=language, limit=limit, offset=offset)

    def _sanitize_fts_query(self, query: str) -> str:
        """Sanitizes user input query for FTS5 syntax."""
        cleaned = re.sub(r'[^\w\s"\'\-]', " ", query)
        terms = [t for t in cleaned.split() if t]
        if not terms:
            return f'"{query}"'
        # Treat multiple terms as phrase or AND query
        return " AND ".join(f'"{t}"' for t in terms)

    def _extract_snippet(self, text: str, query: str, context_chars: int = 100) -> str:
        """Extracts a focused text snippet surrounding the matched query term."""
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        match = pattern.search(text)
        if not match:
            return text[: context_chars * 2] + ("..." if len(text) > context_chars * 2 else "")

        start = max(0, match.start() - context_chars)
        end = min(len(text), match.end() + context_chars)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(text) else ""
        return f"{prefix}{text[start:end].strip()}{suffix}"

    def _search_fallback(
        self,
        query: str,
        book_id: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[BookSearchResult]:
        """Relational fallback search using SQL LIKE or streaming JSONL."""
        results: List[BookSearchResult] = []
        if self.db_path.is_file():
            try:
                conn = get_db_connection(self.db_path)
                cur = conn.cursor()
                sql = """
                    SELECT p.passage_id, p.book_id, b.canonical_title, p.language,
                           p.chapter_number, p.chapter_title, p.verse, p.paragraph,
                           p.sequence_number, p.text, p.source_reference,
                           p.provenance_status, p.translation_links_json
                    FROM book_passages p
                    JOIN books b ON p.book_id = b.book_id
                    WHERE p.text LIKE ?
                """
                params: List[Any] = [f"%{query}%"]
                if book_id:
                    sql += " AND p.book_id = ?"
                    params.append(book_id)
                if language:
                    sql += " AND p.language = ?"
                    params.append(language)
                sql += " ORDER BY p.sequence_number ASC LIMIT ? OFFSET ?"
                params.extend([limit, offset])

                cur.execute(sql, params)
                rows = cur.fetchall()
                conn.close()
                for r in rows:
                    trans_map = {}
                    if r["translation_links_json"]:
                        try:
                            trans_map = json.loads(r["translation_links_json"])
                        except Exception:
                            pass
                    results.append(
                        BookSearchResult(
                            passage_id=r["passage_id"],
                            book_id=r["book_id"],
                            book_title=r["canonical_title"],
                            language=r["language"],
                            chapter_number=r["chapter_number"],
                            chapter_title=r["chapter_title"],
                            verse=r["verse"],
                            paragraph=r["paragraph"],
                            sequence_number=r["sequence_number"],
                            text=r["text"],
                            matched_snippet=self._extract_snippet(r["text"], query),
                            provenance_status=r["provenance_status"],
                            source_reference=r["source_reference"],
                            translations=trans_map,
                        )
                    )
                return results
            except Exception:
                pass
        return results
