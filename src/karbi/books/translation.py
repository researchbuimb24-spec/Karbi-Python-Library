"""
Passage-Level Multilingual Translation Repository (`karbi.books.translation`)
=============================================================================

Supports bidirectional passage translation alignment between Karbi and many languages:
Karbi <-> English, Hindi, Assamese, Bengali, Sanskrit, Urdu, etc.

Maintains strict provenance tracking across published translations, community-reviewed
translations, machine drafts, and unverified submissions.
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Tuple, Union

from karbi.books.importer import get_default_books_dir
from karbi.books.models import Passage, TranslationRecord, TranslationType
from karbi.core.db import get_db_connection, get_default_db_path


# Registered supported/extensible language pairs for Karbi book translations
BOOK_TRANSLATION_LANGUAGES: Dict[str, Dict[str, str]] = {
    "mjw": {"name": "Karbi", "script": "Latin / Assamese-Bengali"},
    "en": {"name": "English", "script": "Latin"},
    "hi": {"name": "Hindi", "script": "Devanagari"},
    "as": {"name": "Assamese", "script": "Bengali-Assamese"},
    "bn": {"name": "Bengali", "script": "Bengali-Assamese"},
    "sa": {"name": "Sanskrit", "script": "Devanagari"},
    "ur": {"name": "Urdu", "script": "Perso-Arabic"},
    # Extensible additional languages
    "ne": {"name": "Nepali", "script": "Devanagari"},
    "brx": {"name": "Bodo", "script": "Devanagari"},
    "kha": {"name": "Khasi", "script": "Latin"},
    "grt": {"name": "Garo", "script": "Latin"},
    "lus": {"name": "Mizo", "script": "Latin"},
    "mni": {"name": "Meitei", "script": "Meitei Mayek / Bengali"},
    "trp": {"name": "Kokborok", "script": "Latin / Bengali"},
    "or": {"name": "Odia", "script": "Odia"},
    "mr": {"name": "Marathi", "script": "Devanagari"},
    "gu": {"name": "Gujarati", "script": "Gujarati"},
    "pa": {"name": "Punjabi", "script": "Gurmukhi"},
    "ta": {"name": "Tamil", "script": "Tamil"},
    "te": {"name": "Telugu", "script": "Telugu"},
    "kn": {"name": "Kannada", "script": "Kannada"},
    "ml": {"name": "Malayalam", "script": "Malayalam"},
}


class BookTranslationRepository:
    """
    Manages bidirectional translations linked to passage IDs.
    """

    def __init__(
        self,
        db_path: Optional[Union[str, Path]] = None,
        books_dir: Optional[Union[str, Path]] = None,
    ):
        self.db_path = Path(db_path) if db_path is not None else get_default_db_path()
        self.books_dir = Path(books_dir) if books_dir is not None else get_default_books_dir()
        self.translations_file = self.books_dir / "translations" / "translations.jsonl"

    def add_translation(
        self,
        translation: TranslationRecord,
        persist_to_file: bool = True,
    ) -> None:
        """
        Stores a passage translation alignment in SQLite and optionally the canonical JSONL file.
        """
        if not translation.translation_id:
            translation.translation_id = (
                f"TR:{translation.source_passage_id}:{translation.target_language}"
            )

        # 1. Store in SQLite
        if self.db_path.is_file():
            try:
                conn = get_db_connection(self.db_path)
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT OR REPLACE INTO book_translations (
                        translation_id, source_passage_id, target_passage_id,
                        source_language, target_language, translated_text,
                        translation_type, translator, reviewer_id,
                        review_status, source_citation, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        translation.translation_id,
                        translation.source_passage_id,
                        translation.target_passage_id,
                        translation.source_language,
                        translation.target_language,
                        translation.translated_text,
                        translation.translation_type,
                        translation.translator,
                        translation.reviewer_id,
                        translation.review_status,
                        translation.source_citation,
                        translation.notes,
                    ),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass

        # 2. Append to canonical translations.jsonl
        if persist_to_file:
            self.translations_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.translations_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(translation.to_dict(), ensure_ascii=False) + "\n")

    def get_translations_for_passage(
        self,
        passage_id: str,
        target_language: Optional[str] = None,
    ) -> List[TranslationRecord]:
        """
        Retrieves all registered translations for a specific source passage ID.
        """
        results: List[TranslationRecord] = []

        # 1. Try SQLite
        if self.db_path.is_file():
            try:
                conn = get_db_connection(self.db_path)
                cur = conn.cursor()
                sql = "SELECT * FROM book_translations WHERE source_passage_id = ?"
                params: List[Any] = [passage_id]
                if target_language:
                    sql += " AND target_language = ?"
                    params.append(target_language.lower())
                cur.execute(sql, params)
                rows = cur.fetchall()
                conn.close()
                for r in rows:
                    results.append(
                        TranslationRecord(
                            translation_id=r["translation_id"],
                            source_passage_id=r["source_passage_id"],
                            target_passage_id=r["target_passage_id"],
                            source_language=r["source_language"],
                            target_language=r["target_language"],
                            translated_text=r["translated_text"],
                            translation_type=r["translation_type"],
                            translator=r["translator"],
                            reviewer_id=r["reviewer_id"],
                            review_status=r["review_status"],
                            source_citation=r["source_citation"],
                            notes=r["notes"],
                        )
                    )
                if results:
                    return results
            except Exception:
                pass

        # 2. Fallback to reading translations.jsonl
        if self.translations_file.is_file():
            with open(self.translations_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    rec = json.loads(line)
                    if rec.get("source_passage_id") == passage_id:
                        if target_language and rec.get("target_language", "").lower() != target_language.lower():
                            continue
                        results.append(TranslationRecord.from_dict(rec))

        return results

    def get_supported_book_languages(self) -> Dict[str, Dict[str, str]]:
        """Returns the dictionary of extensible book translation languages."""
        return BOOK_TRANSLATION_LANGUAGES
