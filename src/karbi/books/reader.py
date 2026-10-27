"""
Book and Passage Reader Subsystem (`karbi.books.reader`)
========================================================

Provides passage streaming, pagination, chapter retrieval, and text formatting.
Works offline using SQLite database indexes with streaming JSONL fallback.
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, Iterator, List, Optional, Union

from karbi.books.catalog import BookCatalog
from karbi.books.importer import get_default_books_dir
from karbi.books.models import Passage
from karbi.core.db import get_db_connection, get_default_db_path


class BookReader:
    """
    Retrieves and formats passages and chapters for offline reading and study.
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

    def get_passage(self, passage_id: str) -> Optional[Passage]:
        """
        Retrieves a single passage by its unique passage_id.
        Tries SQLite index first, then JSONL fallback.
        """
        # 1. Try SQLite
        if self.db_path.is_file():
            try:
                conn = get_db_connection(self.db_path)
                cur = conn.cursor()
                cur.execute("SELECT raw_json FROM book_passages WHERE passage_id = ?", (passage_id,))
                row = cur.fetchone()
                conn.close()
                if row:
                    return Passage.from_dict(json.loads(row["raw_json"]))
            except Exception:
                pass

        # 2. Try JSONL fallback if passage_id starts with book_id
        parts = passage_id.split(":")
        book_id = parts[0]
        jsonl_path = self.books_dir / "texts" / f"{book_id}.jsonl"
        if jsonl_path.is_file():
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    rec = json.loads(line)
                    if rec.get("passage_id") == passage_id:
                        return Passage.from_dict(rec)

        return None

    def get_book_passages(
        self,
        book_id: str,
        chapter: Optional[int] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Passage]:
        """
        Retrieves passages for a book with optional chapter filter and pagination.
        """
        # 1. Try SQLite
        if self.db_path.is_file():
            try:
                conn = get_db_connection(self.db_path)
                cur = conn.cursor()
                query = "SELECT raw_json FROM book_passages WHERE book_id = ?"
                params: List[Any] = [book_id]

                if chapter is not None:
                    query += " AND chapter_number = ?"
                    params.append(chapter)

                query += " ORDER BY sequence_number ASC"

                if limit is not None:
                    query += " LIMIT ? OFFSET ?"
                    params.extend([limit, offset])
                elif offset > 0:
                    query += " LIMIT -1 OFFSET ?"
                    params.append(offset)

                cur.execute(query, params)
                rows = cur.fetchall()
                conn.close()

                if rows:
                    return [Passage.from_dict(json.loads(r["raw_json"])) for r in rows]
            except Exception:
                pass

        # 2. Try JSONL fallback
        passages = list(self.iter_book_passages(book_id, chapter=chapter))
        if offset > 0:
            passages = passages[offset:]
        if limit is not None:
            passages = passages[:limit]
        return passages

    def iter_book_passages(
        self,
        book_id: str,
        chapter: Optional[int] = None,
    ) -> Iterator[Passage]:
        """
        Streams passages for a book line-by-line from JSONL without loading all into memory.
        """
        jsonl_path = self.books_dir / "texts" / f"{book_id}.jsonl"
        if not jsonl_path.is_file():
            return

        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                if chapter is not None and rec.get("chapter_number") != chapter:
                    continue
                yield Passage.from_dict(rec)

    def get_book_chapters(self, book_id: str) -> List[Dict[str, Any]]:
        """
        Retrieves chapter metadata and passage counts for a book.
        """
        # Try SQLite
        if self.db_path.is_file():
            try:
                conn = get_db_connection(self.db_path)
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT chapter_number, chapter_title, COUNT(*) as passage_count,
                           MIN(verse) as min_verse, MAX(verse) as max_verse
                    FROM book_passages
                    WHERE book_id = ?
                    GROUP BY chapter_number, chapter_title
                    ORDER BY chapter_number ASC
                    """,
                    (book_id,),
                )
                rows = cur.fetchall()
                conn.close()
                if rows:
                    return [
                        {
                            "chapter_number": r["chapter_number"],
                            "chapter_title": r["chapter_title"] or f"Chapter {r['chapter_number']}",
                            "passage_count": r["passage_count"],
                            "min_verse": r["min_verse"],
                            "max_verse": r["max_verse"],
                        }
                        for r in rows
                    ]
            except Exception:
                pass

        # Fallback from JSONL streaming
        ch_map: Dict[Optional[int], Dict[str, Any]] = {}
        for p in self.iter_book_passages(book_id):
            ch_num = p.chapter_number
            if ch_num not in ch_map:
                ch_map[ch_num] = {
                    "chapter_number": ch_num,
                    "chapter_title": p.chapter_title or (f"Chapter {ch_num}" if ch_num else "General"),
                    "passage_count": 0,
                    "min_verse": p.verse,
                    "max_verse": p.verse,
                }
            entry = ch_map[ch_num]
            entry["passage_count"] += 1
            if p.verse is not None:
                if entry["min_verse"] is None or p.verse < entry["min_verse"]:
                    entry["min_verse"] = p.verse
                if entry["max_verse"] is None or p.verse > entry["max_verse"]:
                    entry["max_verse"] = p.verse

        return sorted(ch_map.values(), key=lambda c: (c["chapter_number"] is None, c["chapter_number"]))

    def format_passage(self, passage: Passage, include_header: bool = True) -> str:
        """
        Formats a passage into a human-readable text presentation.
        """
        lines = []
        if include_header:
            loc_parts = []
            if passage.chapter_title:
                loc_parts.append(passage.chapter_title)
            elif passage.chapter_number:
                loc_parts.append(f"Chapter {passage.chapter_number}")

            if passage.verse:
                loc_parts.append(f"Verse {passage.verse}")
            elif passage.paragraph:
                loc_parts.append(f"Paragraph {passage.paragraph}")

            loc_str = " | ".join(loc_parts) if loc_parts else f"Passage {passage.sequence_number}"
            lines.append(f"[{passage.passage_id}] {loc_str} ({passage.language.upper()})")
            lines.append("-" * 60)

        lines.append(passage.text)
        return "\n".join(lines)
