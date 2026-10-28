"""
Command-Line Dictionary & Translation Interface for Karbi (`karbi.cli`)
========================================================================

Provides a CLI for:
- Direct Karbi headword and spelling variant lookup.
- Translation search from English, Hindi, Assamese, and Bengali into Karbi.
- Display of pronunciation (IPA) and recorded bibliographic source citations.
- Unambiguous labeling of unverified translations.
- Clean missing-word handling and JSON export mode.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from karbi.core.dataset import DatasetValidationResult, validate_dataset_files
from karbi.core.db import DEFAULT_DB_PATH
from karbi.core.resources import get_resource_paths
from karbi.core.review import validate_community_review_csv
from karbi.dictionary import DictionaryEntry, lookup, lookup_all
from karbi.translator import (
    SUPPORTED_LANGUAGES,
    TranslationMatch,
    get_supported_languages,
    translate,
)


def _ensure_utf8_output() -> None:
    """Configures stdout and stderr to handle UTF-8 text safely on all platforms."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _format_verification_badge(is_verified: bool, status_text: str = "") -> str:
    """Formats a clear, visible badge for translation verification status."""
    st_upper = status_text.upper().replace("_", " ") if status_text else ""
    if is_verified:
        return f"[{st_upper or 'VERIFIED'}]"
    return "[UNVERIFIED]"


def format_dictionary_entry(entry: DictionaryEntry) -> str:
    """
    Formats a Karbi DictionaryEntry into a clear, readable text report.
    Pronunciation, citations, and verification status for each gloss are prominently displayed.
    """
    lines = [
        "=" * 70,
        f"KARBI HEADWORD: {entry.lemma}",
        "=" * 70,
        f"  Script:         {entry.script.title()}",
        f"  Dialect:        {entry.dialect.title()}",
        f"  Status:         {entry.status}",
    ]

    if entry.phonetics_ipa:
        lines.append(f"  Pronunciation:  {entry.phonetics_ipa}")

    if entry.spelling_variants:
        var_strs = []
        for v in entry.spelling_variants:
            if isinstance(v, dict):
                txt = v.get("text", "")
                ctx = v.get("dialect_or_context", "")
                var_strs.append(f"{txt} ({ctx})" if ctx else txt)
            elif isinstance(v, str):
                var_strs.append(v)
        if var_strs:
            lines.append(f"  Variant(s):     {', '.join(var_strs)}")

    if entry.source_citations:
        lines.append("  Source(s):")
        for cit in entry.source_citations:
            lines.append(f"    - {cit}")
    elif entry.source_citation:
        lines.append(f"  Source(s):      {entry.source_citation}")

    lines.append("")
    lines.append("Senses & Meanings:")

    for idx, sense in enumerate(entry.senses, 1):
        pos = sense.get("part_of_speech", "general")
        sid = sense.get("sense_id", f"S{idx}")
        lines.append(f"  [{idx}] Part of Speech: {pos} ({sid})")

        defs = sense.get("definitions", {})
        gloss_prov = sense.get("gloss_provenance") or {}

        lang_labels = [
            ("en", "English"),
            ("hi", "Hindi"),
            ("as", "Assamese"),
            ("bn", "Bengali"),
        ]

        for code, label in lang_labels:
            items = defs.get(code, [])
            if not items:
                continue

            term_pieces = []
            for item in items:
                if isinstance(item, dict):
                    txt = item.get("text", "")
                    ver = item.get("verified", False)
                    badge = "[VERIFIED]" if ver else "[UNVERIFIED]"
                    term_pieces.append(f"{txt} {badge}")
                elif isinstance(item, str):
                    prov = str(gloss_prov.get(code, "")).lower()
                    is_ver = prov in ("source_attested", "verified", "peer_reviewed")
                    badge = _format_verification_badge(is_ver, prov)
                    term_pieces.append(f"{item} {badge}")

            if term_pieces:
                lines.append(f"      • {label:<10}: {', '.join(term_pieces)}")

        cult = sense.get("cultural_metadata", {})
        if cult and cult.get("cultural_notes"):
            lines.append(f"      • Cultural Note: {cult['cultural_notes']}")

        examples = sense.get("examples", [])
        if examples:
            lines.append("      • Examples:")
            for ex in examples:
                k_text = ex.get("text_karbi", "")
                en_trans = ex.get("translations", {}).get("en", "")
                loc = ex.get("locator", "")
                loc_str = f" ({loc})" if loc else ""
                lines.append(f"        - Karbi:   {k_text}")
                if en_trans:
                    lines.append(f"          English: {en_trans}{loc_str}")

    lines.append("=" * 70)
    return "\n".join(lines)


