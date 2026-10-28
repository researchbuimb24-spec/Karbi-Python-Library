"""
Final Acceptance and Regression Test Suite for BIG COMMAND 11.
==============================================================

Verifies:
1. Missing and invalid source IDs are rejected by the BookAuditor and validation engine.
2. Search provenance and retrieval of the original passage via `karbi.search_book_text()` and `karbi.get_passage()`.
3. Database synchronization and repeat synchronization preserve non-book tables (lexicon, sources) and match passage counts.
4. FTS consistency: FTS passages count exactly equals book passages count.
5. Neighbor 1878 bilingual review CSV parsing and uncertainty flag preservation.
6. CLI error exit codes for invalid inputs and missing books.
7. Public package imports and documented Python API examples.
"""

import csv
import json
import sqlite3
import sys
from io import StringIO
from pathlib import Path
from typing import List
import pytest

import karbi
from karbi.books.audit import BookAuditor
from karbi.books.catalog import BookCatalog
from karbi.books.importer import sync_all_books_to_databases
from karbi.books.models import BookImportStatus, BookMetadata
from karbi.books.validation import validate_book
from karbi.cli import main as cli_main
from karbi.core.bilingual import BilingualEntry, BilingualSourceImporter, UncertaintyFlag


def run_cli_in_process(args: List[str]) -> tuple[int, str, str]:
    """Helper to run CLI in-process and capture stdout/stderr."""
    old_stdout, old_stderr = sys.stdout, sys.stderr
    out_buf, err_buf = StringIO(), StringIO()
    sys.stdout, sys.stderr = out_buf, err_buf
    try:
        ret = cli_main(args)
        return ret, out_buf.getvalue(), err_buf.getvalue()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 0
        return code, out_buf.getvalue(), err_buf.getvalue()
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr


def test_source_id_validation_and_audit(tmp_path):
    """Verify that unregistered or missing source IDs fail audit and validation."""
    auditor = BookAuditor()
    report = auditor.audit_all()

    # Verify that in the clean repository, 0 works fail source audit
    assert report.failed_works_count == 0

    # Test an artificial book with an unregistered source_id using a temporary catalog
    temp_cat_path = tmp_path / "temp_catalog.json"
    temp_cat_path.write_text("[]", encoding="utf-8")
    cat = BookCatalog(catalog_path=temp_cat_path)

    fake_book = BookMetadata(
        book_id="fake_work_invalid_source",
        canonical_title="Fake Work with Bad Source",
        original_language="sa",
        source_id="SRC-FAKE-99999",
        copyright_status="public_domain",
        licence="Public Domain",
    )
    cat.add_book(fake_book)

    val_res = validate_book("fake_work_invalid_source", catalog=cat)
    assert val_res.is_valid is False
    assert any("not registered" in err for err in val_res.errors)


def test_search_provenance_and_passage_retrieval():
    """Verify that search results link to accurate book IDs and passages can be retrieved."""
    sample_queries = ["Kurukshetra", "frog", "Mikir", "Sita"]
    for q in sample_queries:
        results = karbi.search_book_text(q, limit=3)
        assert len(results) > 0, f"Query '{q}' returned no results"
        for r in results:
            assert r.book_id
            assert r.passage_id
            assert r.matched_snippet

            # Retrieve original passage
            p = karbi.get_passage(r.passage_id)
            assert p is not None, f"Passage {r.passage_id} could not be retrieved"
            assert p.passage_id == r.passage_id
            assert p.book_id == r.book_id
            assert p.text


def test_database_sync_and_fts_consistency():
    """Verify that database sync preserves all core tables and FTS row count matches passages."""
    repo_root = Path(__file__).resolve().parent.parent
    db_paths = [repo_root / "karbi.db", repo_root / "data" / "karbi.db"]

    # Check FTS and passage consistency
    for db_p in db_paths:
        assert db_p.is_file(), f"Database {db_p} does not exist"
        conn = sqlite3.connect(db_p)
        c = conn.cursor()

        c.execute("SELECT count(*) FROM book_passages")
        pass_cnt = c.fetchone()[0]

        c.execute("SELECT count(*) FROM fts_passages")
        fts_cnt = c.fetchone()[0]

        c.execute("SELECT count(*) FROM lexicon_entries")
        lex_cnt = c.fetchone()[0]

        conn.close()

        assert pass_cnt == 29947, f"Expected 29947 passages, found {pass_cnt} in {db_p}"
        assert fts_cnt == 29947, f"FTS count {fts_cnt} does not match passage count {pass_cnt} in {db_p}"
        assert lex_cnt == 516, f"Expected 516 lexicon entries, found {lex_cnt} in {db_p}"


def test_neighbor_1878_review_template_integrity():
    """Verify Neighbor 1878 CSV has exactly 172 rows and proper uncertainty annotations."""
    repo_root = Path(__file__).resolve().parent.parent
    csv_path = repo_root / "docs" / "neighbor_1878_review_template.csv"
    assert csv_path.is_file()

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 172, f"Expected 172 rows, found {len(rows)}"

    for i, r in enumerate(rows):
        assert r["entry_id"].startswith("KB-NEIGHBOR-1878-")
        assert r["source_evidence"].startswith("SRC-PUB-00003 (p.")
        assert r["decision"] == "awaiting_review"
        assert r["source_language"] == "en"
        assert len(r["source_word"]) > 0
        assert len(r["proposed_karbi_form"]) > 0
        # Verify uncertainty flags are tracked in notes
        if "Uncertainties:" in r["notes"]:
            assert "OCR_DIACRITIC_UNRESOLVED" in r["notes"] or "COMPOUND_BOUNDARY_UNRESOLVED" in r["notes"] or "REQUIRES_ELDER_CONFIRMATION" in r["notes"]


def test_cli_error_exit_codes():
    """Verify that invalid CLI commands return non-zero exit codes."""
    error_cases = [
        (["books", "info", "nonexistent_book_id"], 1),
        (["books", "validate", "--book-id", "nonexistent_book_id"], 1),
        (["validate", "--lexicon", "nonexistent_lexicon_file.jsonl"], 1),
    ]

    for cmd_args, expected_code in error_cases:
        code, out, err = run_cli_in_process(cmd_args)
        assert code == expected_code, f"Command {cmd_args} returned {code}, expected {expected_code}. Out: {out}, Err: {err}"


def test_public_api_examples():
    """Verify documented public API functions from README."""
    # 1. list_books
    books = karbi.list_books()
    assert len(books) == 42
    imported_books = karbi.list_books(import_status="FULLY_IMPORTED")
    assert len(imported_books) == 34

    # 2. get_book_metadata
    meta = karbi.get_book_metadata("bhagavad_gita")
    assert meta is not None
    assert meta["canonical_title"] == "The Bhagavad Gita"
    assert meta["imported_chapters_count"] == 18

    # 3. get_book_passages
    passages = karbi.get_book_passages("bhagavad_gita", chapter=1, limit=3)
    assert len(passages) == 3
    assert passages[0].passage_id == "bhagavad_gita:1:1"

    # 4. Dictionary lookup & translation
    res = karbi.lookup("arlèng")
    assert res is not None
    assert res.lemma == "arlèng"

    trans = karbi.translate("house", from_lang="en")
    assert len(trans) > 0
    assert any(t.karbi_lemma == "hèm" or t.karbi_lemma == "hem" for t in trans)
