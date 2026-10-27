"""
Automated Unit Tests for Batch Dataset Validation (`karbi.core.dataset`)
========================================================================

Uses temporary directories and fictional test datasets to verify:
- Cross-file duplicate ID detection (entries, sources, examples, reviews).
- Referential integrity for sources and cross-references.
- Batch error aggregation (all errors surfaced in one run).
- Enforcement of strict verification and test-fixture rejection rules.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure src is on sys.path
SRC_PATH = Path(__file__).resolve().parent.parent / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from karbi.core.dataset import DatasetValidator, validate_dataset_files
from karbi.core.models import (
    ReviewerRegistration,
    ReviewerRole,
    SourceType,
    Status,
)


def make_fictional_source_dict(source_id: str = "SRC-PUB-00001", title: str = "Mock Source") -> dict:
    """Helper creating a fictional source dictionary for testing."""
    return {
        "source_id": source_id,
        "source_type": SourceType.PRINT_PUBLICATION.value,
        "title": title,
        "creators": [{"name_or_organization": "Synthetic Test Author", "role": "author"}],
        "rights_and_permissions": {"status": "synthetic_test_data", "details": "Testing only"},
        "publication_details": {"publisher": "Test Press", "year": 2026},
    }


def make_fictional_entry_dict(
    entry_id: str = "KB-TEST-0000001",
    lemma: str = "mock_word",
    source_id: str = "SRC-PUB-00001",
    example_id: str = "EX-000001",
    status: str = Status.DRAFT.value,
    is_test_fixture: bool = True,
    target_xref_id: str = None,
) -> dict:
    """Helper creating a fictional entry dictionary for testing."""
    xrefs = []
    if target_xref_id:
        xrefs.append({"target_entry_id": target_xref_id, "relation_type": "see_also"})

    return {
        "id": entry_id,
        "is_test_fixture": is_test_fixture,
        "headword": {
            "lemma": lemma,
            "script": "latin",
            "orthography_standard": {
                "system_name": "fictional_system",
                "authority_status": "provisional",
            },
        },
        "dialect": {"primary_variety": "fictional_variety", "status": "provisional"},
        "cross_references": xrefs,
        "senses": [
            {
                "sense_id": "S1",
                "part_of_speech": "noun",
                "definitions": {"en": ["mock definition"]},
                "status": status,
                "examples": [
                    {
                        "example_id": example_id,
                        "text_karbi": "Mock sentence.",
                        "translations": {"en": "Mock translation."},
                        "source_id": source_id,
                        "locator": "p. 1",
                    }
                ],
            }
        ],
        "status": status,
        "provenance": {
            "evidence_records": [
                {
                    "source_id": source_id,
                    "locator": "p. 1",
                    "evidence_type": "published_print_citation",
                }
            ],
            "contributors": [],
            "reviews": [],
        },
    }


class TestBatchDatasetValidation(unittest.TestCase):
    """Test suite covering multi-file dataset validation and integrity audits."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_valid_dataset_passes(self):
        """A dataset with valid sources and consistent entries passes validation."""
        src_file = self.dir_path / "sources.jsonl"
        src_file.write_text(json.dumps(make_fictional_source_dict("SRC-PUB-00001")) + "\n", encoding="utf-8")

        lex_file = self.dir_path / "lexicon.jsonl"
        lex_file.write_text(
            json.dumps(make_fictional_entry_dict("KB-TEST-0000001", source_id="SRC-PUB-00001", example_id="EX-01")) + "\n"
            + json.dumps(make_fictional_entry_dict("KB-TEST-0000002", source_id="SRC-PUB-00001", example_id="EX-02")) + "\n",
            encoding="utf-8",
        )

        result = validate_dataset_files([lex_file], [src_file])
        self.assertTrue(result.is_valid, f"Expected dataset to be valid, got errors: {[str(e) for e in result.errors]}")
        self.assertEqual(len(result.errors), 0)
        self.assertEqual(result.lexicon_entries_count, 2)
        self.assertEqual(result.sources_count, 1)

    def test_duplicate_entry_id_across_files(self):
        """Duplicate entry IDs across different files are detected with exact locations."""
        src_file = self.dir_path / "sources.jsonl"
        src_file.write_text(json.dumps(make_fictional_source_dict("SRC-PUB-00001")) + "\n", encoding="utf-8")

        file1 = self.dir_path / "file1.jsonl"
        file1.write_text(json.dumps(make_fictional_entry_dict("KB-TEST-0000001", example_id="EX-01")) + "\n", encoding="utf-8")

        file2 = self.dir_path / "file2.jsonl"
        # Duplicate entry ID KB-TEST-0000001!
        file2.write_text(json.dumps(make_fictional_entry_dict("KB-TEST-0000001", example_id="EX-02")) + "\n", encoding="utf-8")

        result = validate_dataset_files([file1, file2], [src_file])
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Duplicate entry ID 'KB-TEST-0000001'" in str(e) for e in result.errors))
        self.assertTrue(any("file1.jsonl:1" in str(e) for e in result.errors))

    def test_duplicate_source_id_across_files(self):
        """Duplicate source IDs across source files are detected and reported."""
        src_file1 = self.dir_path / "sources1.jsonl"
        src_file1.write_text(json.dumps(make_fictional_source_dict("SRC-PUB-00001")) + "\n", encoding="utf-8")

        src_file2 = self.dir_path / "sources2.jsonl"
        # Duplicate source ID!
        src_file2.write_text(json.dumps(make_fictional_source_dict("SRC-PUB-00001")) + "\n", encoding="utf-8")

        result = validate_dataset_files([], [src_file1, src_file2])
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Duplicate source_id 'SRC-PUB-00001'" in str(e) for e in result.errors))

    def test_duplicate_example_id_across_files(self):
        """Duplicate example IDs across different entries and files are detected."""
        src_file = self.dir_path / "sources.jsonl"
        src_file.write_text(json.dumps(make_fictional_source_dict("SRC-PUB-00001")) + "\n", encoding="utf-8")

        lex_file1 = self.dir_path / "lex1.jsonl"
        lex_file1.write_text(
            json.dumps(make_fictional_entry_dict("KB-TEST-0000001", example_id="EX-SHARED-01")) + "\n",
            encoding="utf-8",
        )

        lex_file2 = self.dir_path / "lex2.jsonl"
        # Duplicate example ID EX-SHARED-01!
        lex_file2.write_text(
            json.dumps(make_fictional_entry_dict("KB-TEST-0000002", example_id="EX-SHARED-01")) + "\n",
            encoding="utf-8",
        )

        result = validate_dataset_files([lex_file1, lex_file2], [src_file])
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Duplicate example_id 'EX-SHARED-01'" in str(e) for e in result.errors))

    def test_missing_source_reference(self):
        """An entry referencing an unregistered source ID is flagged with line and record ID."""
        src_file = self.dir_path / "sources.jsonl"
        src_file.write_text(json.dumps(make_fictional_source_dict("SRC-PUB-00001")) + "\n", encoding="utf-8")

        lex_file = self.dir_path / "lexicon.jsonl"
        # References unknown source SRC-PUB-MISSING-999
        lex_file.write_text(
            json.dumps(make_fictional_entry_dict("KB-TEST-0000001", source_id="SRC-PUB-MISSING-999")) + "\n",
            encoding="utf-8",
        )

        result = validate_dataset_files([lex_file], [src_file])
        self.assertFalse(result.is_valid)
        self.assertTrue(any("SRC-PUB-MISSING-999" in str(e) for e in result.errors))

    def test_missing_cross_reference(self):
        """An entry cross-referencing a non-existent entry ID is caught."""
        src_file = self.dir_path / "sources.jsonl"
        src_file.write_text(json.dumps(make_fictional_source_dict("SRC-PUB-00001")) + "\n", encoding="utf-8")

        lex_file = self.dir_path / "lexicon.jsonl"
        # Cross-reference targets non-existent KB-TEST-NONEXISTENT
        lex_file.write_text(
            json.dumps(make_fictional_entry_dict("KB-TEST-0000001", target_xref_id="KB-TEST-NONEXISTENT")) + "\n",
            encoding="utf-8",
        )

        result = validate_dataset_files([lex_file], [src_file])
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Cross-reference target 'KB-TEST-NONEXISTENT' does not exist" in str(e) for e in result.errors))

    def test_cross_reference_jsonl_key_format(self):
        """Cross-references using the JSONL key 'entry_id' validate successfully when target exists."""
        src_file = self.dir_path / "sources.jsonl"
        src_file.write_text(json.dumps(make_fictional_source_dict("SRC-PUB-00001")) + "\n", encoding="utf-8")

        target_entry = make_fictional_entry_dict("KB-TEST-0000001", example_id="EX-01")
        source_entry = make_fictional_entry_dict("KB-TEST-0000002", example_id="EX-02")
        # Use the actual JSONL field format: entry_id + relationship
        source_entry["cross_references"] = [{"entry_id": "KB-TEST-0000001", "relationship": "component_word"}]

        lex_file = self.dir_path / "lexicon.jsonl"
        lex_file.write_text(json.dumps(target_entry) + "\n" + json.dumps(source_entry) + "\n", encoding="utf-8")

        result = validate_dataset_files([lex_file], [src_file])
        self.assertTrue(result.is_valid, f"Expected valid result, got: {[str(e) for e in result.errors]}")

    def test_missing_cross_reference_using_jsonl_key(self):
        """Missing cross-reference target is caught when specified using JSONL key 'entry_id'."""
        src_file = self.dir_path / "sources.jsonl"
        src_file.write_text(json.dumps(make_fictional_source_dict("SRC-PUB-00001")) + "\n", encoding="utf-8")

        entry = make_fictional_entry_dict("KB-TEST-0000001", example_id="EX-01")
        entry["cross_references"] = [{"entry_id": "KB-TEST-NONEXISTENT-99", "relationship": "see_also"}]

        lex_file = self.dir_path / "lexicon.jsonl"
        lex_file.write_text(json.dumps(entry) + "\n", encoding="utf-8")

        result = validate_dataset_files([lex_file], [src_file])
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Cross-reference target 'KB-TEST-NONEXISTENT-99' does not exist" in str(e) for e in result.errors))

    def test_empty_and_whitespace_cross_reference_targets(self):
        """Cross-references with empty or whitespace-only target IDs are reported as errors."""
        src_file = self.dir_path / "sources.jsonl"
        src_file.write_text(json.dumps(make_fictional_source_dict("SRC-PUB-00001")) + "\n", encoding="utf-8")

        # 1. Empty string using JSONL format
        entry_empty = make_fictional_entry_dict("KB-TEST-0000001", example_id="EX-01")
        entry_empty["cross_references"] = [{"entry_id": "", "relationship": "see_also"}]

        # 2. Whitespace-only string using JSONL format
        entry_ws = make_fictional_entry_dict("KB-TEST-0000002", example_id="EX-02")
        entry_ws["cross_references"] = [{"entry_id": "   ", "relationship": "see_also"}]

        # 3. Missing target key altogether
        entry_missing = make_fictional_entry_dict("KB-TEST-0000003", example_id="EX-03")
        entry_missing["cross_references"] = [{"relationship": "see_also"}]

        # 4. Whitespace-only using model format target_entry_id
        entry_model_ws = make_fictional_entry_dict("KB-TEST-0000004", example_id="EX-04")
        entry_model_ws["cross_references"] = [{"target_entry_id": "  \t  ", "relation_type": "see_also"}]

        lex_file = self.dir_path / "lex_empty_targets.jsonl"
        lex_file.write_text(
            json.dumps(entry_empty) + "\n"
            + json.dumps(entry_ws) + "\n"
            + json.dumps(entry_missing) + "\n"
            + json.dumps(entry_model_ws) + "\n",
            encoding="utf-8",
        )

        result = validate_dataset_files([lex_file], [src_file])
        self.assertFalse(result.is_valid)
        err_msgs = [str(e) for e in result.errors]
        empty_target_errs = [e for e in err_msgs if "Cross-reference target ID cannot be empty or missing" in e]
        self.assertEqual(len(empty_target_errs), 4, f"Expected 4 empty target errors, got: {empty_target_errs}")

    def test_multiple_errors_reported_together(self):
        """Batch validation reports multiple diverse errors together without stopping at the first."""
        src_file = self.dir_path / "sources.jsonl"
        src_file.write_text(json.dumps(make_fictional_source_dict("SRC-PUB-00001")) + "\n", encoding="utf-8")

        lex_file = self.dir_path / "lex_multi_err.jsonl"
        # Line 1: Missing lemma
        bad_entry1 = make_fictional_entry_dict("KB-TEST-0000001", lemma="", example_id="EX-01")
        # Line 2: Syntax error
        # Line 3: Unknown source
        bad_entry2 = make_fictional_entry_dict("KB-TEST-0000002", source_id="SRC-PUB-UNKNOWN", example_id="EX-02")

        lex_file.write_text(
            json.dumps(bad_entry1) + "\n"
            + '{"broken_json": [missing_bracket\n'
            + json.dumps(bad_entry2) + "\n",
            encoding="utf-8",
        )

        result = validate_dataset_files([lex_file], [src_file])
        self.assertFalse(result.is_valid)

        # All 3 errors must be surfaced together
        error_texts = [str(e) for e in result.errors]
        has_lemma_error = any("headword.lemma cannot be empty" in t for t in error_texts)
        has_syntax_error = any("Invalid JSON syntax" in t for t in error_texts)
        has_source_error = any("SRC-PUB-UNKNOWN" in t for t in error_texts)

        self.assertTrue(has_lemma_error, "Missing lemma error not reported")
        self.assertTrue(has_syntax_error, "Syntax error on line 2 not reported")
        self.assertTrue(has_source_error, "Unknown source reference not reported")
        self.assertGreaterEqual(len(result.errors), 3)

    def test_test_fixture_cannot_be_verified_in_dataset(self):
        """Test fixtures with status VERIFIED are rejected by dataset validation."""
        src_file = self.dir_path / "sources.jsonl"
        src_file.write_text(json.dumps(make_fictional_source_dict("SRC-PUB-00001")) + "\n", encoding="utf-8")

        lex_file = self.dir_path / "lexicon.jsonl"
        # status: VERIFIED on a test fixture!
        entry = make_fictional_entry_dict("KB-TEST-0000001", status=Status.VERIFIED.value, is_test_fixture=True)
        lex_file.write_text(json.dumps(entry) + "\n", encoding="utf-8")

        result = validate_dataset_files([lex_file], [src_file])
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Test fixtures and synthetic entries are strictly prohibited" in str(e) for e in result.errors))