def format_translation_match(match: TranslationMatch, index: Optional[int] = None) -> str:
    """
    Formats a TranslationMatch into a clear, readable text report.
    Explicitly labels unverified translations.
    """
    prefix = f"{index}. " if index is not None else ""
    lines = [
        f"{prefix}Karbi Lemma:   {match.karbi_lemma} ({match.part_of_speech})",
        f"   Matched Term:  {match.matched_meaning} (from {match.source_language.upper()})",
    ]

    # Verification status
    badge = _format_verification_badge(match.is_verified, match.status)
    lines.append(f"   Gloss Status:  {badge} (Entry Status: {match.entry_status})")
    if not match.is_verified:
        lines.append("   [!] CAUTION:   This translation gloss is unverified and has not been confirmed by native speakers.")

    if match.phonetics_ipa:
        lines.append(f"   Pronunciation: {match.phonetics_ipa}")

    if match.dialect:
        lines.append(f"   Dialect:       {match.dialect.title()}")

    if match.source_citations:
        lines.append("   Source(s):")
        for cit in match.source_citations:
            lines.append(f"     - {cit}")
    elif match.source_citation:
        lines.append(f"   Source(s):     {match.source_citation}")

    # Definitions in all languages
    if match.all_definitions:
        lines.append("   Definitions in other languages:")
        lang_names = {"en": "English", "hi": "Hindi", "as": "Assamese", "bn": "Bengali"}
        for code, l_name in lang_names.items():
            defs = match.all_definitions.get(code, [])
            if not defs:
                continue
            rendered = []
            for d in defs:
                if isinstance(d, dict):
                    txt = d.get("text", "")
                    ver = d.get("verified", False)
                    rendered.append(f"{txt} {'[VERIFIED]' if ver else '[UNVERIFIED]'}")
                elif isinstance(d, str):
                    rendered.append(d)
            if rendered:
                lines.append(f"     • {l_name:<10}: {', '.join(rendered)}")

    if match.cultural_notes:
        lines.append(f"   Cultural Note: {match.cultural_notes}")

    if match.examples:
        lines.append("   Examples:")
        for ex in match.examples:
            k_txt = ex.get("text_karbi", "")
            en_txt = ex.get("translations", {}).get("en", "")
            lines.append(f"     - Karbi:   {k_txt}")
            if en_txt:
                lines.append(f"       English: {en_txt}")

    return "\n".join(lines)


def run_lookup(
    karbi_word: str,
    verified_only: bool = False,
    as_json: bool = False,
    db_path: Optional[Union[str, Path]] = None,
) -> int:
    """
    Performs headword lookup in Karbi dictionary.
    Returns 0 if found, 1 if not found.
    """
    entries = lookup_all(karbi_word, verified_only=verified_only, db_path=db_path)
    if not entries:
        if as_json:
            print(json.dumps({"found": False, "query": karbi_word, "results": []}))
        else:
            filter_msg = " (verified only)" if verified_only else ""
            print(f"No Karbi dictionary entry found for: '{karbi_word}'{filter_msg}.", file=sys.stderr)
            print("Suggestions:", file=sys.stderr)
            print("  - Check diacritics (e.g., 'hèm', 'làng', 'arlèng')", file=sys.stderr)
            print(f"  - Search across translations with: karbi search {karbi_word}", file=sys.stderr)
        return 1

    if as_json:
        entry_dicts = [
            {
                "entry_id": e.entry_id,
                "lemma": e.lemma,
                "script": e.script,
                "dialect": e.dialect,
                "status": e.status,
                "phonetics_ipa": e.phonetics_ipa,
                "senses": e.senses,
                "spelling_variants": e.spelling_variants,
                "source_citations": e.source_citations,
            }
            for e in entries
        ]
        data = {
            "found": True,
            "query": karbi_word,
            "entry": entry_dicts[0],
            "entries": entry_dicts,
        }
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        for idx, e in enumerate(entries):
            if idx > 0:
                print("\n" + "-" * 70 + "\n")
            print(format_dictionary_entry(e))

    return 0


def run_translate(
    query: str,
    from_lang: str = "en",
    verified_only: bool = False,
    as_json: bool = False,
    db_path: Optional[Union[str, Path]] = None,
) -> int:
    """
    Translates from a source language into Karbi.
    Returns 0 if matches found, 1 if no matches found.
    """
    matches = translate(
        query,
        from_lang=from_lang,
        verified_only=verified_only,
        db_path=db_path,
    )

    lang_info = SUPPORTED_LANGUAGES.get(from_lang, {"name": from_lang})
    lang_name = lang_info.get("name", from_lang)

    if not matches:
        if as_json:
            print(json.dumps({
                "found": False,
                "query": query,
                "source_language": from_lang,
                "verified_only": verified_only,
                "results": [],
            }))
        else:
            filter_msg = " (verified only)" if verified_only else ""
            print(
                f"No matching Karbi entries found for: '{query}' [Source: {lang_name} ({from_lang})]{filter_msg}.",
                file=sys.stderr,
            )
            print("Suggestions:", file=sys.stderr)
            print("  - Check spelling or search synonyms", file=sys.stderr)
            print("  - List supported languages with: karbi languages", file=sys.stderr)
            print(f"  - Try multi-language search with: karbi search \"{query}\"", file=sys.stderr)
        return 1

    if as_json:
        out_matches = []
        for m in matches:
            out_matches.append({
                "karbi_lemma": m.karbi_lemma,
                "part_of_speech": m.part_of_speech,
                "matched_meaning": m.matched_meaning,
                "source_language": m.source_language,
                "status": m.status,
                "entry_status": m.entry_status,
                "is_verified": m.is_verified,
                "phonetics_ipa": m.phonetics_ipa,
                "source_citations": m.source_citations,
                "all_definitions": m.all_definitions,
                "cultural_notes": m.cultural_notes,
                "examples": m.examples,
            })
        print(json.dumps({
            "found": True,
            "query": query,
            "source_language": from_lang,
            "count": len(out_matches),
            "results": out_matches,
        }, indent=2, ensure_ascii=False))
    else:
        print("=" * 70)
        print(f"TRANSLATION RESULTS: '{query}' ({lang_name} -> Karbi)")
        print("=" * 70)
        print(f"Found {len(matches)} matching entry/entries:\n")
        for idx, match in enumerate(matches, 1):
            print(format_translation_match(match, index=idx))
            if idx < len(matches):
                print("-" * 50)
        print("=" * 70)

    return 0


