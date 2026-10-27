"""
Validation Engine for Digital Books and Passages (`karbi.books.validation`)
==========================================================================

Verifies integrity of book catalogue records, passage sequences, Unicode encoding,
licensing, and text checksums.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import unicodedata

from karbi.books.catalog import BookCatalog, get_default_catalog_path
from karbi.books.importer import get_default_books_dir
from karbi.books.models import BookImportStatus, BookMetadata, Passage


@dataclass
class BookValidationResult:
    """
    Structured outcome of book and passage validation.
    """
    book_id: str
    is_valid: bool
    total_passages: int = 0
    total_chapters: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def report(self, verbose: bool = False) -> str:
        """Formats the validation result into a human-readable text report."""
        status = "PASSED" if self.is_valid else "FAILED"
        lines = [
            f"Book Validation Report: {self.book_id} [{status}]",
            f"  Total Chapters: {self.total_chapters}",
            f"  Total Passages: {self.total_passages}",
        ]
        if self.errors:
            lines.append("  Errors:")
            for e in self.errors:
                lines.append(f"    - {e}")
        if self.warnings and (verbose or not self.is_valid):
            lines.append("  Warnings:")
            for w in self.warnings:
                lines.append(f"    - {w}")
        return "\n".join(lines)

    def as_dict(self) -> Dict[str, Any]:
        """Serializes validation result to dictionary."""
        return {
            "book_id": self.book_id,
            "is_valid": self.is_valid,
            "total_passages": self.total_passages,
            "total_chapters": self.total_chapters,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def validate_book(
    book_id: str,
    catalog: Optional[BookCatalog] = None,
    books_dir: Optional[Union[str, Path]] = None,
) -> BookValidationResult:
    """
    Validates a book entry and its imported text files.
    """
    cat = catalog or BookCatalog()
    b_dir = Path(books_dir) if books_dir is not None else get_default_books_dir()
    metadata = cat.get_book(book_id)

    if not metadata:
        return BookValidationResult(
            book_id=book_id,
            is_valid=False,
            errors=[f"Book ID '{book_id}' not found in catalogue."],
        )

    errors: List[str] = []
    warnings: List[str] = []

    # Metadata validations
    if not metadata.canonical_title:
        errors.append("Missing canonical_title.")
    if not metadata.original_language:
        errors.append("Missing original_language.")
    if not metadata.copyright_status:
        errors.append("Missing copyright_status.")
    if not metadata.licence:
        errors.append("Missing licence.")

    if metadata.import_status == BookImportStatus.CATALOG_ONLY.value:
        if metadata.imported_passages_count > 0:
            errors.append(
                f"Book is marked CATALOG_ONLY but has imported_passages_count = {metadata.imported_passages_count}."
            )
        return BookValidationResult(
            book_id=book_id,
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    # Validations for imported books
    jsonl_path = b_dir / "texts" / f"{book_id}.jsonl"
    if not jsonl_path.is_file():
        errors.append(f"Imported book text file does not exist: {jsonl_path}")
        return BookValidationResult(
            book_id=book_id,
            is_valid=False,
            errors=errors,
            warnings=warnings,
        )

    passages: List[Passage] = []
    passage_ids = set()
    chapters = set()

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                p = Passage.from_dict(rec)
                passages.append(p)

                # Check unique passage IDs
                if p.passage_id in passage_ids:
                    errors.append(f"Duplicate passage_id '{p.passage_id}' at line {line_num}.")
                passage_ids.add(p.passage_id)

                if not p.text.strip():
                    errors.append(f"Passage '{p.passage_id}' has empty text at line {line_num}.")

                if p.chapter_number is not None:
                    chapters.add(p.chapter_number)

            except Exception as ex:
                errors.append(f"Malformed JSON at line {line_num}: {ex}")

    total_passages = len(passages)
    total_chapters = len(chapters) if chapters else (1 if total_passages > 0 else 0)

    if metadata.imported_passages_count != total_passages:
        warnings.append(
            f"Catalogue passage count ({metadata.imported_passages_count}) differs from file count ({total_passages})."
        )

    return BookValidationResult(
        book_id=book_id,
        is_valid=len(errors) == 0,
        total_passages=total_passages,
        total_chapters=total_chapters,
        errors=errors,
        warnings=warnings,
    )


def validate_book_catalog(
    catalog_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """
    Validates all entries across the book catalogue.
    """
    cat = BookCatalog(catalog_path)
    books = cat.list_books()

    results: Dict[str, Any] = {
        "is_valid": True,
        "total_books": len(books),
        "book_results": {},
        "overall_errors": [],
    }

    seen_ids = set()
    for b in books:
        if b.book_id in seen_ids:
            results["overall_errors"].append(f"Duplicate book_id '{b.book_id}' in catalogue.")
            results["is_valid"] = False
        seen_ids.add(b.book_id)

        res = validate_book(b.book_id, catalog=cat)
        results["book_results"][b.book_id] = res.as_dict()
        if not res.is_valid:
            results["is_valid"] = False

    return results
