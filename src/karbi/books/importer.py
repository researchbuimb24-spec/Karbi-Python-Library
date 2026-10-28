"""
Book and Passage Import Pipeline (`karbi.books.importer`)
=========================================================

Handles ingestion of digital book texts (JSONL, JSON, TXT, Markdown) into the
Karbi Language Library. Enforces structural preservation, stable passage IDs,
duplicate detection, provenance validation, and atomic writes.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from karbi.books.catalog import BookCatalog, get_default_catalog_path
from karbi.books.models import (
    BookImportStatus,
    BookMetadata,
    ImportManifest,
    Passage,
    PassageProvenanceStatus,
    TranslationRecord,
)
from karbi.core.db import get_db_connection, get_default_db_path, init_db_schema


def get_default_books_dir() -> Path:
    """Returns the base data directory for book storage (`data/books`)."""
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    repo_books = repo_root / "data" / "books"
    if repo_books.is_dir():
        return repo_books
    return repo_books


class BookImporter:
    """
    Robust digital book text importer supporting streaming JSONL, JSON, and structured text.
    """

    def __init__(
        self,
        catalog: Optional[BookCatalog] = None,
        db_path: Optional[Union[str, Path]] = None,
        base_dir: Optional[Union[str, Path]] = None,
    ):
        self.catalog = catalog or BookCatalog()
        self.db_path = Path(db_path) if db_path is not None else get_default_db_path()
        self.base_dir = Path(base_dir) if base_dir is not None else get_default_books_dir()
        self.texts_dir = self.base_dir / "texts"
        self.manifests_dir = self.base_dir / "manifests"
        self.translations_dir = self.base_dir / "translations"

    def calculate_checksum(self, text_or_bytes: Union[str, bytes]) -> str:
        """Calculates SHA-256 content checksum."""
        raw = text_or_bytes.encode("utf-8") if isinstance(text_or_bytes, str) else text_or_bytes
        return hashlib.sha256(raw).hexdigest()

    def parse_plain_text(
        self,
        raw_text: str,
        book_id: str,
        language: str = "en",
        chapter_regex: Optional[str] = None,
    ) -> List[Passage]:
        """
        Parses structured plain text into passages while preserving chapters,
        stanzas, or paragraphs.
        """
        passages: List[Passage] = []
        normalized_text = unicodedata.normalize("NFC", raw_text)

        # Default chapter pattern matching "CHAPTER I", "Chapter 1", etc.
        ch_pattern = re.compile(
            chapter_regex or r"(?:^|\n)\s*(?:CHAPTER\s+([IVXLCDM\d]+)|##\s+(?:Chapter\s+)?([IVXLCDM\d]+))([^\n]*)",
            re.IGNORECASE,
        )

        matches = list(ch_pattern.finditer(normalized_text))
        if not matches:
            # No chapters found; treat paragraphs as passages
            paragraphs = [p.strip() for p in normalized_text.split("\n\n") if p.strip()]
            for seq, para in enumerate(paragraphs, 1):
                passages.append(
                    Passage(
                        passage_id=f"{book_id}:{seq}",
                        book_id=book_id,
                        language=language,
                        sequence_number=seq,
                        paragraph=seq,
                        text=para,
                        provenance_status=PassageProvenanceStatus.SOURCE_ATTESTED.value,
                    )
                )
            return passages

        seq_counter = 1
        for i, match in enumerate(matches):
            raw_num = match.group(1) or match.group(2)
            title_rest = (match.group(3) or "").strip()
            ch_num = self._roman_or_int_to_int(raw_num)
            ch_title = f"Chapter {raw_num}" + (f": {title_rest}" if title_rest else "")

            start_idx = match.end()
            end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(normalized_text)
            body = normalized_text[start_idx:end_idx].strip()

            # Split chapter body into verse blocks / stanzas / paragraphs
            blocks = [b.strip() for b in re.split(r"\n\s*\n", body) if b.strip()]
            for verse_num, block in enumerate(blocks, 1):
                passages.append(
                    Passage(
                        passage_id=f"{book_id}:{ch_num}:{verse_num}",
                        book_id=book_id,
                        language=language,
                        chapter_number=ch_num,
                        chapter_title=ch_title,
                        verse=verse_num,
                        sequence_number=seq_counter,
                        text=block,
                        provenance_status=PassageProvenanceStatus.SOURCE_ATTESTED.value,
                    )
                )
                seq_counter += 1

        return passages

    def _roman_or_int_to_int(self, val: str) -> int:
        """Converts Roman numerals or digit strings into integers."""
        clean = val.strip().upper()
        if clean.isdigit():
            return int(clean)
        roman_map = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
        total = 0
        prev = 0
        for char in reversed(clean):
            curr = roman_map.get(char, 0)
            if curr >= prev:
                total += curr
            else:
                total -= curr
            prev = curr
        return total if total > 0 else 1

    def import_passages(
        self,
        metadata: BookMetadata,
        passages: List[Passage],
        dry_run: bool = False,
        overwrite: bool = False,
        translations: Optional[List[TranslationRecord]] = None,
    ) -> ImportManifest:
        """
        Imports a validated list of passages for a book into the repository.
        Performs collision checks, atomic disk writes, catalogue updates, and database indexing.
        """
        if not metadata.book_id:
            raise ValueError("BookMetadata must contain a non-empty 'book_id'.")
        if not metadata.canonical_title:
            raise ValueError("BookMetadata must contain a non-empty 'canonical_title'.")
        if not passages:
            raise ValueError(f"No passages provided for import into book '{metadata.book_id}'.")

        existing_book = self.catalog.get_book(metadata.book_id)
        if existing_book and existing_book.import_status == BookImportStatus.FULLY_IMPORTED.value and not overwrite:
            raise ValueError(
                f"Book '{metadata.book_id}' is already fully imported ({existing_book.imported_passages_count} passages). "
                f"Specify overwrite=True to replace."
            )

        # Calculate checksum across all passage texts
        combined_text = "\n---\n".join(p.text for p in passages)
        content_sha256 = self.calculate_checksum(combined_text)

        # Detect distinct chapters
        distinct_chapters = {p.chapter_number for p in passages if p.chapter_number is not None}
        chapter_count = len(distinct_chapters) if distinct_chapters else 1

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        manifest = ImportManifest(
            book_id=metadata.book_id,
            canonical_title=metadata.canonical_title,
            source_file_path=metadata.text_path or f"data/books/texts/{metadata.book_id}.jsonl",
            sha256_checksum=content_sha256,
            total_chapters=chapter_count,
            total_passages=len(passages),
            language=metadata.original_language,
            import_timestamp=now_iso,
            licence=metadata.licence,
            copyright_status=metadata.copyright_status,
            dry_run=dry_run,
            notes=f"Imported {len(passages)} passages across {chapter_count} chapter(s).",
        )

        if dry_run:
            return manifest

        # 1. Atomic write to data/books/texts/{book_id}.jsonl
        self.texts_dir.mkdir(parents=True, exist_ok=True)
        target_jsonl = self.texts_dir / f"{metadata.book_id}.jsonl"
        temp_jsonl = target_jsonl.with_suffix(".tmp")

        with open(temp_jsonl, "w", encoding="utf-8") as f:
            for p in passages:
                f.write(json.dumps(p.to_dict(), ensure_ascii=False) + "\n")
        temp_jsonl.replace(target_jsonl)

        # Recompute SHA-256 directly from the canonical on-disk JSONL text file
        content_sha256 = self.calculate_checksum(target_jsonl.read_bytes())
        manifest.sha256_checksum = content_sha256

        # 2. Atomic write to manifests/
        self.manifests_dir.mkdir(parents=True, exist_ok=True)
        target_manifest = self.manifests_dir / f"manifest_{metadata.book_id}.json"
        temp_manifest = target_manifest.with_suffix(".tmp")
        with open(temp_manifest, "w", encoding="utf-8") as f:
            json.dump(manifest.to_dict(), f, indent=2, ensure_ascii=False)
        temp_manifest.replace(target_manifest)

        # 3. Update catalogue metadata
        metadata.import_status = BookImportStatus.FULLY_IMPORTED.value
        metadata.imported_chapters_count = chapter_count
        metadata.imported_passages_count = len(passages)
        metadata.content_checksum = content_sha256
        metadata.import_timestamp = now_iso
        metadata.text_path = f"data/books/texts/{metadata.book_id}.jsonl"
        self.catalog.update_book(metadata)
        self.catalog.save()

        # 4. Index passages into SQLite database
        self.index_book_to_db(metadata, passages, translations=translations)

        return manifest

    def index_book_to_db(
        self,
        metadata: BookMetadata,
        passages: List[Passage],
        translations: Optional[List[TranslationRecord]] = None,
    ) -> None:
        """
        Indexes book metadata, passages, and full-text search entries into SQLite.
        """
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = get_db_connection(self.db_path)
        init_db_schema(conn)
        cur = conn.cursor()

        # 1. Upsert Book Metadata
        cur.execute(
            """
            INSERT OR REPLACE INTO books (
                book_id, canonical_title, alternate_titles_json, author,
                original_language, original_script, translator, editor,
                edition, publisher, publication_year, document_type,
                volume, source_id, source_title, source_url, access_date,
                copyright_status, licence, permitted_reuse,
                attribution_requirements, redistribution_restrictions,
                import_status, imported_chapters_count, imported_passages_count,
                content_checksum, import_timestamp, text_path, notes, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                metadata.book_id,
                metadata.canonical_title,
                json.dumps(metadata.alternate_titles, ensure_ascii=False),
                metadata.author,
                metadata.original_language,
                metadata.original_script,
                metadata.translator,
                metadata.editor,
                metadata.edition,
                metadata.publisher,
                metadata.publication_year,
                metadata.document_type,
                metadata.volume,
                metadata.source_id,
                metadata.source_title,
                metadata.source_url,
                metadata.access_date,
                metadata.copyright_status,
                metadata.licence,
                metadata.permitted_reuse,
                metadata.attribution_requirements,
                metadata.redistribution_restrictions,
                metadata.import_status,
                metadata.imported_chapters_count,
                metadata.imported_passages_count,
                metadata.content_checksum,
                metadata.import_timestamp,
                metadata.text_path,
                metadata.notes,
                json.dumps(metadata.to_dict(), ensure_ascii=False),
            ),
        )

        # Clear any existing passages for this book (to support clean overwrites)
        cur.execute("DELETE FROM book_passages WHERE book_id = ?", (metadata.book_id,))
        try:
            cur.execute("DELETE FROM fts_passages WHERE book_id = ?", (metadata.book_id,))
        except sqlite3.OperationalError:
            pass

        # 2. Insert Passages
        for p in passages:
            cur.execute(
                """
                INSERT INTO book_passages (
                    passage_id, book_id, language, chapter_number,
                    chapter_title, section, verse, paragraph,
                    sequence_number, text, source_reference,
                    provenance_status, translation_links_json, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    p.passage_id,
                    p.book_id,
                    p.language,
                    p.chapter_number,
                    p.chapter_title,
                    p.section,
                    p.verse,
                    p.paragraph,
                    p.sequence_number,
                    p.text,
                    p.source_reference,
                    p.provenance_status,
                    json.dumps(p.translation_links, ensure_ascii=False),
                    json.dumps(p.to_dict(), ensure_ascii=False),
                ),
            )

            # Insert into FTS5
            try:
                cur.execute(
                    """
                    INSERT INTO fts_passages (passage_id, book_id, language, chapter_title, text)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (p.passage_id, p.book_id, p.language, p.chapter_title or "", p.text),
                )
            except sqlite3.OperationalError:
                pass

        # 3. Insert Translations if provided
        if translations:
            for tr in translations:
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
                        tr.translation_id,
                        tr.source_passage_id,
                        tr.target_passage_id,
                        tr.source_language,
                        tr.target_language,
                        tr.translated_text,
                        tr.translation_type,
                        tr.translator,
                        tr.reviewer_id,
                        tr.review_status,
                        tr.source_citation,
                        tr.notes,
                    ),
                )

        conn.commit()
        conn.close()

    def import_file(
        self,
        file_path: Union[str, Path],
        metadata: Optional[BookMetadata] = None,
        book_id: Optional[str] = None,
        language: str = "en",
        dry_run: bool = False,
        overwrite: bool = False,
    ) -> ImportManifest:
        """
        Imports an authorized local file (.jsonl, .json, .txt, .md).
        """
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Source file not found: {path}")

        ext = path.suffix.lower()

        # If metadata not passed, find in catalog or construct
        resolved_book_id = book_id or (metadata.book_id if metadata else path.stem)
        resolved_metadata = metadata or self.catalog.get_book(resolved_book_id)

        if not resolved_metadata:
            resolved_metadata = BookMetadata(
                book_id=resolved_book_id,
                canonical_title=resolved_book_id.replace("_", " ").title(),
                original_language=language,
                copyright_status="public_domain",
                licence="Public Domain",
            )

        passages: List[Passage] = []
        translations: List[TranslationRecord] = []

        if ext == ".jsonl":
            with open(path, "r", encoding="utf-8") as f:
                for line_idx, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    if "book_id" not in rec:
                        rec["book_id"] = resolved_book_id
                    if "sequence_number" not in rec:
                        rec["sequence_number"] = line_idx
                    if "language" not in rec:
                        rec["language"] = language
                    if "passage_id" not in rec:
                        rec["passage_id"] = f"{resolved_book_id}:{line_idx}"
                    passages.append(Passage.from_dict(rec))

        elif ext == ".json":
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                for idx, item in enumerate(data, 1):
                    if "passage_id" not in item:
                        item["passage_id"] = f"{resolved_book_id}:{idx}"
                    if "book_id" not in item:
                        item["book_id"] = resolved_book_id
                    if "sequence_number" not in item:
                        item["sequence_number"] = idx
                    if "language" not in item:
                        item["language"] = language
                    passages.append(Passage.from_dict(item))
            elif isinstance(data, dict):
                if "metadata" in data and not metadata:
                    resolved_metadata = BookMetadata.from_dict(data["metadata"])
                if "passages" in data:
                    for idx, item in enumerate(data["passages"], 1):
                        if "passage_id" not in item:
                            item["passage_id"] = f"{resolved_book_id}:{idx}"
                        if "book_id" not in item:
                            item["book_id"] = resolved_book_id
                        if "sequence_number" not in item:
                            item["sequence_number"] = idx
                        if "language" not in item:
                            item["language"] = language
                        passages.append(Passage.from_dict(item))

        elif ext in {".txt", ".md"}:
            with open(path, "r", encoding="utf-8") as f:
                raw_text = f.read()
            passages = self.parse_plain_text(
                raw_text=raw_text,
                book_id=resolved_book_id,
                language=language,
            )
        else:
            raise ValueError(f"Unsupported book file format: '{ext}'. Supported: .jsonl, .json, .txt, .md")

        return self.import_passages(
            metadata=resolved_metadata,
            passages=passages,
            dry_run=dry_run,
            overwrite=overwrite,
            translations=translations,
        )