def run_search(
    query: str,
    lang: str = "auto",
    verified_only: bool = False,
    as_json: bool = False,
    db_path: Optional[Union[str, Path]] = None,
) -> int:
    """
    Flexible search across Karbi dictionary and translation index.
    If lang='karbi', looks up headwords.
    If lang in ('en', 'hi', 'as', 'bn'), translates from that language.
    If lang='auto', first checks Karbi headwords; if not found or if translation query,
    checks translations across supported languages.
    """
    clean_query = query.strip()
    if not clean_query:
        print("Error: Search query cannot be empty.", file=sys.stderr)
        return 2

    # Explicit Karbi lookup
    if lang == "karbi":
        return run_lookup(clean_query, verified_only=verified_only, as_json=as_json, db_path=db_path)

    # Specific source language
    if lang in ("en", "hi", "as", "bn"):
        return run_translate(clean_query, from_lang=lang, verified_only=verified_only, as_json=as_json, db_path=db_path)

    # Auto search:
    # 1. Try Karbi headword lookup first (including when verified_only is True)
    entries = lookup_all(clean_query, verified_only=verified_only, db_path=db_path)
    if entries:
        return run_lookup(clean_query, verified_only=verified_only, as_json=as_json, db_path=db_path)

    # 2. Try translating from each supported active language
    candidate_langs = ["en", "as", "hi", "bn"]
    for code in candidate_langs:
        matches = translate(clean_query, from_lang=code, verified_only=verified_only, db_path=db_path)
        if matches:
            return run_translate(clean_query, from_lang=code, verified_only=verified_only, as_json=as_json, db_path=db_path)

    # Not found in any language
    if as_json:
        print(json.dumps({
            "found": False,
            "query": clean_query,
            "searched_languages": candidate_langs + ["karbi"],
            "results": [],
        }))
    else:
        print(f"No matching Karbi entries found for '{clean_query}'.", file=sys.stderr)
        print("Searched:", file=sys.stderr)
        print("  - Karbi headwords and contemporary variants", file=sys.stderr)
        print("  - English, Assamese, Hindi, and Bengali translations", file=sys.stderr)
        print("Suggestions:", file=sys.stderr)
        print("  - Specify the source language explicitly: karbi translate <word> --from <en|hi|as|bn>", file=sys.stderr)
        print("  - Check available languages: karbi languages", file=sys.stderr)

    return 1


def run_languages(as_json: bool = False) -> int:
    """Displays registry of supported source languages and their status."""
    langs = get_supported_languages()
    if as_json:
        print(json.dumps(langs, indent=2))
        return 0

    print("=" * 60)
    print("SUPPORTED SOURCE LANGUAGES FOR KARBI TRANSLATION")
    print("=" * 60)
    for code, info in langs.items():
        name = info.get("name", code)
        script = info.get("script", "Unknown")
        status = info.get("status", "unknown").replace("_", " ").title()
        print(f"  • [{code}] {name:<12} (Script: {script:<18}) Status: {status}")
    print("=" * 60)
    return 0


def run_validate(
    lexicon_paths: Optional[Sequence[Union[str, Path]]] = None,
    source_paths: Optional[Sequence[Union[str, Path]]] = None,
    review_csv: Optional[Union[str, Path]] = None,
    strict: bool = False,
    verbose: bool = False,
    as_json: bool = False,
) -> int:
    """
    Validates JSONL dataset files or community review CSV submissions for syntax,
    schema, unique IDs, source citations, and cross-reference integrity.
    Audits unverified translations and AI candidates. Does NOT modify or rewrite data.
    """
    if review_csv:
        c_res = validate_community_review_csv(review_csv)
        if as_json:
            print(json.dumps(c_res.as_dict(), indent=2, ensure_ascii=False))
        else:
            print(c_res.report(verbose=verbose or not c_res.is_valid))
        return 0 if c_res.is_valid else 1

    # If paths not explicitly provided, discover default dataset resources
    if not lexicon_paths or not source_paths:
        def_lex, def_src = get_resource_paths()
        lexicon_paths = lexicon_paths or def_lex
        source_paths = source_paths or def_src

    # Expand any directory paths to *.jsonl files
    final_lex: List[Path] = []
    for lp in lexicon_paths:
        p = Path(lp)
        if p.is_dir():
            final_lex.extend(sorted(p.glob("*.jsonl")))
        elif p.is_file():
            final_lex.append(p)
        else:
            final_lex.append(p)

    final_src: List[Path] = []
    for sp in source_paths:
        p = Path(sp)
        if p.is_dir():
            final_src.extend(sorted(p.glob("*.jsonl")))
        elif p.is_file():
            final_src.append(p)
        else:
            final_src.append(p)

    res = validate_dataset_files(lexicon_paths=final_lex, source_paths=final_src)

    if as_json:
        print(json.dumps(res.as_dict(), indent=2, ensure_ascii=False))
    else:
        print(res.report(verbose=verbose or not res.is_valid))

    if not res.is_valid:
        return 1

    if strict and (res.unverified_glosses_count > 0 or len(res.missing_citation_entries) > 0):
        print(
            f"Error: Strict validation mode active. "
            f"Found {res.unverified_glosses_count} unverified gloss(es) and "
            f"{len(res.missing_citation_entries)} entry/entries missing citations.",
            file=sys.stderr,
        )
        return 1

    return 0


