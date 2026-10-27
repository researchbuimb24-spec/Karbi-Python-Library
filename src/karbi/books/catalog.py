"""
Book Catalogue Management Engine (`karbi.books.catalog`)
========================================================

Provides access, filtering, registration, and statistics for the digital book library.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from karbi.books.models import BookImportStatus, BookMetadata


def get_default_catalog_path() -> Path:
    """
    Returns the path to the book catalogue JSON file.
    Resolves repository root `data/books/catalog.json` or fallback user data path.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    repo_cat = repo_root / "data" / "books" / "catalog.json"
    if repo_cat.is_file():
        return repo_cat

    # Fallback to package resources if available
    pkg_cat = Path(__file__).resolve().parent.parent / "resources" / "books" / "catalog.json"
    if pkg_cat.is_file():
        return pkg_cat

    # Fallback default
    return repo_cat


class BookCatalog:
    """
    In-memory and file-backed manager for book metadata catalogue records.
    """

    def __init__(self, catalog_path: Optional[Union[str, Path]] = None):
        self.catalog_path = Path(catalog_path) if catalog_path is not None else get_default_catalog_path()
        self._books: Dict[str, BookMetadata] = {}
        self.load()

    def load(self) -> None:
        """Loads catalogue records from JSON file."""
        self._books.clear()
        if not self.catalog_path.is_file():
            return

        with open(self.catalog_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            for item in data:
                bm = BookMetadata.from_dict(item)
                self._books[bm.book_id] = bm
        elif isinstance(data, dict):
            for book_id, item in data.items():
                if "book_id" not in item:
                    item["book_id"] = book_id
                bm = BookMetadata.from_dict(item)
                self._books[bm.book_id] = bm

    def save(self) -> None:
        """Atomically saves the catalogue records to disk."""
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.catalog_path.with_suffix(".tmp")
        serializable = [b.to_dict() for b in self._books.values()]
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)
        temp_path.replace(self.catalog_path)

    def list_books(
        self,
        import_status: Optional[Union[str, BookImportStatus]] = None,
        language: Optional[str] = None,
        document_type: Optional[str] = None,
    ) -> List[BookMetadata]:
        """
        Lists books in the catalogue matching optional filters.
        """
        results: List[BookMetadata] = []
        target_status = import_status.value if isinstance(import_status, BookImportStatus) else import_status
        for bm in self._books.values():
            if target_status and bm.import_status != target_status:
                continue
            if language and bm.original_language.lower() != language.lower():
                continue
            if document_type and bm.document_type.lower() != document_type.lower():
                continue
            results.append(bm)
        return sorted(results, key=lambda b: b.book_id)

    def get_book(self, book_id: str) -> Optional[BookMetadata]:
        """Retrieves a book by its stable book_id."""
        return self._books.get(book_id)

    def add_book(self, metadata: BookMetadata, overwrite: bool = False) -> None:
        """Adds a new book record to the catalogue."""
        if metadata.book_id in self._books and not overwrite:
            raise ValueError(
                f"Book with ID '{metadata.book_id}' already exists in catalogue. "
                f"Set overwrite=True to replace."
            )
        self._books[metadata.book_id] = metadata
        self.save()

    def update_book(self, metadata: BookMetadata) -> None:
        """Updates an existing book record in the catalogue."""
        self._books[metadata.book_id] = metadata
        self.save()

    def get_stats(self) -> Dict[str, Any]:
        """Calculates aggregated catalogue statistics."""
        total_books = len(self._books)
        fully_imported = sum(
            1 for b in self._books.values() if b.import_status == BookImportStatus.FULLY_IMPORTED.value
        )
        partially_imported = sum(
            1 for b in self._books.values() if b.import_status == BookImportStatus.PARTIALLY_IMPORTED.value
        )
        catalog_only = sum(
            1 for b in self._books.values() if b.import_status == BookImportStatus.CATALOG_ONLY.value
        )
        total_imported_passages = sum(b.imported_passages_count for b in self._books.values())
        total_imported_chapters = sum(b.imported_chapters_count for b in self._books.values())

        languages: Dict[str, int] = {}
        document_types: Dict[str, int] = {}
        for b in self._books.values():
            languages[b.original_language] = languages.get(b.original_language, 0) + 1
            document_types[b.document_type] = document_types.get(b.document_type, 0) + 1

        return {
            "total_books": total_books,
            "fully_imported_books": fully_imported,
            "partially_imported_books": partially_imported,
            "catalog_only_books": catalog_only,
            "total_imported_passages": total_imported_passages,
            "total_imported_chapters": total_imported_chapters,
            "languages": languages,
            "document_types": document_types,
        }
