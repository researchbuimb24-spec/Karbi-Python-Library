"""
Tests for Bilingual Source Ingestion and Review Engine (`karbi.core.bilingual`).
"""

import tempfile
from pathlib import Path
import pytest

from karbi.core.bilingual import (
    BilingualEntry,
    BilingualSourceImporter,
    LanguageDirection,
    UncertaintyFlag,
)
from karbi.core.models import Status


def test_bilingual_entry_serialization():
    entry = BilingualEntry(
        source_id="SRC-PUB-00003",
        locator="p. 75, Sentence 1",
        source_wording="I shall reside here about one year.",
        karbi_form="Ne ludak ningkan isibak do po.",
        language_direction=LanguageDirection.EN_TO_KARBI.value,
        part_of_speech="sentence",
        extracted_text_quote="1. I shall reside here about one year. / Ne ludak ningkan isibak do po.",
        verification_status=Status.SOURCE_ATTESTED.value,
        uncertainty_flags=[UncertaintyFlag.TONE_NOT_INDICATED.value],
        reviewer_role="linguist",
        reviewer_attribution="Archival Ingestion",
        dialect="rongkhang",
        notes="Illustrative sentence from Neighbor 1878"
    )

    data = entry.to_dict()
    assert data["source_id"] == "SRC-PUB-00003"
    assert data["locator"] == "p. 75, Sentence 1"
    assert data["source_wording"] == "I shall reside here about one year."
    assert data["karbi_form"] == "Ne ludak ningkan isibak do po."
    assert UncertaintyFlag.TONE_NOT_INDICATED.value in data["uncertainty_flags"]

    recovered = BilingualEntry.from_dict(data)
    assert recovered.source_id == entry.source_id
    assert recovered.karbi_form == entry.karbi_form
    assert recovered.uncertainty_flags == entry.uncertainty_flags


def test_bilingual_community_review_row():
    entry = BilingualEntry(
        entry_id="KB-REV-001",
        source_id="SRC-PUB-00003",
        locator="p. 75, Sentence 1",
        source_wording="reside",
        karbi_form="do",
        language_direction=LanguageDirection.EN_TO_KARBI.value,
        uncertainty_flags=[UncertaintyFlag.ARCHAIC_ORTHOGRAPHY.value]
    )

    row = entry.to_community_review_row()
    assert row["entry_id"] == "KB-REV-001"
    assert row["source_language"] == "en"
    assert row["source_word"] == "reside"
    assert row["proposed_karbi_form"] == "do"
    assert row["decision"] == "awaiting_review"
    assert "ARCHAIC_ORTHOGRAPHY" in row["notes"]


def test_bilingual_importer_validation():
    importer = BilingualSourceImporter()

    # Valid entry
    valid_entry = BilingualEntry(
        source_id="SRC-PUB-00003",
        locator="p. 75, Sentence 1",
        source_wording="house",
        karbi_form="hem"
    )
    errors = importer.validate_entry(valid_entry)
    assert len(errors) == 0

    # Invalid source_id
    invalid_src = BilingualEntry(
        source_id="SRC-FAKE-99999",
        locator="p. 1",
        source_wording="house",
        karbi_form="hem"
    )
    errors = importer.validate_entry(invalid_src)
    assert any("not registered" in e for e in errors)

    # Missing fields
    missing = BilingualEntry(
        source_id="",
        locator="",
        source_wording="",
        karbi_form=""
    )
    errors = importer.validate_entry(missing)
    assert len(errors) >= 3


def test_bilingual_export_review_csv(tmp_path):
    importer = BilingualSourceImporter()
    entries = [
        BilingualEntry(
            source_id="SRC-PUB-00003",
            locator="p. 75, Sentence 1",
            source_wording="I shall reside here about one year.",
            karbi_form="Ne ludak ningkan isibak do po."
        ),
        BilingualEntry(
            source_id="SRC-PUB-00003",
            locator="p. 75, Sentence 2",
            source_wording="What is he about?",
            karbi_form="La kopi kang-hoy lo?"
        ),
    ]

    csv_file = tmp_path / "test_review.csv"
    count = importer.export_review_csv(entries, csv_file)
    assert count == 2
    assert csv_file.is_file()

    lines = csv_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3  # header + 2 rows
    assert "entry_id,source_language,source_word" in lines[0]
    assert "Ne ludak ningkan isibak do po." in lines[1]