# =========================================================================
# Digital Book Library CLI Handlers
# =========================================================================

def run_books_list(
    status: Optional[str] = None,
    language: Optional[str] = None,
    as_json: bool = False,
) -> int:
    """Lists books registered in the catalogue."""
    from karbi.books.catalog import BookCatalog

    cat = BookCatalog()
    books = cat.list_books(import_status=status, language=language)

    if as_json:
        print(json.dumps([b.to_dict() for b in books], indent=2, ensure_ascii=False))
        return 0

    print("=" * 80)
    print(f"KARBI DIGITAL BOOK LIBRARY CATALOGUE ({len(books)} works registered)")
    print("=" * 80)
    for b in books:
        status_badge = f"[{b.import_status}]"
        counts = f"{b.imported_chapters_count} ch / {b.imported_passages_count} pass" if b.imported_passages_count > 0 else "catalog only"
        author_or_trans = b.author or b.translator or "Unknown"
        print(f"  • {b.book_id:<28} {status_badge:<18} ({b.original_language.upper()}) {b.canonical_title}")
        print(f"    By: {author_or_trans:<30} | {counts:<16} | Licence: {b.licence}")
    print("=" * 80)
    return 0


def run_books_info(book_id: str, as_json: bool = False) -> int:
    """Displays detailed metadata for a registered book."""
    from karbi.books.catalog import BookCatalog

    cat = BookCatalog()
    b = cat.get_book(book_id)
    if not b:
        print(f"Error: Book '{book_id}' not found in catalogue.", file=sys.stderr)
        return 1

    if as_json:
        print(json.dumps(b.to_dict(), indent=2, ensure_ascii=False))
        return 0

    print("=" * 70)
    print(f"BOOK METADATA: {b.canonical_title}")
    print("=" * 70)
    print(f"  Book ID:          {b.book_id}")
    print(f"  Canonical Title:  {b.canonical_title}")
    if b.alternate_titles:
        alt_str = ", ".join(f"{k}: {v}" for k, v in b.alternate_titles.items())
        print(f"  Alternate Titles: {alt_str}")
    print(f"  Attributed Author:{b.author or 'Unknown'}")
    print(f"  Original Lang:    {b.original_language.upper()} (Script: {b.original_script})")
    print(f"  Document Type:    {b.document_type.title()}")
    if b.translator:
        print(f"  Translator:       {b.translator}")
    if b.editor:
        print(f"  Editor:           {b.editor}")
    if b.edition:
        print(f"  Edition:          {b.edition}")
    if b.publisher:
        print(f"  Publisher:        {b.publisher} ({b.publication_year or 'n.d.'})")
    print(f"  Copyright Status: {b.copyright_status}")
    print(f"  Licence:          {b.licence}")
    print(f"  Import Status:    {b.import_status}")
    print(f"  Imported Text:    {b.imported_chapters_count} chapter(s), {b.imported_passages_count} passage(s)")
    if b.content_checksum:
        print(f"  SHA-256 Checksum: {b.content_checksum}")
    if b.source_url:
        print(f"  Source Archive:   {b.source_url}")
    if b.notes:
        print(f"  Notes:            {b.notes}")
    if b.missing_sections:
        print(f"  Missing Sections: {', '.join(b.missing_sections)}")
    print("=" * 70)
    return 0


def run_books_read(
    book_id: str,
    chapter: Optional[int] = None,
    limit: Optional[int] = None,
    offset: int = 0,
    as_json: bool = False,
) -> int:
    """Reads and formats passages from an imported book."""
    from karbi.books.reader import BookReader

    reader = BookReader()
    passages = reader.get_book_passages(book_id=book_id, chapter=chapter, limit=limit, offset=offset)

    if not passages:
        print(f"No passages found for book '{book_id}' (chapter={chapter}).", file=sys.stderr)
        return 1

    if as_json:
        print(json.dumps([p.to_dict() for p in passages], indent=2, ensure_ascii=False))
        return 0

    print("=" * 70)
    print(f"READING BOOK: {book_id.upper()}" + (f" (Chapter {chapter})" if chapter else ""))
    print("=" * 70)
    for p in passages:
        print(reader.format_passage(p))
        print()
    return 0


