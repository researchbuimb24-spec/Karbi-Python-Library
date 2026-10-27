"""
SQLite & FTS5 Database Engine for Karbi Language Library (`karbi.core.db`)
==========================================================================

Compiles canonical JSONL files into an optimized, indexed SQLite database
with Full-Text Search (FTS5) and reverse Multilingual-to-Karbi indexing.
"""

from __future__ import annotations
import json
import os
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from karbi.core.loader import load_jsonl_file


def get_user_data_dir() -> Path:
    """Returns an OS-appropriate writable directory for karbi runtime data/cache."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / "karbi"
        return Path.home() / ".karbi"
    else:
        xdg_data = os.environ.get("XDG_DATA_HOME")
        if xdg_data:
            return Path(xdg_data) / "karbi"
        xdg_cache = os.environ.get("XDG_CACHE_HOME")
        if xdg_cache:
            return Path(xdg_cache) / "karbi"
        return Path.home() / ".local" / "share" / "karbi"


def get_default_db_path() -> Path:
    """
    Returns the default path to the SQLite database.

    Resolution order:
    1. KARBI_DB_PATH environment variable (if set).
    2. Source repository root karbi.db if running from a source checkout
       (where pyproject.toml and data/ exist at the repository root).
    3. Standalone / installed package: karbi.db in the writable user data directory.
    """
    env_override = os.environ.get("KARBI_DB_PATH")
    if env_override:
        return Path(env_override)

    # Detect source-tree checkout
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    if (repo_root / "pyproject.toml").is_file() and (repo_root / "data" / "lexicon").is_dir():
        return repo_root / "karbi.db"

    return get_user_data_dir() / "karbi.db"


DEFAULT_DB_PATH = get_default_db_path()


@dataclass
class SearchResult:
    """Represents a search or translation match."""
    entry_id: str
    lemma: str
    part_of_speech: str
    definitions: Dict[str, List[str]]
    status: str
    match_source: str                      # e.g., "exact_translation", "fts_definition", "lemma_match"
    source_citation: Optional[str] = None
    examples: List[Dict[str, Any]] = None
    phonetic_ipa: Optional[str] = None


def get_db_connection(db_path: Optional[Union[str, Path]] = None) -> sqlite3.Connection:
    """Returns a connection to the SQLite database with row factory and foreign keys enabled."""
    target = db_path if db_path is not None else get_default_db_path()
    conn = sqlite3.connect(str(target))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn



def init_db_schema(conn: sqlite3.Connection) -> None:
    """Initializes normalized relational tables and the FTS5 search index."""
    cur = conn.cursor()

    # Enable foreign keys
    cur.execute("PRAGMA foreign_keys = ON;")

    # 1. Sources Registry
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            source_id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            title TEXT NOT NULL,
            creators_json TEXT NOT NULL,
            publication_json TEXT,
            archive_location TEXT,
            rights_status TEXT NOT NULL
        );
    """)

    # 2. Lexicon Entries
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lexicon_entries (
            entry_id TEXT PRIMARY KEY,
            lemma TEXT NOT NULL COLLATE NOCASE,
            script TEXT NOT NULL,
            dialect TEXT NOT NULL,
            status TEXT NOT NULL,
            ipa TEXT,
            raw_json TEXT NOT NULL
        );
    """)

    # 3. Senses
    cur.execute("""
        CREATE TABLE IF NOT EXISTS senses (
            sense_id TEXT NOT NULL,
            entry_id TEXT NOT NULL,
            part_of_speech TEXT NOT NULL,
            def_en TEXT,
            def_hi TEXT,
            def_as TEXT,
            def_bn TEXT,
            status TEXT NOT NULL,
            is_sensitive INTEGER NOT NULL DEFAULT 0,
            allow_index INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(entry_id) REFERENCES lexicon_entries(entry_id) ON DELETE CASCADE
        );
    """)

    # 4. Multilingual Translation Index (Reverse lookups: en/hi/as/bn -> Karbi)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS translations_index (
            from_lang TEXT NOT NULL,
            query_term TEXT NOT NULL COLLATE NOCASE,
            entry_id TEXT NOT NULL,
            sense_id TEXT NOT NULL,
            lemma TEXT NOT NULL,
            part_of_speech TEXT NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY(entry_id) REFERENCES lexicon_entries(entry_id) ON DELETE CASCADE
        );
    """)

    # Create b-tree indexes for fast lookups
    cur.execute("CREATE INDEX IF NOT EXISTS idx_trans_lookup ON translations_index(from_lang, query_term);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_trans_entry ON translations_index(entry_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lemma_lookup ON lexicon_entries(lemma);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_senses_entry ON senses(entry_id);")

    # 5. Spelling Variants Index (Instant lookup for modern/alternative orthography)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS spelling_variants_index (
            variant_term TEXT NOT NULL COLLATE NOCASE,
            entry_id TEXT NOT NULL,
            lemma TEXT NOT NULL,
            context TEXT,
            FOREIGN KEY(entry_id) REFERENCES lexicon_entries(entry_id) ON DELETE CASCADE
        );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_variant_lookup ON spelling_variants_index(variant_term);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_variant_entry ON spelling_variants_index(entry_id);")

    # 6. Full-Text Search (FTS5) Virtual Table for Lexicon
    try:
        cur.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_lexicon USING fts5(
                entry_id UNINDEXED,
                lemma,
                def_en,
                def_hi,
                def_as,
                def_bn,
                text_karbi,
                tokenize = 'unicode61 remove_diacritics 0'
            );
        """)
    except sqlite3.OperationalError:
        pass  # FTS5 not compiled or disabled; database continues with relational indices

    # 7. Books Catalogue Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS books (
            book_id TEXT PRIMARY KEY,
            canonical_title TEXT NOT NULL,
            alternate_titles_json TEXT,
            author TEXT,
            original_language TEXT NOT NULL,
            original_script TEXT,
            translator TEXT,
            editor TEXT,
            edition TEXT,
            publisher TEXT,
            publication_year INTEGER,
            document_type TEXT,
            volume TEXT,
            source_id TEXT,
            source_title TEXT,
            source_url TEXT,
            access_date TEXT,
            copyright_status TEXT NOT NULL,
            licence TEXT NOT NULL,
            permitted_reuse TEXT,
            attribution_requirements TEXT,
            redistribution_restrictions TEXT,
            import_status TEXT NOT NULL,
            imported_chapters_count INTEGER DEFAULT 0,
            imported_passages_count INTEGER DEFAULT 0,
            content_checksum TEXT,
            import_timestamp TEXT,
            text_path TEXT,
            notes TEXT,
            raw_json TEXT NOT NULL
        );
    """)

    # 8. Book Passages Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS book_passages (
            passage_id TEXT PRIMARY KEY,
            book_id TEXT NOT NULL,
            language TEXT NOT NULL,
            chapter_number INTEGER,
            chapter_title TEXT,
            section TEXT,
            verse INTEGER,
            paragraph INTEGER,
            sequence_number INTEGER NOT NULL,
            text TEXT NOT NULL,
            source_reference TEXT,
            provenance_status TEXT NOT NULL,
            translation_links_json TEXT,
            raw_json TEXT NOT NULL,
            FOREIGN KEY(book_id) REFERENCES books(book_id) ON DELETE CASCADE
        );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_passages_book ON book_passages(book_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_passages_chapter ON book_passages(book_id, chapter_number);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_passages_lang ON book_passages(language);")

    # 9. Book Translations Table (Bidirectional)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS book_translations (
            translation_id TEXT PRIMARY KEY,
            source_passage_id TEXT NOT NULL,
            target_passage_id TEXT,
            source_language TEXT NOT NULL,
            target_language TEXT NOT NULL,
            translated_text TEXT NOT NULL,
            translation_type TEXT NOT NULL,
            translator TEXT,
            reviewer_id TEXT,
            review_status TEXT NOT NULL,
            source_citation TEXT,
            notes TEXT,
            FOREIGN KEY(source_passage_id) REFERENCES book_passages(passage_id) ON DELETE CASCADE
        );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_trans_source_pid ON book_translations(source_passage_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_trans_langs ON book_translations(source_language, target_language);")

    # 10. Vocabulary Candidates Queue Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS book_vocab_candidates (
            candidate_id TEXT PRIMARY KEY,
            source_passage_id TEXT NOT NULL,
            book_id TEXT NOT NULL,
            source_term TEXT NOT NULL,
            source_language TEXT NOT NULL,
            context_sentence TEXT NOT NULL,
            proposed_karbi_term TEXT,
            dialect TEXT,
            status TEXT NOT NULL,
            reviewer_id TEXT,
            reviewer_notes TEXT,
            existing_lexicon_entry_id TEXT,
            created_at TEXT,
            FOREIGN KEY(source_passage_id) REFERENCES book_passages(passage_id) ON DELETE CASCADE
        );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_vocab_cand_book ON book_vocab_candidates(book_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_vocab_cand_status ON book_vocab_candidates(status);")

    # 11. Full-Text Search (FTS5) Virtual Table for Book Passages
    try:
        cur.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_passages USING fts5(
                passage_id UNINDEXED,
                book_id UNINDEXED,
                language UNINDEXED,
                chapter_title,
                text,
                tokenize = 'unicode61 remove_diacritics 0'
            );
        """)
    except sqlite3.OperationalError:
        pass

    conn.commit()



def compile_database(
    lexicon_paths: List[Union[str, Path]],
    source_paths: List[Union[str, Path]],
    db_path: Optional[Union[str, Path]] = None,
) -> Tuple[int, int]:
    """
    Compiles raw JSONL source files and lexicon files into the SQLite database.

    Returns:
        (entries_inserted_count, sources_inserted_count)
    """
    db_p = Path(db_path) if db_path is not None else get_default_db_path()
    if db_p.exists():
        db_p.unlink()

    db_p.parent.mkdir(parents=True, exist_ok=True)
    conn = get_db_connection(db_p)
    init_db_schema(conn)
    cur = conn.cursor()

    sources_count = 0
    entries_count = 0

    # 1. Ingest Sources
    for sp in source_paths:
        records, _ = load_jsonl_file(sp, raise_on_error=False)
        for rec in records:
            s = rec.data
            sid = s.get("source_id")
            if not sid:
                continue
            cur.execute(
                """
                INSERT OR REPLACE INTO sources (
                    source_id, source_type, title, creators_json,
                    publication_json, archive_location, rights_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sid,
                    s.get("source_type", "print_publication"),
                    s.get("title", ""),
                    json.dumps(s.get("creators", []), ensure_ascii=False),
                    json.dumps(s.get("publication_details", {}), ensure_ascii=False),
                    s.get("archive_location", ""),
                    s.get("rights_and_permissions", {}).get("status", ""),
                ),
            )
            sources_count += 1

    # 2. Ingest Lexicon Entries
    for lp in lexicon_paths:
        records, _ = load_jsonl_file(lp, raise_on_error=False)
        for rec in records:
            e = rec.data
            eid = e.get("id")
            if not eid:
                continue

            lemma = unicodedata.normalize("NFC", e.get("headword", {}).get("lemma", ""))
            script = e.get("headword", {}).get("script", "latin")
            dialect = e.get("dialect", {}).get("primary_variety", "rongkhang")
            status = e.get("status", "DRAFT")
            ipa = e.get("phonetics", {}).get("ipa")
            raw_json = json.dumps(e, ensure_ascii=False)

            cur.execute(
                """
                INSERT OR REPLACE INTO lexicon_entries (
                    entry_id, lemma, script, dialect, status, ipa, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (eid, lemma, script, dialect, status, ipa, raw_json),
            )
            entries_count += 1

            # Ingest Spelling Variants for Fast Indexed Lookup
            for v in e.get("spelling_variants", []):
                v_text = (v.get("text", "") if isinstance(v, dict) else str(v)).strip()
                v_ctx = v.get("dialect_or_context", "") if isinstance(v, dict) else ""
                if v_text:
                    cur.execute(
                        """
                        INSERT INTO spelling_variants_index (
                            variant_term, entry_id, lemma, context
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (unicodedata.normalize("NFC", v_text), eid, lemma, v_ctx),
                    )

            # Ingest Senses and Index Reverse Translations
            senses = e.get("senses", [])
            for s in senses:
                sid = s.get("sense_id", "S1")
                pos = s.get("part_of_speech", "")
                s_status = s.get("status", status)
                cm = s.get("cultural_metadata", {})
                is_sens = 1 if cm.get("is_culturally_sensitive", False) else 0
                allow_idx = 1 if cm.get("allow_search_indexing", True) else 0

                defs = s.get("definitions", {})

                def _gloss_texts(gloss_list):
                    """Extract plain strings from a definition list.

                    Each item may be either a bare string or a dict with a
                    'text' key (and optional 'verified' flag).
                    """
                    out = []
                    for item in gloss_list:
                        if isinstance(item, str):
                            out.append(item)
                        elif isinstance(item, dict):
                            t = item.get("text", "")
                            if t:
                                out.append(t)
                    return out

                def_en_str = " ; ".join(_gloss_texts(defs.get("en", [])))
                def_hi_str = " ; ".join(_gloss_texts(defs.get("hi", [])))
                def_as_str = " ; ".join(_gloss_texts(defs.get("as", [])))
                def_bn_str = " ; ".join(_gloss_texts(defs.get("bn", [])))

                cur.execute(
                    """
                    INSERT INTO senses (
                        sense_id, entry_id, part_of_speech,
                        def_en, def_hi, def_as, def_bn,
                        status, is_sensitive, allow_index
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (sid, eid, pos, def_en_str, def_hi_str, def_as_str, def_bn_str, s_status, is_sens, allow_idx),
                )

                # Populate Multilingual Index (Every word/gloss maps to Karbi lemma)
                for lang_code, glosses in defs.items():
                    for gloss in _gloss_texts(glosses):
                        cleaned = unicodedata.normalize("NFC", gloss.strip())
                        if cleaned:
                            cur.execute(
                                """
                                INSERT INTO translations_index (
                                    from_lang, query_term, entry_id, sense_id, lemma, part_of_speech, status
                                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                                """,
                                (lang_code.lower(), cleaned, eid, sid, lemma, pos, s_status),
                            )

                # Insert into FTS5 Index (only if allowed and not culturally confidential)
                if allow_idx and not is_sens:
                    try:
                        ex_karbi_text = " ".join([ex.get("text_karbi", "") for ex in s.get("examples", [])])
                        cur.execute(
                            """
                            INSERT INTO fts_lexicon (entry_id, lemma, def_en, def_hi, def_as, def_bn, text_karbi)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (eid, lemma, def_en_str, def_hi_str, def_as_str, def_bn_str, ex_karbi_text),
                        )
                    except sqlite3.OperationalError:
                        pass

    conn.commit()
    conn.close()
    return entries_count, sources_count


def ensure_database_ready(db_path: Optional[Union[str, Path]] = None) -> Path:
    """
    Ensures the compiled SQLite database exists and is populated, compiling it if necessary or stale.

    Validation checks:
    - Verifies that input resource files exist and can be discovered.
    - Verifies database mtime against resource files mtime.
    - Verifies that all expected relational tables and search virtual tables exist.
    - Verifies non-empty record count.
    - Automatically recompiles on corruption, missing tables, or stale data.
    """
    from karbi.core.resources import get_resource_paths

    target_path = Path(db_path) if db_path is not None else get_default_db_path()
    lex_files, src_files = get_resource_paths()

    if target_path.exists():
        conn = None
        try:
            db_mtime = target_path.stat().st_mtime
            input_files = [f for f in lex_files + src_files if f.is_file()]
            if not input_files:
                raise FileNotFoundError("No input lexicon or source files found to build database.")

            is_stale = any(f.stat().st_mtime > db_mtime for f in input_files)

            if not is_stale:
                conn = get_db_connection(target_path)
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
                existing_tables = {row[0] for row in cur.fetchall()}
                required_tables = {
                    "sources",
                    "lexicon_entries",
                    "senses",
                    "translations_index",
                    "spelling_variants_index",
                    "fts_lexicon",
                }
                if required_tables.issubset(existing_tables):
                    cur.execute("SELECT COUNT(*) FROM lexicon_entries")
                    count = cur.fetchone()[0]
                    if count > 0:
                        return target_path
        except Exception:
            pass  # Recompile if corrupted, incomplete, missing tables, or stale
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    target_path.parent.mkdir(parents=True, exist_ok=True)
    compile_database(lex_files, src_files, db_path=target_path)
    return target_path


__all__ = [
    "DEFAULT_DB_PATH",
    "SearchResult",
    "compile_database",
    "ensure_database_ready",
    "get_db_connection",
    "get_default_db_path",
    "get_user_data_dir",
    "init_db_schema",
]
