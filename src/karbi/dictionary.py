"""
Karbi Dictionary Lookup & Search Engine (`karbi.dictionary`)
============================================================

Provides direct Karbi headword lookup, spelling variant resolution,
and comprehensive search across definitions and phonetic notations.
"""

from __future__ import annotations
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from karbi.core.db import DEFAULT_DB_PATH, ensure_database_ready, get_db_connection


@dataclass
class DictionaryEntry:
    """A fully hydrated Karbi dictionary entry."""
    entry_id: str
    lemma: str
    script: str
    dialect: str
    status: str
    phonetics_ipa: Optional[str]
    senses: List[Dict[str, Any]]
    spelling_variants: List[Dict[str, Any]]
    cross_references: List[Dict[str, Any]]
    provenance: Dict[str, Any]
    source_citation: Optional[str] = None
    source_citations: List[str] = field(default_factory=list)

    def get_meanings(self, lang: str = "en", verified_only: bool = False) -> List[str]:
        """
        Returns list of definition strings for a given language code ('en', 'hi', 'as', 'bn').
        If verified_only=True, excludes definitions marked as unverified.
        """
        results: List[str] = []
        for sense in self.senses:
            defs = sense.get("definitions", {}).get(lang, [])
            gloss_prov = str((sense.get("gloss_provenance") or {}).get(lang, "")).lower()
            for d in defs:
                if isinstance(d, dict):
                    txt = d.get("text", "").strip()
                    is_ver = d.get("verified", False)
                    if verified_only and not is_ver:
                        continue
                    if txt and txt not in results:
                        results.append(txt)
                elif isinstance(d, str):
                    txt = d.strip()
                    is_ver = gloss_prov in ("source_attested", "verified", "peer_reviewed")
                    if verified_only and not is_ver:
                        continue
                    if txt and txt not in results:
                        results.append(txt)
        return results

    def get_spelling_variants(self) -> List[str]:
        """Returns list of alternative spellings and contemporary orthographic variants."""
        variants: List[str] = []
        for v in self.spelling_variants:
            if isinstance(v, dict):
                t = v.get("text", "").strip()
                if t and t not in variants:
                    variants.append(t)
            elif isinstance(v, str):
                t = v.strip()
                if t and t not in variants:
                    variants.append(t)
        return variants

    def as_dict(self) -> Dict[str, Any]:
        """Serializes the dictionary entry into a clean Python dictionary."""
        return {
            "entry_id": self.entry_id,
            "lemma": self.lemma,
            "script": self.script,
            "dialect": self.dialect,
            "status": self.status,
            "phonetics_ipa": self.phonetics_ipa,
            "senses": self.senses,
            "spelling_variants": self.spelling_variants,
            "cross_references": self.cross_references,
            "provenance": self.provenance,
            "source_citation": self.source_citation,
            "source_citations": self.source_citations,
        }


def _raw_to_entry(raw: Dict[str, Any], cur: sqlite3.Cursor) -> DictionaryEntry:
    """Converts a raw JSON lexicon entry into a fully populated DictionaryEntry."""
    citations: List[str] = []
    evs = raw.get("provenance", {}).get("evidence_records", [])
    for ev in evs:
        if not isinstance(ev, dict):
            continue
        sid = ev.get("source_id")
        locator = ev.get("locator", "")
        if sid:
            cur.execute("SELECT title FROM sources WHERE source_id = ?", (sid,))
            s_row = cur.fetchone()
            if s_row and s_row["title"]:
                title = s_row["title"]
                c_str = f"{title} ({locator})" if locator else title
            else:
                c_str = f"{sid} ({locator})" if locator else sid
            if c_str not in citations:
                citations.append(c_str)

    citation = "; ".join(citations) if citations else None

    return DictionaryEntry(
        entry_id=raw.get("id", ""),
        lemma=raw.get("headword", {}).get("lemma", ""),
        script=raw.get("headword", {}).get("script", "latin"),
        dialect=raw.get("dialect", {}).get("primary_variety", "rongkhang"),
        status=raw.get("status", "DRAFT"),
        phonetics_ipa=raw.get("phonetics", {}).get("ipa"),
        senses=raw.get("senses", []),
        spelling_variants=raw.get("spelling_variants", []),
        cross_references=raw.get("cross_references", []),
        provenance=raw.get("provenance", {}),
        source_citation=citation,
        source_citations=citations,
    )