def run_books_search(
    query: str,
    book_id: Optional[str] = None,
    language: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    as_json: bool = False,
) -> int:
    """Searches book passages using full-text search (FTS5)."""
    from karbi.books.search import BookSearchEngine

    searcher = BookSearchEngine()
    results = searcher.search_book_text(
        query=query,
        book_id=book_id,
        language=language,
        limit=limit,
        offset=offset,
    )

    if as_json:
        print(json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False))
        return 0

    print("=" * 80)
    print(f"BOOK TEXT SEARCH: '{query}' ({len(results)} matches found)")
    if book_id:
        print(f"Filter Book: {book_id}")
    if language:
        print(f"Filter Language: {language}")
    print("=" * 80)

    if not results:
        print("  No matching passages found in imported books.")
        return 0

    for idx, r in enumerate(results, 1):
        loc = f"Ch. {r.chapter_number}" if r.chapter_number else ""
        if r.verse:
            loc += f", Verse {r.verse}"
        elif r.paragraph:
            loc += f", Para {r.paragraph}"
        loc_str = f"({loc})" if loc else ""

        print(f"[{idx}] {r.book_title} {loc_str} | ID: {r.passage_id}")
        print(f"    Snippet: \"{r.matched_snippet}\"")
        print()

    return 0


def run_books_import(
    file_path: str,
    book_id: Optional[str] = None,
    title: Optional[str] = None,
    language: str = "en",
    dry_run: bool = False,
    overwrite: bool = False,
    as_json: bool = False,
) -> int:
    """Imports an authorized book text file into the repository."""
    from karbi.books.importer import BookImporter
    from karbi.books.models import BookMetadata

    meta = None
    if book_id:
        meta = BookMetadata(
            book_id=book_id,
            canonical_title=title or book_id.replace("_", " ").title(),
            original_language=language,
            copyright_status="public_domain",
            licence="Public Domain",
        )

    importer = BookImporter()
    try:
        manifest = importer.import_file(
            file_path=file_path,
            metadata=meta,
            book_id=book_id,
            language=language,
            dry_run=dry_run,
            overwrite=overwrite,
        )
    except Exception as ex:
        print(f"Error during import: {ex}", file=sys.stderr)
        return 1

    if as_json:
        print(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False))
        return 0

    mode_str = "[DRY-RUN]" if manifest.dry_run else "[IMPORTED]"
    print("=" * 60)
    print(f"BOOK IMPORT SUCCESSFUL {mode_str}")
    print("=" * 60)
    print(f"  Book ID:        {manifest.book_id}")
    print(f"  Title:          {manifest.canonical_title}")
    print(f"  Total Chapters: {manifest.total_chapters}")
    print(f"  Total Passages: {manifest.total_passages}")
    print(f"  Checksum:       {manifest.sha256_checksum[:16]}...")
    print(f"  Source Path:    {manifest.source_file_path}")
    print("=" * 60)
    return 0


def run_books_validate(
    book_id: Optional[str] = None,
    as_json: bool = False,
) -> int:
    """Validates book catalogue or a specific book."""
    from karbi.books.validation import validate_book as _vb, validate_book_catalog as _vbc

    if book_id:
        res = _vb(book_id)
        if as_json:
            print(json.dumps(res.as_dict(), indent=2, ensure_ascii=False))
        else:
            print(res.report())
        return 0 if res.is_valid else 1

    res_all = _vbc()
    if as_json:
        print(json.dumps(res_all, indent=2, ensure_ascii=False))
    else:
        status_str = "PASSED" if res_all["is_valid"] else "FAILED"
        print("=" * 60)
        print(f"BOOK CATALOGUE VALIDATION: {status_str} ({res_all['total_books']} books audited)")
        print("=" * 60)
        for b_id, b_res in res_all["book_results"].items():
            b_st = "OK" if b_res["is_valid"] else "INVALID"
            print(f"  • {b_id:<28} [{b_st}] {b_res['total_chapters']} ch, {b_res['total_passages']} pass")
            if b_res["errors"]:
                for err in b_res["errors"]:
                    print(f"      ERROR: {err}")
    return 0 if res_all["is_valid"] else 1


def run_books_stats(
    book_id: Optional[str] = None,
    as_json: bool = False,
) -> int:
    """Displays statistics of the book library."""
    from karbi.books.catalog import BookCatalog

    cat = BookCatalog()
    if book_id:
        b = cat.get_book(book_id)
        if not b:
            print(f"Error: Book '{book_id}' not found.", file=sys.stderr)
            return 1
        stats = {
            "book_id": b.book_id,
            "title": b.canonical_title,
            "status": b.import_status,
            "chapters": b.imported_chapters_count,
            "passages": b.imported_passages_count,
            "licence": b.licence,
            "checksum": b.content_checksum,
        }
    else:
        stats = cat.get_stats()

    if as_json:
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return 0

    print("=" * 60)
    print("KARBI DIGITAL BOOK LIBRARY STATISTICS")
    print("=" * 60)
    for k, v in stats.items():
        if isinstance(v, dict):
            print(f"  {k.replace('_', ' ').title()}:")
            for sub_k, sub_v in v.items():
                print(f"    - {sub_k}: {sub_v}")
        else:
            print(f"  {k.replace('_', ' ').title():<28}: {v}")
    print("=" * 60)
    return 0