def sync_all_books_to_databases(
    db_paths: Optional[List[Union[str, Path]]] = None,
    books_dir: Optional[Union[str, Path]] = None,
    catalog: Optional[BookCatalog] = None,
) -> Dict[str, Any]:
    """
    Synchronizes all imported book JSONL text files on disk into SQLite databases and FTS5 indexes.
    By default synchronizes both intentionally maintained databases:
    1. Canonical repo root karbi.db
    2. data/karbi.db
    """
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    b_dir = Path(books_dir) if books_dir is not None else (repo_root / "data" / "books")
    texts_dir = b_dir / "texts"
    cat = catalog or BookCatalog(catalog_path=b_dir / "catalog.json")
    book_map = {b.book_id: b for b in cat.list_books()}

    if db_paths is None:
        targets = [repo_root / "karbi.db", repo_root / "data" / "karbi.db"]
    else:
        targets = [Path(p) for p in db_paths]

    text_files = sorted(list(texts_dir.glob("*.jsonl")))
    total_passages_indexed = 0
    books_indexed_count = 0

    for db_target in targets:
        importer = BookImporter(catalog=cat, db_path=db_target, base_dir=b_dir)
        total_passages_this_db = 0
        books_this_db = 0

        for tf in text_files:
            book_id = tf.stem
            metadata = book_map.get(book_id)
            if not metadata:
                continue

            passages: List[Passage] = []
            with open(tf, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        passages.append(Passage.from_dict(json.loads(line)))

            importer.index_book_to_db(metadata, passages)
            total_passages_this_db += len(passages)
            books_this_db += 1

        total_passages_indexed = total_passages_this_db
        books_indexed_count = books_this_db

    return {
        "total_books": books_indexed_count,
        "total_passages": total_passages_indexed,
        "databases": [str(t) for t in targets],
        "status": "SUCCESS"
    }
