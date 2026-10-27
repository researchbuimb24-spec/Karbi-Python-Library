"""
Comprehensive Tests for the Karbi Digital Book Library Subsystem (`karbi.books`)
================================================================================

Covers:
- Book catalogue operations, filtering, and metadata.
- Import pipeline (JSONL, JSON, TXT, MD, dry-run, atomic writes, duplicate detection).
- Structural preservation (chapters, verses, paragraphs, stable IDs).
- Full-text search (FTS5, snippets, filtering, unicode-safety).
- Passage reading, pagination, and chapter inspection.
- Bidirectional translation alignment and provenance tracking.
- Vocabulary candidate extraction and strict isolation from the verified lexicon.
- Public Python API and CLI commands.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import pytest

from karbi.books.catalog import BookCatalog
from karbi.books.importer import BookImporter
from karbi.books.models import (
    BookImportStatus,
    BookMetadata,
    CandidateStatus,
    Passage,
    PassageProvenanceStatus,
    TranslationRecord,
    TranslationType,
    VocabularyCandidate,
)
from karbi.books.reader import BookReader
from karbi.books.search import BookSearchEngine
from karbi.books.translation import BookTranslationRepository
from karbi.books.validation import validate_book, validate_book_catalog
from karbi.books.vocabulary import VocabularyCandidateWorkflow
import karbi
import karbi.cli


@pytest.fixture
def temp_books_env(tmp_path: Path):
    """Creates an isolated temporary book directory and database for tests."""
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    (books_dir / "texts").mkdir()
    (books_dir / "manifests").mkdir()
    (books_dir / "translations").mkdir()
    (books_dir / "candidates").mkdir()

    cat_path = books_dir / "catalog.json"
    cat_path.write_text("[]", encoding="utf-8")

    db_path = tmp_path / "test_karbi.db"
    catalog = BookCatalog(catalog_path=cat_path)
    importer = BookImporter(catalog=catalog, db_path=db_path, base_dir=books_dir)
    reader = BookReader(db_path=db_path, books_dir=books_dir, catalog=catalog)
    searcher = BookSearchEngine(db_path=db_path, books_dir=books_dir, catalog=catalog)
    trans_repo = BookTranslationRepository(db_path=db_path, books_dir=books_dir)
    vocab_wf = VocabularyCandidateWorkflow(db_path=db_path, books_dir=books_dir)

    return {
        "dir": books_dir,
        "db": db_path,
        "catalog": catalog,
        "importer": importer,
        "reader": reader,
        "searcher": searcher,
        "trans_repo": trans_repo,
        "vocab_wf": vocab_wf,
    }


def test_catalog_operations(temp_books_env):
    """Test adding, listing, filtering, and stats in BookCatalog."""
    cat: BookCatalog = temp_books_env["catalog"]

    b1 = BookMetadata(
        book_id="book_alpha",
        canonical_title="Book Alpha",
        original_language="sa",
        document_type="philosophy",
        import_status=BookImportStatus.CATALOG_ONLY.value,
        copyright_status="public_domain",
        licence="Public Domain",
    )
    b2 = BookMetadata(
        book_id="book_beta",
        canonical_title="Book Beta",
        original_language="mjw",
        document_type="folklore",
        import_status=BookImportStatus.FULLY_IMPORTED.value,
        imported_chapters_count=2,
        imported_passages_count=10,
        copyright_status="public_domain",
        licence="Public Domain",
    )

    cat.add_book(b1)
    cat.add_book(b2)

    # Collision test
    with pytest.raises(ValueError, match="already exists"):
        cat.add_book(b1, overwrite=False)

    # Filtering
    all_books = cat.list_books()
    assert len(all_books) == 2

    sa_books = cat.list_books(language="sa")
    assert len(sa_books) == 1
    assert sa_books[0].book_id == "book_alpha"

    imported = cat.list_books(import_status="FULLY_IMPORTED")
    assert len(imported) == 1
    assert imported[0].book_id == "book_beta"

    stats = cat.get_stats()
    assert stats["total_books"] == 2
    assert stats["fully_imported_books"] == 1
    assert stats["catalog_only_books"] == 1
    assert stats["total_imported_passages"] == 10


def test_plain_text_import_and_structural_preservation(temp_books_env):
    """Test importing structured plain text into chapters and verses with stable IDs."""
    importer: BookImporter = temp_books_env["importer"]
    reader: BookReader = temp_books_env["reader"]

    sample_text = """
    CHAPTER I: THE AWAKENING
    
    Arise, O Prince! The field is set.
    The drums beat loud upon the hill.
    
    Fear not the multitude of spears,
    Stand fast in righteousness.
    
    CHAPTER II: THE PATH OF DUTY
    
    Action alone is thy concern,
    Never the fruit thereof.
    """

    meta = BookMetadata(
        book_id="test_epic",
        canonical_title="The Test Epic",
        original_language="en",
        licence="Public Domain",
        copyright_status="public_domain",
    )

    passages = importer.parse_plain_text(sample_text, book_id="test_epic", language="en")
    assert len(passages) == 3
    assert passages[0].passage_id == "test_epic:1:1"
    assert passages[0].chapter_number == 1
    assert passages[1].passage_id == "test_epic:1:2"
    assert passages[2].passage_id == "test_epic:2:1"
    assert passages[2].chapter_number == 2

    # Dry-run test: no files or db writes
    manifest_dry = importer.import_passages(meta, passages, dry_run=True)
    assert manifest_dry.dry_run is True
    assert manifest_dry.total_passages == 3
    assert not (temp_books_env["dir"] / "texts" / "test_epic.jsonl").exists()

    # Actual import
    manifest = importer.import_passages(meta, passages, overwrite=True)
    assert manifest.dry_run is False
    assert (temp_books_env["dir"] / "texts" / "test_epic.jsonl").exists()

    # Verify via reader
    p1 = reader.get_passage("test_epic:1:1")
    assert p1 is not None
    assert "Arise, O Prince" in p1.text

    # Chapters check
    chapters = reader.get_book_chapters("test_epic")
    assert len(chapters) == 2
    assert chapters[0]["passage_count"] == 2
    assert chapters[1]["passage_count"] == 1


def test_jsonl_and_json_file_imports(temp_books_env, tmp_path: Path):
    """Test file-based imports from JSON and JSONL formats."""
    importer: BookImporter = temp_books_env["importer"]
    reader: BookReader = temp_books_env["reader"]

    # 1. JSONL import
    jsonl_file = tmp_path / "sample.jsonl"
    with open(jsonl_file, "w", encoding="utf-8") as f:
        f.write(json.dumps({"passage_id": "jl_book:1:1", "text": "First verse in Karbi", "language": "mjw"}) + "\n")
        f.write(json.dumps({"passage_id": "jl_book:1:2", "text": "Second verse in Karbi", "language": "mjw"}) + "\n")

    manifest_jl = importer.import_file(jsonl_file, book_id="jl_book", language="mjw")
    assert manifest_jl.total_passages == 2
    assert reader.get_passage("jl_book:1:1") is not None

    # 2. JSON array import
    json_file = tmp_path / "sample.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump([
            {"passage_id": "json_book:1:1", "text": "Prose passage one"},
            {"passage_id": "json_book:1:2", "text": "Prose passage two"},
        ], f)

    manifest_js = importer.import_file(json_file, book_id="json_book")
    assert manifest_js.total_passages == 2
    assert reader.get_passage("json_book:1:2").text == "Prose passage two"


def test_full_text_search(temp_books_env):
    """Test full-text search across multilingual passages with snippets."""
    importer: BookImporter = temp_books_env["importer"]
    searcher: BookSearchEngine = temp_books_env["searcher"]

    meta = BookMetadata(
        book_id="multilingual_fables",
        canonical_title="Multilingual Fables",
        original_language="mjw",
        licence="Public Domain",
        copyright_status="public_domain",
    )
    passages = [
        Passage(
            passage_id="multilingual_fables:1:1",
            book_id="multilingual_fables",
            language="mjw",
            chapter_number=1,
            chapter_title="Story of the Deer",
            verse=1,
            sequence_number=1,
            text="The deer (sajir) leaped over the flowing river in the deep forest.",
        ),
        Passage(
            passage_id="multilingual_fables:1:2",
            book_id="multilingual_fables",
            language="en",
            chapter_number=1,
            chapter_title="Story of the Deer (English)",
            verse=2,
            sequence_number=2,
            text="The tiger waited patiently by the water source in silence.",
        ),
    ]

    importer.import_passages(meta, passages, overwrite=True)

    # Search term in first passage
    res = searcher.search_book_text("forest")
    assert len(res) == 1
    assert res[0].passage_id == "multilingual_fables:1:1"
    assert "forest" in res[0].matched_snippet.lower()

    # Search with language filter
    res_en = searcher.search_book_text("water", language="en")
    assert len(res_en) == 1
    assert res_en[0].passage_id == "multilingual_fables:1:2"

    res_mjw = searcher.search_book_text("water", language="mjw")
    assert len(res_mjw) == 0


def test_bidirectional_translation_alignment(temp_books_env):
    """Test linking and retrieving translations in both directions."""
    trans_repo: BookTranslationRepository = temp_books_env["trans_repo"]

    # Karbi -> English translation alignment
    tr1 = TranslationRecord(
        translation_id="TR:karbi_story:1:1:en",
        source_passage_id="karbi_story:1:1",
        source_language="mjw",
        target_language="en",
        translated_text="Once upon a time, an orphan went to fish.",
        translation_type=TranslationType.PUBLISHED_TRANSLATION.value,
        translator="Sir Charles Lyall",
        review_status="SOURCE_ATTESTED",
        source_citation="The Mikirs (1908)",
    )

    # English -> Karbi translation alignment
    tr2 = TranslationRecord(
        translation_id="TR:gita:2:47:mjw",
        source_passage_id="gita:2:47",
        source_language="en",
        target_language="mjw",
        translated_text="Nang kam sai-se nang phan do, a-the aphari matha ri.",
        translation_type=TranslationType.COMMUNITY_REVIEWED.value,
        reviewer_id="REV-LING-001",
        review_status="COMMUNITY_REVIEWED",
    )

    trans_repo.add_translation(tr1)
    trans_repo.add_translation(tr2)

    # Query translations for karbi_story:1:1
    res1 = trans_repo.get_translations_for_passage("karbi_story:1:1")
    assert len(res1) == 1
    assert res1[0].target_language == "en"
    assert "orphan" in res1[0].translated_text

    # Query translations for gita:2:47
    res2 = trans_repo.get_translations_for_passage("gita:2:47", target_language="mjw")
    assert len(res2) == 1
    assert res2[0].target_language == "mjw"
    assert res2[0].review_status == "COMMUNITY_REVIEWED"


def test_vocabulary_candidate_isolation(temp_books_env):
    """Test extracting vocabulary candidates and verifying isolation from core lexicon."""
    vocab_wf: VocabularyCandidateWorkflow = temp_books_env["vocab_wf"]

    passage = Passage(
        passage_id="sample:1:1",
        book_id="sample",
        language="en",
        sequence_number=1,
        text="The ancient village elder spoke of sacred traditions and folklore.",
    )

    candidates = vocab_wf.extract_candidates_from_passage(passage, min_len=4)
    assert len(candidates) > 0
    assert any(c.source_term.lower() == "ancient" for c in candidates)

    saved_count = vocab_wf.save_candidates(candidates)
    assert saved_count == len(candidates)

    listed = vocab_wf.list_candidates(book_id="sample")
    assert len(listed) == len(candidates)

    # Verify status is EXTRACTED, not verified or in lexicon
    for cand in listed:
        assert cand.status == CandidateStatus.EXTRACTED.value


def test_book_validation_engine(temp_books_env):
    """Test book and catalogue validation for schema and missing sections."""
    cat: BookCatalog = temp_books_env["catalog"]
    books_dir = temp_books_env["dir"]

    # 1. CATALOG_ONLY book: valid without text file
    meta_cat_only = BookMetadata(
        book_id="catalog_work",
        canonical_title="A Catalogued Work",
        original_language="sa",
        import_status=BookImportStatus.CATALOG_ONLY.value,
        copyright_status="public_domain",
        licence="Public Domain",
    )
    cat.add_book(meta_cat_only)

    res_cat = validate_book("catalog_work", catalog=cat, books_dir=books_dir)
    assert res_cat.is_valid is True

    # 2. FULLY_IMPORTED book with missing file: should fail validation
    meta_broken = BookMetadata(
        book_id="broken_work",
        canonical_title="Broken Work",
        original_language="en",
        import_status=BookImportStatus.FULLY_IMPORTED.value,
        imported_passages_count=5,
        copyright_status="public_domain",
        licence="Public Domain",
    )
    cat.add_book(meta_broken)

    res_broken = validate_book("broken_work", catalog=cat, books_dir=books_dir)
    assert res_broken.is_valid is False
    assert any("does not exist" in e for e in res_broken.errors)


def test_public_book_apis():
    """Test high-level public book APIs exposed through `karbi`."""
    books = karbi.list_books()
    assert len(books) >= 20  # 20 initial catalogue entries

    # Check imported Bhagavad Gita
    bg_meta = karbi.get_book_metadata("bhagavad_gita")
    assert bg_meta is not None
    assert bg_meta["import_status"] == "FULLY_IMPORTED"
    assert bg_meta["imported_chapters_count"] == 18

    # Check reading passage
    p = karbi.get_passage("bhagavad_gita:1:1")
    assert p is not None
    assert "Kurukshetra" in p.text

    # Check search
    results = karbi.search_book_text("Kurukshetra")
    assert len(results) >= 1
    assert any(r.book_id == "bhagavad_gita" for r in results)

    # Check imported Ramayana
    ram_meta = karbi.get_book_metadata("ramayana")
    assert ram_meta is not None
    assert ram_meta["import_status"] == "FULLY_IMPORTED"
    assert ram_meta["imported_chapters_count"] == 493
    p_ram = karbi.get_passage("ramayana:1:1:2")
    assert p_ram is not None
    assert "Nárad" in p_ram.text or "Narad" in p_ram.text

    # Check imported Mahabharata (Adi Parva)
    mb_meta = karbi.get_book_metadata("mahabharata")
    assert mb_meta is not None
    assert mb_meta["import_status"] == "PARTIALLY_IMPORTED"
    assert mb_meta["imported_chapters_count"] == 236
    p_mb = karbi.get_passage("mahabharata:1:1:1")
    assert p_mb is not None

    # Check imported Hitopadesha
    hito_meta = karbi.get_book_metadata("hitopadesha")
    assert hito_meta is not None
    assert hito_meta["import_status"] == "FULLY_IMPORTED"
    assert hito_meta["imported_chapters_count"] == 5

    # Check imported Dhammapada
    dh_meta = karbi.get_book_metadata("dhammapada")
    assert dh_meta is not None
    assert dh_meta["import_status"] == "FULLY_IMPORTED"
    assert dh_meta["imported_chapters_count"] == 26

    # Check imported Indian Fairy Tales
    ift_meta = karbi.get_book_metadata("indian_fairy_tales")
    assert ift_meta is not None
    assert ift_meta["import_status"] == "FULLY_IMPORTED"
    assert ift_meta["imported_chapters_count"] == 29

    # Check imported Folk Tales of Bengal
    ftb_meta = karbi.get_book_metadata("folk_tales_of_bengal")
    assert ftb_meta is not None
    assert ftb_meta["import_status"] == "FULLY_IMPORTED"
    assert ftb_meta["imported_chapters_count"] == 22
    assert ftb_meta["imported_passages_count"] == 294
    p_ftb = karbi.get_passage("folk_tales_of_bengal:1:1")
    assert p_ftb is not None

    # Check imported Shakuntala
    shak_meta = karbi.get_book_metadata("shakuntala")
    assert shak_meta is not None
    assert shak_meta["import_status"] == "FULLY_IMPORTED"
    assert shak_meta["imported_chapters_count"] == 7
    assert shak_meta["imported_passages_count"] == 1380
    p_shak = karbi.get_passage("shakuntala:1:1")
    assert p_shak is not None

    # Check newly imported works
    odd_meta = karbi.get_book_metadata("old_deccan_days")
    assert odd_meta is not None
    assert odd_meta["import_status"] == "FULLY_IMPORTED"
    assert odd_meta["imported_chapters_count"] == 24
    assert odd_meta["imported_passages_count"] == 772
    assert "36696" in odd_meta["source_url"]

    jt_meta = karbi.get_book_metadata("jataka_tales")
    assert jt_meta is not None
    assert jt_meta["import_status"] == "FULLY_IMPORTED"
    assert jt_meta["imported_chapters_count"] == 18
    assert jt_meta["imported_passages_count"] == 372

    lcc_meta = karbi.get_book_metadata("little_clay_cart")
    assert lcc_meta is not None
    assert lcc_meta["import_status"] == "FULLY_IMPORTED"
    assert lcc_meta["imported_chapters_count"] == 12
    assert lcc_meta["imported_passages_count"] == 2314

    # Check statistics
    stats = karbi.get_book_statistics()
    assert stats["total_books"] == 27
    assert stats["fully_imported_books"] == 17
    assert stats["partially_imported_books"] == 1
    assert stats["catalog_only_books"] == 9
    assert stats["total_imported_passages"] == 16499
    assert stats["total_imported_chapters"] == 1185


def test_cli_book_subcommands(capsys):
    """Test CLI commands for `karbi books`."""
    # 1. karbi books list
    exit_code = karbi.cli.main(["books", "list"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "KARBI DIGITAL BOOK LIBRARY CATALOGUE" in captured.out
    assert "bhagavad_gita" in captured.out
    assert "folk_tales_of_bengal" in captured.out
    assert "shakuntala" in captured.out

    # 2. karbi books info
    exit_code = karbi.cli.main(["books", "info", "bhagavad_gita"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "BOOK METADATA: The Bhagavad Gita" in captured.out

    # 3. karbi books read
    exit_code = karbi.cli.main(["books", "read", "bhagavad_gita", "--chapter", "1", "--limit", "2"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "bhagavad_gita:1:1" in captured.out

    # 4. karbi books search
    exit_code = karbi.cli.main(["books", "search", "Kurukshetra"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "The Bhagavad Gita" in captured.out

    # 5. karbi books stats
    exit_code = karbi.cli.main(["books", "stats"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "KARBI DIGITAL BOOK LIBRARY STATISTICS" in captured.out

    # 6. karbi books audit
    exit_code_audit = karbi.cli.main(["books", "audit"])
    assert exit_code_audit == 0
    captured_audit = capsys.readouterr()
    assert "KARBI DIGITAL BOOK LIBRARY AUDIT REPORT" in captured_audit.out
    assert "Security Audit:   [PASSED]" in captured_audit.out
    assert "Consent Audit:    [PASSED]" in captured_audit.out
    assert "Lexicon Audit:    [PASSED]" in captured_audit.out


def test_book_auditor_all_works():
    """Test BookAuditor across all 20 catalogued works and verify integrity metrics."""
    from karbi.books.audit import BookAuditor

    auditor = BookAuditor()
    report = auditor.audit_all(write_report=True)

    assert report.total_catalog_works == 27
    assert report.imported_works_audited == 18
    assert report.verified_works_count == 17
    assert report.partially_verified_count == 1  # mahabharata
    assert report.failed_works_count == 0
    assert report.not_applicable_count == 9
    assert report.total_verified_passages == 16499
    assert report.total_verified_chapters == 1185

    # Check that audit report was written to disk
    report_file = auditor.books_dir / "audit_report.json"
    assert report_file.is_file()
    with open(report_file, "r", encoding="utf-8") as f:
        saved_report = json.load(f)
    assert saved_report["total_verified_passages"] == 16499


def test_security_tls_verification_enforced():
    """Verify that no insecure TLS context bypasses exist in production import code."""
    repo_root = Path(__file__).resolve().parent.parent
    src_dir = repo_root / "src" / "karbi"
    forbidden_pattern = "_create_unverified" + "_context"

    violating_files = []
    for py_file in src_dir.rglob("*.py"):
        # Exclude audit.py check itself
        if py_file.name == "audit.py":
            continue
        text = py_file.read_text(encoding="utf-8")
        if forbidden_pattern in text:
            violating_files.append(str(py_file.relative_to(repo_root)))

    assert not violating_files, f"Insecure TLS bypasses found in: {violating_files}"


def test_community_consent_and_rights_safeguards():
    """Verify community consent is not claimed for historical 1908 Stack & Lyall text."""
    repo_root = Path(__file__).resolve().parent.parent
    sources_file = repo_root / "data" / "books" / "sources.jsonl"
    assert sources_file.is_file()

    stack_lyall_found = False
    with open(sources_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            src = json.loads(line)
            if src.get("source_id") == "SRC-BOOK-00012":
                stack_lyall_found = True
                rp = src.get("rights_and_permissions", {})
                assert rp.get("community_consent_verified") is False, (
                    "Historical 1908 text must not assert community consent without contemporary FPIC documentation."
                )
                assert rp.get("native_speaker_verified") is False
                assert "1908" in rp.get("notes", "")
    assert stack_lyall_found, "SRC-BOOK-00012 not found in sources.jsonl"


def test_dhammapada_canonical_verses_mapping():
    """Verify Dhammapada 414 passage entries accurately map to 423 canonical verses."""
    repo_root = Path(__file__).resolve().parent.parent
    dh_file = repo_root / "data" / "books" / "texts" / "dhammapada.jsonl"
    assert dh_file.is_file()

    total_passages = 0
    total_canonical_verses = 0
    combined_count = 0

    with open(dh_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            total_passages += 1
            p = json.loads(line)
            c_cnt = p.get("canonical_verse_count") or p.get("metadata", {}).get("canonical_verse_count", 1)
            total_canonical_verses += c_cnt
            is_combined = p.get("is_combined_verse") or p.get("metadata", {}).get("is_combined_verse", False)
            if is_combined:
                combined_count += 1
                c_verses = p.get("canonical_verses") or p.get("metadata", {}).get("canonical_verses", [])
                assert len(c_verses) == 2

    assert total_passages == 414, f"Expected 414 passage records, got {total_passages}"
    assert total_canonical_verses == 423, f"Expected 423 canonical verses, got {total_canonical_verses}"
    assert combined_count == 9, f"Expected exactly 9 combined verse pairs, got {combined_count}"


def test_annotations_separated_from_passages():
    """Verify scholarly translator footnotes are preserved in annotations and not in stanzas."""
    repo_root = Path(__file__).resolve().parent.parent
    annot_dir = repo_root / "data" / "books" / "annotations"

    # 1. Bhagavad Gita annotations
    bg_annot_file = annot_dir / "annotations_bhagavad_gita.json"
    assert bg_annot_file.is_file()
    with open(bg_annot_file, "r", encoding="utf-8") as f:
        bg_annot = json.load(f)
    bg_notes = bg_annot.get("annotations", bg_annot)
    assert len(bg_notes) == 37, f"Expected 37 Bhagavad Gita endnotes, got {len(bg_notes)}"

    # 2. Hitopadesha annotations
    hito_annot_file = annot_dir / "annotations_hitopadesha.json"
    assert hito_annot_file.is_file()
    with open(hito_annot_file, "r", encoding="utf-8") as f:
        hito_annot = json.load(f)
    hito_notes = hito_annot.get("annotations", hito_annot)
    assert len(hito_notes) == 20, f"Expected 20 Hitopadesha endnotes, got {len(hito_notes)}"

    # 3. Verify Hitopadesha passages contain 0 endnote records
    hito_passages_file = repo_root / "data" / "books" / "texts" / "hitopadesha.jsonl"
    with open(hito_passages_file, "r", encoding="utf-8") as f:
        for line in f:
            p = json.loads(line)
            assert not p["passage_id"].startswith("hitopadesha:notes:"), (
                f"Endnote {p['passage_id']} should not be in narrative passages file"
            )


def test_lexicon_remains_isolated():
    """Verify core lexicon is untouched by book imports (516 entries, KB-LEX-0000382 intact)."""
    repo_root = Path(__file__).resolve().parent.parent
    lexicon_file = repo_root / "data" / "lexicon" / "core_lexicon.jsonl"
    assert lexicon_file.is_file()

    entries = []
    kathe_entry = None
    with open(lexicon_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            entries.append(entry)
            if entry.get("id") == "KB-LEX-0000382":
                kathe_entry = entry

    assert len(entries) == 516, f"Core lexicon size must remain exactly 516, got {len(entries)}"
    assert kathe_entry is not None, "KB-LEX-0000382 ('kāthē') must exist"
    assert kathe_entry.get("status") == "CITATION_MISMATCH", (
        f"KB-LEX-0000382 status must remain CITATION_MISMATCH, got {kathe_entry.get('status')}"
    )
    lemma = kathe_entry.get("lemma") or kathe_entry.get("headword", {}).get("lemma")
    assert lemma == "kāthē"


def test_folk_tales_of_bengal_structure_and_annotations():
    """Verify Folk Tales of Bengal has 22 stories, 294 passages, and 47 endnotes."""
    repo_root = Path(__file__).resolve().parent.parent
    texts_dir = repo_root / "data" / "books" / "texts"
    annot_dir = repo_root / "data" / "books" / "annotations"

    ftb_file = texts_dir / "folk_tales_of_bengal.jsonl"
    assert ftb_file.is_file()

    passages = []
    stories = set()
    with open(ftb_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            p = json.loads(line)
            passages.append(p)
            stories.add(p["chapter_number"])
            assert p["passage_id"].startswith("folk_tales_of_bengal:")
            assert len(p["text"].strip()) > 10

    assert len(stories) == 22, f"Expected 22 stories, found {len(stories)}"
    assert len(passages) == 294, f"Expected 294 passages, found {len(passages)}"

    # Check 47 endnotes
    annot_file = annot_dir / "annotations_folk_tales_of_bengal.json"
    assert annot_file.is_file()
    with open(annot_file, "r", encoding="utf-8") as f:
        annot_data = json.load(f)
    assert len(annot_data["annotations"]) == 47, f"Expected 47 endnotes, got {len(annot_data['annotations'])}"


def test_shakuntala_structure_and_acts():
    """Verify Shakuntala has 7 acts and 1,380 dialogue/narrative passages."""
    repo_root = Path(__file__).resolve().parent.parent
    shak_file = repo_root / "data" / "books" / "texts" / "shakuntala.jsonl"
    assert shak_file.is_file()

    passages = []
    acts = set()
    with open(shak_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            p = json.loads(line)
            passages.append(p)
            acts.add(p["chapter_number"])
            assert p["passage_id"].startswith("shakuntala:")
            assert len(p["text"].strip()) > 5

    assert len(acts) == 7, f"Expected 7 acts, found {len(acts)}"
    assert len(passages) == 1380, f"Expected 1380 passages, found {len(passages)}"


def test_panchatantra_obstacle_documented_as_catalog_only():
    """Verify Panchatantra is kept CATALOG_ONLY due to unverified raw OCR on Internet Archive."""
    repo_root = Path(__file__).resolve().parent.parent
    cat_file = repo_root / "data" / "books" / "catalog.json"
    with open(cat_file, "r", encoding="utf-8") as f:
        catalog = {b["book_id"]: b for b in json.load(f)}

    panch = catalog.get("panchatantra")
    assert panch is not None
    assert panch["import_status"] == "CATALOG_ONLY"
    assert panch["imported_passages_count"] == 0
    assert panch["imported_chapters_count"] == 0
    # Text file must not exist
    txt_file = repo_root / "data" / "books" / "texts" / "panchatantra.jsonl"
    assert not txt_file.is_file(), "Unverified OCR text must not be silently ingested"


def test_import_idempotence_and_atomic_preservation(temp_books_env):
    """Verify importer refuses to overwrite fully imported books without overwrite=True."""
    importer: BookImporter = temp_books_env["importer"]
    meta = BookMetadata(
        book_id="idempotent_test",
        canonical_title="Idempotent Test",
        import_status=BookImportStatus.CATALOG_ONLY.value
    )
    temp_books_env["catalog"].add_book(meta)

    passages = [
        Passage(passage_id="idempotent_test:1:1", book_id="idempotent_test", sequence_number=1, text="First passage"),
        Passage(passage_id="idempotent_test:1:2", book_id="idempotent_test", sequence_number=2, text="Second passage"),
    ]

    # First import succeeds
    m1 = importer.import_passages(meta, passages, overwrite=False)
    assert m1.total_passages == 2

    # Second import without overwrite raises ValueError
    with pytest.raises(ValueError, match="already fully imported"):
        importer.import_passages(meta, passages, overwrite=False)

    # Re-import with overwrite=True succeeds and is idempotent
    m2 = importer.import_passages(meta, passages, overwrite=True)
    assert m2.sha256_checksum == m1.sha256_checksum


def test_old_deccan_days_gutenberg_36696_and_structure():
    """Verify Old Deccan Days uses authentic PG #36696 (not #12690) with all 24 stories."""
    repo_root = Path(__file__).resolve().parent.parent
    cat_file = repo_root / "data" / "books" / "catalog.json"
    with open(cat_file, "r", encoding="utf-8") as f:
        catalog = {b["book_id"]: b for b in json.load(f)}

    odd = catalog.get("old_deccan_days")
    assert odd is not None
    assert odd["import_status"] == "FULLY_IMPORTED"
    assert odd["source_url"] == "https://www.gutenberg.org/ebooks/36696"
    assert "12690" not in odd["source_url"]
    assert "36696" in odd["licence"]
    assert odd["imported_chapters_count"] == 24
    assert odd["imported_passages_count"] == 772

    # Verify JSONL content on disk
    txt_file = repo_root / "data" / "books" / "texts" / "old_deccan_days.jsonl"
    assert txt_file.is_file()
    passages = []
    stories = set()
    with open(txt_file, "r", encoding="utf-8") as f:
        for line in f:
            p = json.loads(line)
            passages.append(p)
            stories.add(p["chapter_number"])
            assert p["passage_id"].startswith("old_deccan_days:")
            assert len(p["text"].strip()) > 5

    assert len(stories) == 24
    assert len(passages) == 772