def run_books_audit(
    book_id: Optional[str] = None,
    as_json: bool = False,
    no_save: bool = False,
) -> int:
    """Runs a thorough data integrity and provenance audit on imported books."""
    from karbi.books.audit import BookAuditor

    auditor = BookAuditor()
    if book_id:
        res = auditor.audit_book(book_id)
        if as_json:
            print(json.dumps(res.to_dict(), indent=2, ensure_ascii=False))
            return 0 if res.overall_status in ("VERIFIED", "PARTIALLY_VERIFIED", "NOT_APPLICABLE") else 1

        print("=" * 70)
        print(f"BOOK AUDIT: {res.canonical_title} [{res.overall_status}]")
        print("=" * 70)
        print(f"  Book ID:          {res.book_id}")
        print(f"  Overall Status:   {res.overall_status}")
        print(f"  Import Status:    {res.import_status}")
        print(f"  Chapters (rec/act): {res.total_chapters_recorded} / {res.total_chapters_actual}")
        print(f"  Passages (rec/act): {res.total_passages_recorded} / {res.total_passages_actual}")
        print(f"  Checksum Matches: {res.checksum_matches} ({res.content_checksum_actual[:16] if res.content_checksum_actual else 'N/A'}...)")
        print(f"  Unique Passages:  {res.unique_passage_ids} (Monotonic: {res.monotonic_sequence})")
        print(f"  Footnotes Sep:    {res.footnotes_accounted_for} ({res.annotations_file or 'None'})")
        print(f"  Combined Verses:  {res.combined_verses_accounted_for}")
        print(f"  Consent Verified: {res.community_consent_verified}")
        print(f"  Completeness:     {res.completeness_statement}")
        if res.errors:
            print("  ERRORS:")
            for err in res.errors:
                print(f"    - {err}")
        if res.warnings:
            print("  WARNINGS:")
            for w in res.warnings:
                print(f"    - {w}")
        print("=" * 70)
        return 0 if res.overall_status in ("VERIFIED", "PARTIALLY_VERIFIED", "NOT_APPLICABLE") else 1

    report = auditor.audit_all(write_report=(not no_save))
    if as_json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return 0 if report.failed_works_count == 0 else 1

    print("=" * 80)
    print("KARBI DIGITAL BOOK LIBRARY AUDIT REPORT")
    print(f"Timestamp: {report.audit_timestamp}")
    print("=" * 80)
    print(f"Total Catalogue Works: {report.total_catalog_works}")
    print(f"Imported Works Audited: {report.imported_works_audited}")
    print(f"  • Verified:           {report.verified_works_count}")
    print(f"  • Partially Verified: {report.partially_verified_count}")
    print(f"  • Failed:             {report.failed_works_count}")
    print(f"  • Not Applicable:     {report.not_applicable_count}")
    print(f"Total Authentic Passages: {report.total_verified_passages}")
    print(f"Total Authentic Chapters: {report.total_verified_chapters}")
    print("-" * 80)
    print(f"Security Audit:   [{report.security_audit.get('status')}] TLS Verification Enforced: {report.security_audit.get('tls_verification_enforced')}")
    print(f"Consent Audit:    [{report.consent_audit.get('status')}] Historical Isolated: {report.consent_audit.get('historical_sources_isolated_from_consent')}")
    print(f"Lexicon Audit:    [{report.lexicon_isolation_audit.get('status')}] Core Lexicon Isolated: {report.lexicon_isolation_audit.get('core_lexicon_isolated')}")
    print("-" * 80)
    print(f"{'Book ID':<24} {'Status':<20} {'Chapters':<10} {'Passages':<10} {'Integrity'}")
    print("-" * 80)
    for b_id, b_res in report.book_results.items():
        if b_res.import_status == "CATALOG_ONLY":
            continue
        chk_str = "OK" if b_res.checksum_matches and b_res.unique_passage_ids else "WARN"
        print(f"{b_id:<24} [{b_res.overall_status:<18}] {b_res.total_chapters_actual:<10} {b_res.total_passages_actual:<10} {chk_str}")
        if b_res.errors:
            for err in b_res.errors:
                print(f"    ERROR: {err}")
    print("=" * 80)
    if not no_save:
        print("Audit report written to data/books/audit_report.json")
    return 0 if report.failed_works_count == 0 else 1


def run_books_sync(as_json: bool = False) -> int:
    """Synchronizes all imported book passages to SQLite databases."""
    from karbi.books.importer import sync_all_books_to_databases
    try:
        res = sync_all_books_to_databases()
        if as_json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
            return 0
        print("=" * 60)
        print("DATABASE SYNCHRONIZATION COMPLETE")
        print("=" * 60)
        print(f"Total Books Synced:    {res['total_books']}")
        print(f"Total Passages Synced: {res['total_passages']}")
        print("Target Databases:")
        for db in res["databases"]:
            print(f"  • {db}")
        print("=" * 60)
        return 0
    except Exception as exc:
        if as_json:
            print(json.dumps({"status": "FAILED", "error": str(exc)}, indent=2))
        else:
            print(f"ERROR during database synchronization: {exc}", file=sys.stderr)
        return 1