class TestCanonicalRepositoryDataset(unittest.TestCase):
    """Validation and integrity tests against the canonical repository datasets."""

    def test_canonical_lexicon_and_sources_validity(self):
        """Authoritative repository dataset passes full batch validation with 0 errors."""
        repo_root = Path(__file__).resolve().parent.parent
        lex_file = repo_root / "data" / "lexicon" / "core_lexicon.jsonl"
        src_file = repo_root / "data" / "sources" / "sources.jsonl"

        self.assertTrue(lex_file.is_file(), f"Canonical lexicon file not found at {lex_file}")
        self.assertTrue(src_file.is_file(), f"Canonical sources file not found at {src_file}")

        result = validate_dataset_files([lex_file], [src_file])
        self.assertTrue(result.is_valid, f"Dataset validation failed: {result.errors}")
        self.assertEqual(len(result.errors), 0)
        self.assertEqual(result.lexicon_entries_count, 516)
        self.assertEqual(result.sources_count, 4)

    def test_canonical_entries_duplicate_prevention(self):
        """All 516 entries have unique IDs in canonical dataset."""
        repo_root = Path(__file__).resolve().parent.parent
        lex_file = repo_root / "data" / "lexicon" / "core_lexicon.jsonl"

        seen_ids = set()
        with open(lex_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                eid = entry["id"]
                self.assertNotIn(eid, seen_ids, f"Duplicate entry ID detected: {eid}")
                seen_ids.add(eid)

        self.assertEqual(len(seen_ids), 516)

    def test_expanded_lexicon_entries_integrity(self):
        """Newly expanded entries (KB-LEX-0000482 to KB-LEX-0000516) have valid locators and unverified Indic glosses."""
        repo_root = Path(__file__).resolve().parent.parent
        lex_file = repo_root / "data" / "lexicon" / "core_lexicon.jsonl"

        with open(lex_file, "r", encoding="utf-8") as f:
            entries = [json.loads(line) for line in f if line.strip()]

        expanded = [e for e in entries if int(e["id"].split("-")[-1]) >= 482]
        self.assertEqual(len(expanded), 35)

        for e in expanded:
            self.assertEqual(e["status"], "SOURCE_ATTESTED")
            self.assertGreaterEqual(len(e["provenance"]["evidence_records"]), 1)
            ev = e["provenance"]["evidence_records"][0]
            self.assertEqual(ev["source_id"], "SRC-PUB-00001")
            self.assertTrue(ev["locator"].strip())

            # Verify sense gloss provenance and unverified flags
            for s in e["senses"]:
                self.assertEqual(s["gloss_provenance"]["en"], "source_attested")
                self.assertEqual(s["gloss_provenance"]["hi"], "unverified")
                self.assertEqual(s["gloss_provenance"]["as"], "unverified")
                self.assertEqual(s["gloss_provenance"]["bn"], "unverified")
                for lang in ("hi", "as", "bn"):
                    for g in s["definitions"][lang]:
                        self.assertFalse(g["verified"])

    def test_ingnar_and_chikli_presence(self):
        """Authentic cultural and natural terms ingnar (elephant) and chikli (earthquake) exist."""
        repo_root = Path(__file__).resolve().parent.parent
        lex_file = repo_root / "data" / "lexicon" / "core_lexicon.jsonl"

        with open(lex_file, "r", encoding="utf-8") as f:
            entries = {json.loads(line)["headword"]["lemma"]: json.loads(line) for line in f if line.strip()}

        self.assertIn("ingnar", entries)
        self.assertEqual(entries["ingnar"]["senses"][0]["definitions"]["en"], ["elephant"])

        self.assertIn("chikli", entries)
        self.assertEqual(entries["chikli"]["senses"][0]["definitions"]["en"], ["earthquake"])

    def test_per_language_verified_and_unverified_audit_metrics(self):
        """Audit report exposes accurate per-language verified, unverified, and total counts."""
        repo_root = Path(__file__).resolve().parent.parent
        lex_file = repo_root / "data" / "lexicon" / "core_lexicon.jsonl"
        src_file = repo_root / "data" / "sources" / "sources.jsonl"

        validator = DatasetValidator()
        res = validator.validate([lex_file], [src_file])

        self.assertTrue(res.is_valid)
        self.assertEqual(res.lexicon_entries_count, 516)
        self.assertEqual(res.sources_count, 4)

        # Quantitative counts
        self.assertEqual(res.total_glosses_count, 1659)
        self.assertEqual(res.verified_glosses_count, 1097)
        self.assertEqual(res.unverified_glosses_count, 562)

        # Per-language verified counts
        self.assertEqual(res.verified_glosses_by_lang["en"], 1097)
        self.assertEqual(res.verified_glosses_by_lang.get("hi", 0), 0)
        self.assertEqual(res.verified_glosses_by_lang.get("as", 0), 0)
        self.assertEqual(res.verified_glosses_by_lang.get("bn", 0), 0)

        # Per-language unverified counts
        self.assertEqual(res.unverified_glosses_by_lang["en"], 1)
        self.assertEqual(res.unverified_glosses_by_lang["hi"], 206)
        self.assertEqual(res.unverified_glosses_by_lang["as"], 186)
        self.assertEqual(res.unverified_glosses_by_lang["bn"], 169)

        # Citation mismatch tracking
        self.assertEqual(res.citation_mismatch_entries, ["KB-LEX-0000382"])

        # Dict serialization and report formatting
        data = res.as_dict()
        self.assertIn("verified_glosses_count", data)
        self.assertIn("verified_glosses_by_lang", data)
        self.assertIn("total_glosses_count", data)
        self.assertIn("citation_mismatch_entries", data)

        report_str = res.report(verbose=True)
        self.assertIn("Total Definitions/Glosses:   1659", report_str)
        self.assertIn("Verified Glosses:            1097 (66.1%)", report_str)
        self.assertIn("Language 'en':        1097 /  1098 verified", report_str)
        self.assertIn("Language 'hi':           0 /   206 verified", report_str)
        self.assertIn("Mismatch IDs: KB-LEX-0000382", report_str)


if __name__ == "__main__":
    unittest.main()
