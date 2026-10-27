"""
Vocabulary Candidate Extraction Workflow (`karbi.books.vocabulary`)
===================================================================

Extracts linguistic candidates from book passages for community and linguistic review.
Strictly isolates unreviewed candidates from the authoritative core lexicon.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional, Set, Union
import unicodedata

from karbi.books.importer import get_default_books_dir
from karbi.books.models import CandidateStatus, Passage, VocabularyCandidate
from karbi.books.reader import BookReader
from karbi.core.db import get_db_connection, get_default_db_path


class VocabularyCandidateWorkflow:
    """
    Safely discovers and tracks candidate lexical terms from books without
    polluting the authoritative lexicon.
    """

    def __init__(
        self,
        db_path: Optional[Union[str, Path]] = None,
        books_dir: Optional[Union[str, Path]] = None,
    ):
        self.db_path = Path(db_path) if db_path is not None else get_default_db_path()
        self.books_dir = Path(books_dir) if books_dir is not None else get_default_books_dir()
        self.reader = BookReader(db_path=self.db_path, books_dir=self.books_dir)
        self.candidates_file = self.books_dir / "candidates" / "vocab_candidates.jsonl"

    def check_existing_lexicon(self, term: str) -> Optional[str]:
        """
        Checks if the term already exists in the authoritative Karbi lexicon.
        Returns the entry_id if found, or None.
        """
        clean = unicodedata.normalize("NFC", term.strip().lower())
        if not self.db_path.is_file():
            return None

        try:
            conn = get_db_connection(self.db_path)
            cur = conn.cursor()
            cur.execute("SELECT entry_id FROM lexicon_entries WHERE lemma = ? COLLATE NOCASE", (clean,))
            row = cur.fetchone()
            if row:
                conn.close()
                return row["entry_id"]

            # Also check spelling variants
            cur.execute(
                "SELECT entry_id FROM spelling_variants_index WHERE variant_term = ? COLLATE NOCASE",
                (clean,),
            )
            row = cur.fetchone()
            conn.close()
            if row:
                return row["entry_id"]
        except Exception:
            pass

        return None

    def extract_candidates_from_passage(
        self,
        passage: Passage,
        min_len: int = 3,
    ) -> List[VocabularyCandidate]:
        """
        Extracts candidate word tokens from a passage text, filtering punctuation and existing entries.
        """
        candidates: List[VocabularyCandidate] = []
        # Match alphabetic words including diacritics
        words = re.findall(r"\b[\w\u00C0-\u024F\u1E00-\u1EFF\-]{" + str(min_len) + r",}\b", passage.text)

        seen: Set[str] = set()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        for idx, word in enumerate(words, 1):
            normalized = unicodedata.normalize("NFC", word.strip())
            lower_norm = normalized.lower()
            if lower_norm in seen:
                continue
            seen.add(lower_norm)

            existing_id = self.check_existing_lexicon(normalized)

            cand = VocabularyCandidate(
                candidate_id=f"CAND:{passage.passage_id}:{idx}",
                source_passage_id=passage.passage_id,
                book_id=passage.book_id,
                source_term=normalized,
                source_language=passage.language,
                context_sentence=passage.text[:250],
                status=CandidateStatus.EXTRACTED.value,
                existing_lexicon_entry_id=existing_id,
                created_at=now_iso,
            )
            candidates.append(cand)

        return candidates

    def save_candidates(self, candidates: List[VocabularyCandidate]) -> int:
        """
        Saves extracted candidates to SQLite and the candidate queue JSONL file.
        Returns the number of candidates saved.
        """
        if not candidates:
            return 0

        # 1. SQLite storage
        if self.db_path.is_file():
            try:
                conn = get_db_connection(self.db_path)
                cur = conn.cursor()
                for c in candidates:
                    cur.execute(
                        """
                        INSERT OR REPLACE INTO book_vocab_candidates (
                            candidate_id, source_passage_id, book_id,
                            source_term, source_language, context_sentence,
                            proposed_karbi_term, dialect, status,
                            reviewer_id, reviewer_notes,
                            existing_lexicon_entry_id, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            c.candidate_id,
                            c.source_passage_id,
                            c.book_id,
                            c.source_term,
                            c.source_language,
                            c.context_sentence,
                            c.proposed_karbi_term,
                            c.dialect,
                            c.status,
                            c.reviewer_id,
                            c.reviewer_notes,
                            c.existing_lexicon_entry_id,
                            c.created_at,
                        ),
                    )
                conn.commit()
                conn.close()
            except Exception:
                pass

        # 2. Append to JSONL file
        self.candidates_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.candidates_file, "a", encoding="utf-8") as f:
            for c in candidates:
                f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")

        return len(candidates)

    def list_candidates(
        self,
        book_id: Optional[str] = None,
        status: Optional[str] = None,
        unattested_only: bool = False,
    ) -> List[VocabularyCandidate]:
        """
        Lists vocabulary candidates with optional filters.
        """
        results: List[VocabularyCandidate] = []
        if self.db_path.is_file():
            try:
                conn = get_db_connection(self.db_path)
                cur = conn.cursor()
                sql = "SELECT * FROM book_vocab_candidates WHERE 1=1"
                params: List[Any] = []
                if book_id:
                    sql += " AND book_id = ?"
                    params.append(book_id)
                if status:
                    sql += " AND status = ?"
                    params.append(status)
                if unattested_only:
                    sql += " AND existing_lexicon_entry_id IS NULL"

                cur.execute(sql, params)
                rows = cur.fetchall()
                conn.close()
                for r in rows:
                    results.append(
                        VocabularyCandidate(
                            candidate_id=r["candidate_id"],
                            source_passage_id=r["source_passage_id"],
                            book_id=r["book_id"],
                            source_term=r["source_term"],
                            source_language=r["source_language"],
                            context_sentence=r["context_sentence"],
                            proposed_karbi_term=r["proposed_karbi_term"],
                            dialect=r["dialect"],
                            status=r["status"],
                            reviewer_id=r["reviewer_id"],
                            reviewer_notes=r["reviewer_notes"],
                            existing_lexicon_entry_id=r["existing_lexicon_entry_id"],
                            created_at=r["created_at"],
                        )
                    )
                if results:
                    return results
            except Exception:
                pass

        # Fallback to candidates.jsonl
        if self.candidates_file.is_file():
            with open(self.candidates_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    rec = json.loads(line)
                    c = VocabularyCandidate.from_dict(rec)
                    if book_id and c.book_id != book_id:
                        continue
                    if status and c.status != status:
                        continue
                    if unattested_only and c.existing_lexicon_entry_id:
                        continue
                    results.append(c)

        return results