def run_books(args: argparse.Namespace) -> int:
    """Dispatches 'karbi books' subcommands."""
    book_cmd = getattr(args, "book_command", None)
    if not book_cmd or book_cmd == "list":
        return run_books_list(
            status=getattr(args, "status", None),
            language=getattr(args, "language", None),
            as_json=getattr(args, "json", False),
        )
    elif book_cmd == "info":
        return run_books_info(args.book_id, as_json=getattr(args, "json", False))
    elif book_cmd == "read":
        return run_books_read(
            args.book_id,
            chapter=getattr(args, "chapter", None),
            limit=getattr(args, "limit", None),
            offset=getattr(args, "offset", 0),
            as_json=getattr(args, "json", False),
        )
    elif book_cmd == "search":
        return run_books_search(
            args.query,
            book_id=getattr(args, "book", None),
            language=getattr(args, "language", None),
            limit=getattr(args, "limit", 20),
            offset=getattr(args, "offset", 0),
            as_json=getattr(args, "json", False),
        )
    elif book_cmd == "import":
        return run_books_import(
            file_path=args.file,
            book_id=getattr(args, "book_id", None),
            title=getattr(args, "title", None),
            language=getattr(args, "language", "en"),
            dry_run=getattr(args, "dry_run", False),
            overwrite=getattr(args, "overwrite", False),
            as_json=getattr(args, "json", False),
        )
    elif book_cmd == "validate":
        return run_books_validate(
            book_id=getattr(args, "book_id", None),
            as_json=getattr(args, "json", False),
        )
    elif book_cmd == "stats":
        return run_books_stats(
            book_id=getattr(args, "book_id", None),
            as_json=getattr(args, "json", False),
        )
    elif book_cmd == "audit":
        return run_books_audit(
            book_id=getattr(args, "book_id", None),
            as_json=getattr(args, "json", False),
            no_save=getattr(args, "no_save", False),
        )
    elif book_cmd == "sync":
        return run_books_sync(as_json=getattr(args, "json", False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Constructs the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="karbi",
        description="Command-line dictionary and multilingual translation tool for the Karbi language.",
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )

    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # 1. lookup subcommand
    p_lookup = subparsers.add_parser("lookup", help="Look up a Karbi headword or spelling variant.")
    p_lookup.add_argument("word", help="The Karbi word to look up (e.g. 'arlèng', 'hèm', 'làng', 'hem')")
    p_lookup.add_argument(
        "--verified-only",
        action="store_true",
        help="Only return entries verified by registered authorities or source-attested records",
    )
    p_lookup.add_argument("--json", action="store_true", help="Output results in JSON format")

    # 2. translate subcommand
    p_trans = subparsers.add_parser("translate", help="Translate from English, Hindi, Assamese, or Bengali into Karbi.")
    p_trans.add_argument("query", help="Word or concept to translate into Karbi (e.g. 'water', 'घर', 'পানী')")
    p_trans.add_argument(
        "--from", "-l", "--lang", "--from-lang",
        dest="from_lang",
        default="en",
        choices=["en", "hi", "as", "bn"],
        help="Source language code (default: 'en')",
    )
    p_trans.add_argument(
        "--verified-only",
        action="store_true",
        help="Only return entries verified by registered authorities",
    )
    p_trans.add_argument("--json", action="store_true", help="Output results in JSON format")

    # 3. search subcommand
    p_search = subparsers.add_parser("search", help="Search across Karbi headwords and translation glosses.")
    p_search.add_argument("query", help="Search term")
    p_search.add_argument(
        "--lang", "-l",
        default="auto",
        choices=["auto", "karbi", "en", "hi", "as", "bn"],
        help="Language to search in ('auto', 'karbi', 'en', 'hi', 'as', 'bn')",
    )
    p_search.add_argument(
        "--verified-only",
        action="store_true",
        help="Only return verified translations",
    )
    p_search.add_argument("--json", action="store_true", help="Output results in JSON format")

    # 4. languages subcommand
    p_langs = subparsers.add_parser("languages", help="List supported translation source languages.")
    p_langs.add_argument("--json", action="store_true", help="Output results in JSON format")

    # 5. validate subcommand
    p_val = subparsers.add_parser("validate", help="Validate dataset files for schema, unique IDs, citations, and unverified glosses.")
    p_val.add_argument("--lexicon", "-l", nargs="*", help="Path(s) to lexicon JSONL file(s) or directory")
    p_val.add_argument("--sources", "-s", nargs="*", help="Path(s) to sources JSONL file(s) or directory")
    p_val.add_argument("--review-csv", help="Path to community review CSV file to audit and validate")
    p_val.add_argument("--strict", action="store_true", help="Fail with non-zero exit code if unverified glosses or missing citations exist")
    p_val.add_argument("--verbose", "-V", action="store_true", help="Show detailed breakdown of missing citations and errors")
    p_val.add_argument("--json", action="store_true", help="Output validation report in JSON format")

    # 6. books subcommand
    p_books = subparsers.add_parser("books", help="Browse, read, search, import, and validate digital books.")
    books_sub = p_books.add_subparsers(dest="book_command", help="Book operations")

    # karbi books list
    b_list = books_sub.add_parser("list", help="List registered books in the catalogue.")
    b_list.add_argument("--status", choices=["CATALOG_ONLY", "PARTIALLY_IMPORTED", "FULLY_IMPORTED"], help="Filter by import status")
    b_list.add_argument("--language", "-l", help="Filter by language code")
    b_list.add_argument("--json", action="store_true", help="Output in JSON format")

    # karbi books info <book_id>
    b_info = books_sub.add_parser("info", help="Show full metadata for a book.")
    b_info.add_argument("book_id", help="Book ID (e.g. 'bhagavad_gita', 'ramayana')")
    b_info.add_argument("--json", action="store_true", help="Output in JSON format")

    # karbi books read <book_id>
    b_read = books_sub.add_parser("read", help="Read passages from an imported book.")
    b_read.add_argument("book_id", help="Book ID to read")
    b_read.add_argument("--chapter", "-c", type=int, help="Chapter number")
    b_read.add_argument("--limit", "-n", type=int, help="Limit number of passages displayed")
    b_read.add_argument("--offset", type=int, default=0, help="Passage offset")
    b_read.add_argument("--json", action="store_true", help="Output in JSON format")

    # karbi books search <query>
    b_search = books_sub.add_parser("search", help="Full-text search across book passages.")
    b_search.add_argument("query", help="Text query to search for")
    b_search.add_argument("--book", "-b", help="Filter by book ID")
    b_search.add_argument("--language", "-l", help="Filter by language code")
    b_search.add_argument("--limit", "-n", type=int, default=20, help="Max results")
    b_search.add_argument("--offset", type=int, default=0, help="Result offset")
    b_search.add_argument("--json", action="store_true", help="Output in JSON format")

    # karbi books import <file>
    b_import = books_sub.add_parser("import", help="Import a book text file (.jsonl, .json, .txt, .md).")
    b_import.add_argument("file", help="Path to book text file")
    b_import.add_argument("--book-id", help="Assign a specific book ID")
    b_import.add_argument("--title", help="Book canonical title")
    b_import.add_argument("--language", "-l", default="en", help="Language code (default: 'en')")
    b_import.add_argument("--dry-run", action="store_true", help="Report changes without writing to disk or database")
    b_import.add_argument("--overwrite", action="store_true", help="Overwrite existing book passages")
    b_import.add_argument("--json", action="store_true", help="Output manifest in JSON format")

    # karbi books validate
    b_validate = books_sub.add_parser("validate", help="Validate book catalogue or a specific imported book.")
    b_validate.add_argument("--book-id", "-b", help="Specific book ID to validate")
    b_validate.add_argument("--json", action="store_true", help="Output in JSON format")

    # karbi books stats
    b_stats = books_sub.add_parser("stats", help="Display book library metrics and statistics.")
    b_stats.add_argument("--book-id", "-b", help="Specific book ID for statistics")
    b_stats.add_argument("--json", action="store_true", help="Output in JSON format")

    # karbi books audit
    b_audit = books_sub.add_parser("audit", help="Run thorough integrity and provenance audit on imported books.")
    b_audit.add_argument("--book-id", "-b", help="Specific book ID to audit")
    b_audit.add_argument("--json", action="store_true", help="Output audit report in JSON format")
    b_audit.add_argument("--no-save", action="store_true", help="Do not write audit_report.json to disk")

    # karbi books sync
    b_sync = books_sub.add_parser("sync", help="Synchronize and rebuild all imported book passages into SQLite databases.")
    b_sync.add_argument("--json", action="store_true", help="Output sync summary in JSON format")

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """
    Main entry point for the Karbi CLI.
    Supports subcommands ('lookup', 'translate', 'search', 'languages', 'validate', 'books')
    as well as direct queries ('karbi arlèng', 'karbi water').
    """
    _ensure_utf8_output()
    parser = build_parser()

    if argv is None:
        argv = sys.argv[1:]

    # If invoked with no arguments, display help
    if not argv:
        parser.print_help()
        return 0

    known_subcmds = {"lookup", "translate", "search", "languages", "validate", "books", "-h", "--help", "-v", "--version"}

    # Rewrite direct word queries to 'search' for immediate usability
    if argv and argv[0] not in known_subcmds:
        if argv[0].startswith("-"):
            # Flag passed directly e.g. `karbi --json water`
            argv = ["search"] + list(argv)
        else:
            # Word passed directly e.g. `karbi water` or `karbi arlèng`
            argv = ["search"] + list(argv)

    args = parser.parse_args(argv)

    if args.subcommand == "lookup":
        return run_lookup(args.word, verified_only=args.verified_only, as_json=args.json)
    elif args.subcommand == "translate":
        return run_translate(
            args.query,
            from_lang=args.from_lang,
            verified_only=args.verified_only,
            as_json=args.json,
        )
    elif args.subcommand == "search":
        return run_search(
            args.query,
            lang=args.lang,
            verified_only=args.verified_only,
            as_json=args.json,
        )
    elif args.subcommand == "languages":
        return run_languages(as_json=args.json)
    elif args.subcommand == "validate":
        return run_validate(
            lexicon_paths=args.lexicon,
            source_paths=args.sources,
            review_csv=getattr(args, "review_csv", None),
            strict=args.strict,
            verbose=args.verbose,
            as_json=args.json,
        )
    elif args.subcommand == "books":
        return run_books(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