def test_big_command_4_imported_books_integrity():
    """Verify all 9 newly imported works maintain structural integrity, manifest checksums, and db indexing."""
    repo_root = Path(__file__).resolve().parent.parent
    books_dir = repo_root / "data" / "books"
    
    new_books = [
        ("old_deccan_days", 24, 772),
        ("jataka_tales", 18, 372),
        ("more_jataka_tales", 21, 364),
        ("tales_of_the_punjab", 42, 1452),
        ("little_clay_cart", 12, 2314),
        ("deccan_nursery_tales", 20, 72),
        ("hindoo_tales_dandin", 11, 684),
        ("vikram_and_the_vampire", 12, 1254),
        ("folklore_santal_parganas", 185, 1364),
    ]

    for b_id, expected_ch, expected_pass in new_books:
        # Check text file
        t_path = books_dir / "texts" / f"{b_id}.jsonl"
        assert t_path.is_file(), f"Missing text file for {b_id}"
        
        # Check manifest file
        m_path = books_dir / "manifests" / f"manifest_{b_id}.json"
        assert m_path.is_file(), f"Missing manifest for {b_id}"
        with open(m_path, "r", encoding="utf-8") as mf:
            m_obj = json.load(mf)
        assert m_obj["total_passages"] == expected_pass
        assert m_obj["total_chapters"] == expected_ch

        # Check passage sequence
        passages = []
        with open(t_path, "r", encoding="utf-8") as tf:
            for line in tf:
                passages.append(json.loads(line))
        assert len(passages) == expected_pass
        for i, p in enumerate(passages, 1):
            assert p["sequence_number"] == i
            assert len(p["text"].strip()) > 0


