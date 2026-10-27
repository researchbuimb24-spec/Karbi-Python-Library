"""
Tests for Karbi Command-Line Interface (`karbi.cli`).
======================================================
"""

import json
import subprocess
import sys
from io import StringIO
from pathlib import Path
from typing import List

import pytest
from karbi.cli import build_parser, main

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_cli_capture(args: List[str]) -> tuple[int, str, str]:
    """Helper to run the CLI in-process and capture stdout/stderr."""
    old_stdout, old_stderr = sys.stdout, sys.stderr
    out_buf, err_buf = StringIO(), StringIO()
    sys.stdout, sys.stderr = out_buf, err_buf
    try:
        ret = main(args)
        return ret, out_buf.getvalue(), err_buf.getvalue()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 0
        return code, out_buf.getvalue(), err_buf.getvalue()
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr


class TestCommandLineInterface:
    """Comprehensive tests for karbi CLI commands, formats, and safety rules."""

    def test_cli_help(self):
        """CLI with --help outputs usage text and returns exit code 0."""
        ret, out, err = run_cli_capture(["--help"])
        assert ret == 0
        assert "usage: karbi" in out
        assert "lookup" in out
        assert "translate" in out
        assert "search" in out
        assert "languages" in out

    def test_cli_version(self):
        """CLI with --version outputs version and exits with 0."""
        # argparse version action raises SystemExit(0)
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0

    def test_cli_no_args_shows_help(self):
        """Running karbi with no arguments outputs help and exits with 0."""
        ret, out, err = run_cli_capture([])
        assert ret == 0
        assert "usage: karbi" in out

    def test_cli_lookup_karbi_headword(self):
        """Search for a Karbi word displays lemma, IPA, citations, and meanings."""
        ret, out, err = run_cli_capture(["lookup", "arlèng"])
        assert ret == 0
        assert "KARBI HEADWORD: arlèng" in out
        assert "/aɾˈlɛŋ/" in out
        assert "The Mikirs (p. 74, 80)" in out
        assert "English" in out
        assert "[SOURCE ATTESTED]" in out
        assert "Hindi" in out
        assert "[UNVERIFIED]" in out
        assert "Assamese" in out
        assert "Bengali" in out

    def test_cli_lookup_spelling_variant(self):
        """Search using contemporary spelling variant without diacritics finds headword."""
        ret, out, err = run_cli_capture(["lookup", "hem"])
        assert ret == 0
        assert "KARBI HEADWORD: hèm" in out
        assert "/hɛm/" in out
        assert "The Mikirs (p. 77, 79)" in out

    def test_cli_lookup_missing_word(self):
        """Missing Karbi word exits cleanly with code 1 and prints suggestions."""
        ret, out, err = run_cli_capture(["lookup", "nonexistentword"])
        assert ret == 1
        assert "No Karbi dictionary entry found for: 'nonexistentword'" in err
        assert "Check diacritics" in err

    def test_cli_lookup_json(self):
        """Lookup with --json flag outputs valid structured JSON."""
        ret, out, err = run_cli_capture(["lookup", "arlèng", "--json"])
        assert ret == 0
        data = json.loads(out)
        assert data["found"] is True
        assert data["query"] == "arlèng"
        assert data["entry"]["lemma"] == "arlèng"
        assert data["entry"]["phonetics_ipa"] == "/aɾˈlɛŋ/"
        assert len(data["entry"]["source_citations"]) > 0

    def test_cli_lookup_missing_json(self):
        """Missing word lookup with --json outputs valid JSON with found: false."""
        ret, out, err = run_cli_capture(["lookup", "unknownxyz", "--json"])
        assert ret == 1
        data = json.loads(out)
        assert data["found"] is False
        assert data["results"] == []

    def test_cli_translate_english(self):
        """Search using English finds matching Karbi entries with pronunciation and citations."""
        ret, out, err = run_cli_capture(["translate", "water", "--from", "en"])
        assert ret == 0
        assert "TRANSLATION RESULTS: 'water'" in out
        assert "Karbi Lemma:   làng (noun)" in out
        assert "Pronunciation: /laŋ/" in out
        assert "The Mikirs (p. 10)" in out
        assert "[SOURCE ATTESTED]" in out

    def test_cli_translate_indic_unverified_labeling(self):
        """Hindi, Assamese, and Bengali translations clearly label unverified glosses."""
        # Test Hindi query
        ret_hi, out_hi, _ = run_cli_capture(["translate", "पानी", "--from", "hi"])
        assert ret_hi == 0
        assert "Karbi Lemma:   làng (noun)" in out_hi
        assert "[UNVERIFIED]" in out_hi
        assert "CAUTION:   This translation gloss is unverified" in out_hi

        # Test Assamese query
        ret_as, out_as, _ = run_cli_capture(["translate", "পানী", "--from", "as"])
        assert ret_as == 0
        assert "Karbi Lemma:   làng (noun)" in out_as
        assert "[UNVERIFIED]" in out_as
        assert "CAUTION:   This translation gloss is unverified" in out_as

        # Test Bengali query
        ret_bn, out_bn, _ = run_cli_capture(["translate", "জল", "--from", "bn"])
        assert ret_bn == 0
        assert "Karbi Lemma:   làng (noun)" in out_bn
        assert "[UNVERIFIED]" in out_bn
        assert "CAUTION:   This translation gloss is unverified" in out_bn

    def test_cli_translate_verified_only_filters_unverified(self):
        """The --verified-only flag excludes unverified translations and reports clean status."""
        ret, out, err = run_cli_capture(["translate", "पानी", "--from", "hi", "--verified-only"])
        assert ret == 1
        assert "No matching Karbi entries found" in err
        assert "(verified only)" in err

    def test_cli_translate_missing_term(self):
        """Missing translation query exits cleanly with code 1 and helpful suggestions."""
        ret, out, err = run_cli_capture(["translate", "qwertyuiop", "--from", "en"])
        assert ret == 1
        assert "No matching Karbi entries found for: 'qwertyuiop'" in err
        assert "Check spelling or search synonyms" in err

    def test_cli_translate_json(self):
        """Translate with --json outputs valid JSON results."""
        ret, out, err = run_cli_capture(["translate", "water", "--from", "en", "--json"])
        assert ret == 0
        data = json.loads(out)
        assert data["found"] is True
        assert data["count"] >= 1
        assert data["results"][0]["karbi_lemma"] == "làng"
        assert data["results"][0]["phonetics_ipa"] == "/laŋ/"

    def test_cli_direct_word_query_auto_routing(self):
        """Passing word directly without subcommand routes automatically to search."""
        # Karbi word direct query
        ret_k, out_k, _ = run_cli_capture(["arlèng"])
        assert ret_k == 0
        assert "KARBI HEADWORD: arlèng" in out_k

        # English translation direct query
        ret_e, out_e, _ = run_cli_capture(["water"])
        assert ret_e == 0
        assert "TRANSLATION RESULTS: 'water'" in out_e

    def test_cli_languages(self):
        """The languages subcommand lists supported translation languages and their status."""
        ret, out, err = run_cli_capture(["languages"])
        assert ret == 0
        assert "SUPPORTED SOURCE LANGUAGES FOR KARBI TRANSLATION" in out
        assert "English" in out
        assert "Hindi" in out
        assert "Assamese" in out
        assert "Bengali" in out
        assert "Marathi" in out

    def test_cli_languages_json(self):
        """The languages subcommand with --json outputs JSON registry."""
        ret, out, err = run_cli_capture(["languages", "--json"])
        assert ret == 0
        data = json.loads(out)
        assert "en" in data
        assert "hi" in data
        assert "as" in data
        assert "bn" in data

    def test_cli_empty_query_error(self):
        """Searching with whitespace or empty query returns error code 2."""
        ret, out, err = run_cli_capture(["search", "   "])
        assert ret == 2
        assert "Error: Search query cannot be empty" in err

    def test_python_module_execution(self):
        """Running python -m karbi via subprocess confirms entrypoint works."""
        import os
        from pathlib import Path
        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent / "src")
        proc = subprocess.run(
            [sys.executable, "-m", "karbi", "lookup", "arlèng"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        assert proc.returncode == 0
        assert "KARBI HEADWORD: arlèng" in proc.stdout
        assert "/aɾˈlɛŋ/" in proc.stdout

    def test_cli_lookup_homonyms(self):
        """Looking up a word with multiple homonyms displays all matching entries."""
        # JSON mode
        ret_j, out_j, _ = run_cli_capture(["lookup", "cho", "--json"])
        assert ret_j == 0
        data = json.loads(out_j)
        assert data["found"] is True
        assert len(data["entries"]) == 2
        entry_ids = [e["entry_id"] for e in data["entries"]]
        assert "KB-LEX-0000154" in entry_ids
        assert "KB-LEX-0000323" in entry_ids

        # Text mode
        ret_t, out_t, _ = run_cli_capture(["lookup", "cho"])
        assert ret_t == 0
        assert "KB-LEX-0000154" in out_t or "to eat" in out_t
        assert "axe" in out_t or "hatchet" in out_t

    def test_cli_search_verified_only_finds_attested_entry(self):
        """karbi search <word> --verified-only successfully finds source-attested entries."""
        ret, out, err = run_cli_capture(["search", "arlèng", "--verified-only"])
        assert ret == 0
        assert "KARBI HEADWORD: arlèng" in out
        assert "/aɾˈlɛŋ/" in out

    def test_cli_search_verified_only_excludes_citation_mismatch(self):
        """karbi search <word> --verified-only excludes citation-mismatch records."""
        ret, out, err = run_cli_capture(["search", "kāthē", "--verified-only"])
        assert ret == 1
        assert "No matching Karbi entries found for 'kāthē'" in err

    def test_cli_lookup_verified_only_finds_attested_and_excludes_mismatch(self):
        """karbi lookup --verified-only finds attested words but excludes citation-mismatches."""
        # Attested word finds entry
        ret_ok, out_ok, _ = run_cli_capture(["lookup", "arlèng", "--verified-only"])
        assert ret_ok == 0
        assert "KARBI HEADWORD: arlèng" in out_ok

        # Citation-mismatch entry is excluded
        ret_mismatch, _, err_mismatch = run_cli_capture(["lookup", "kāthē", "--verified-only"])
        assert ret_mismatch == 1
        assert "No Karbi dictionary entry found for: 'kāthē' (verified only)" in err_mismatch

    def test_cli_validate_review_csv(self):
        """karbi validate --review-csv audits community submissions."""
        template_path = str(PROJECT_ROOT / "docs" / "community_gloss_review_template.csv")
        ret, out, _ = run_cli_capture(["validate", "--review-csv", template_path])
        assert ret == 0
        assert "KARBI COMMUNITY REVIEW SUBMISSION AUDIT REPORT" in out
        assert "PASSED [VALID]" in out
        assert "Total Submissions:          0 (Header-only template)" in out
        assert "Review Decisions Breakdown:" in out

    def test_cli_validate_review_csv_json(self):
        """karbi validate --review-csv --json outputs structured validation report."""
        template_path = str(PROJECT_ROOT / "docs" / "community_gloss_review_template.csv")
        ret, out, _ = run_cli_capture(["validate", "--review-csv", template_path, "--json"])
        assert ret == 0
        data = json.loads(out)
        assert data["is_valid"] is True
        assert data["submissions_count"] == 0
        assert data["is_empty_template"] is True
        assert "submissions" in data