def lookup_all(
    karbi_word: str,
    verified_only: bool = False,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> List[DictionaryEntry]:
    """
    Looks up all matching Karbi headwords and spelling variants (including homonyms).

    Args:
        karbi_word: The Karbi word to search for (e.g. 'arlèng', 'hem', 'cho').
        verified_only: If True, only returns entries whose status is verified or source-attested
                       (excluding DRAFT, AI_CANDIDATE, and CITATION_MISMATCH entries).
        db_path: Optional custom path to compiled SQLite database.
        conn: Optional active sqlite3.Connection to reuse for batch operations.

    Returns:
        List of DictionaryEntry objects matching the query.
    """
    if karbi_word is None or not isinstance(karbi_word, str):
        return []
    word = unicodedata.normalize("NFC", karbi_word.strip())
    if not word:
        return []

    should_close = False
    if conn is None:
        target_db = ensure_database_ready(db_path)
        conn = get_db_connection(target_db)
        should_close = True

    try:
        cur = conn.cursor()
        entries: List[DictionaryEntry] = []
        seen_ids: set[str] = set()

        # 1. Direct match on lemma
        cur.execute("SELECT raw_json FROM lexicon_entries WHERE lemma = ? COLLATE NOCASE", (word,))
        for row in cur.fetchall():
            raw = json.loads(row["raw_json"])
            eid = raw.get("id", "")
            if eid not in seen_ids:
                seen_ids.add(eid)
                entries.append(_raw_to_entry(raw, cur))

        # Fallback to stripped punctuation if initial direct lookup yielded nothing
        if not entries:
            cleaned_word = re.sub(r"^[^\w]+|[^\w]+$", "", word)
            if cleaned_word and cleaned_word != word:
                cur.execute("SELECT raw_json FROM lexicon_entries WHERE lemma = ? COLLATE NOCASE", (cleaned_word,))
                for row in cur.fetchall():
                    raw = json.loads(row["raw_json"])
                    eid = raw.get("id", "")
                    if eid not in seen_ids:
                        seen_ids.add(eid)
                        entries.append(_raw_to_entry(raw, cur))

        # 2. Check FTS5 for lemma variants if no exact match
        if not entries:
            try:
                safe_word = word.replace('"', '""')
                cur.execute(
                    """
                    SELECT e.raw_json
                    FROM fts_lexicon f
                    JOIN lexicon_entries e ON f.entry_id = e.entry_id
                    WHERE f.lemma MATCH ?
                    LIMIT 10
                    """,
                    (f'"{safe_word}"',),
                )
                for row in cur.fetchall():
                    raw = json.loads(row["raw_json"])
                    eid = raw.get("id", "")
                    if eid not in seen_ids:
                        seen_ids.add(eid)
                        entries.append(_raw_to_entry(raw, cur))
            except (sqlite3.OperationalError, sqlite3.DatabaseError):
                pass

        # 3. Check spelling variants using indexed table first
        if not entries:
            search_target = word.lower()
            cleaned_target = re.sub(r"^[^\w]+|[^\w]+$", "", word).lower()
            try:
                cur.execute(
                    """
                    SELECT e.raw_json
                    FROM spelling_variants_index v
                    JOIN lexicon_entries e ON v.entry_id = e.entry_id
                    WHERE v.variant_term IN (?, ?) COLLATE NOCASE
                    """,
                    (search_target, cleaned_target),
                )
                for row in cur.fetchall():
                    raw = json.loads(row["raw_json"])
                    eid = raw.get("id", "")
                    if eid not in seen_ids:
                        seen_ids.add(eid)
                        entries.append(_raw_to_entry(raw, cur))
            except Exception:
                pass

        # 4. Fallback table scan if index is missing or yielded nothing
        if not entries:
            search_target = word.lower()
            cleaned_target = re.sub(r"^[^\w]+|[^\w]+$", "", word).lower()
            cur.execute("SELECT raw_json FROM lexicon_entries")
            for candidate_row in cur.fetchall():
                c_raw = json.loads(candidate_row["raw_json"])
                variants = c_raw.get("spelling_variants", [])
                for v in variants:
                    v_text = (v.get("text", "") if isinstance(v, dict) else str(v)).strip().lower()
                    if v_text in (search_target, cleaned_target) and v_text:
                        eid = c_raw.get("id", "")
                        if eid not in seen_ids:
                            seen_ids.add(eid)
                            entries.append(_raw_to_entry(c_raw, cur))
                        break

        if verified_only:
            entries = [
                e for e in entries
                if e.status in ("SOURCE_ATTESTED", "VERIFIED", "CONFIRMED_FROM_SOURCE")
            ]

        return entries
    finally:
        if should_close:
            try:
                conn.close()
            except Exception:
                pass


def lookup(
    karbi_word: str,
    dialect: Optional[str] = None,
    verified_only: bool = False,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[DictionaryEntry]:
    """
    Looks up a Karbi headword or spelling variant.

    Args:
        karbi_word: The Karbi word to search for (e.g. 'arlèng', 'hem', 'làng').
        dialect: Optional dialect filter (e.g. 'rongkhang').
        verified_only: If True, only returns verified or source-attested entries.
        db_path: Optional custom path to compiled SQLite database.
        conn: Optional active sqlite3.Connection to reuse.

    Returns:
        DictionaryEntry object if found, or None.
    """
    entries = lookup_all(karbi_word, verified_only=verified_only, db_path=db_path, conn=conn)
    if not entries:
        return None
    if dialect:
        dialect_matches = [e for e in entries if e.dialect == dialect]
        if dialect_matches:
            return dialect_matches[0]
    return entries[0]


def batch_lookup(
    karbi_words: Sequence[str],
    verified_only: bool = False,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Optional[DictionaryEntry]]:
    """
    Performs batch lookup for multiple Karbi headwords or spelling variants,
    reusing a single database connection.

    Args:
        karbi_words: Iterable of Karbi words to look up.
        verified_only: If True, only returns verified or source-attested entries.
        db_path: Optional custom path to compiled SQLite database.
        conn: Optional active sqlite3.Connection to reuse.

    Returns:
        Dictionary mapping each input word to its DictionaryEntry, or None if not found.
    """
    should_close = False
    if conn is None:
        target_db = ensure_database_ready(db_path)
        conn = get_db_connection(target_db)
        should_close = True

    try:
        return {word: lookup(word, verified_only=verified_only, db_path=db_path, conn=conn) for word in karbi_words}
    finally:
        if should_close:
            try:
                conn.close()
            except Exception:
                pass

