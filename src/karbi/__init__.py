"""
Karbi Language Python Library (`karbi`)
=======================================

A comprehensive Python library for Multilingual-to-Karbi translation,
lexicography, grammar, phonetics, and documented cultural heritage.

Primary Translation Direction:
    English  (en) -> Karbi
    Hindi    (hi) -> Karbi
    Assamese (as) -> Karbi
    Bengali  (bn) -> Karbi
"""

from karbi.alphabet import (
    get_aspirates,
    get_consonants,
    get_diphthongs,
    get_phonology_summary,
    get_vowels,
)
from karbi.culture import (
    get_cultural_ethics_policy,
    get_deities,
    get_rituals,
)
from karbi.api import (
    DatasetValidationResult,
    SearchResult,
    batch_lookup,
    batch_search,
    batch_translate,
    get_book,
    get_book_chapters,
    get_book_metadata,
    get_book_passages,
    get_book_statistics,
    get_passage,
    import_book,
    list_books,
    search,
    search_book_text,
    search_books,
    validate_book,
    validate_dataset,
)
from karbi.core.review import (
    CommunityReviewValidationResult,
    validate_community_review_csv,
)
from karbi.cli import main as cli_main
from karbi.dictionary import DictionaryEntry, lookup, lookup_all
from karbi.grammar import (
    count_with_classifier,
    get_cardinals,
    get_classifiers,
    get_pronouns,
)
from karbi.core.session import KarbiSession, session
from karbi.translator import (
    TranslationMatch,
    get_supported_languages,
    translate,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "cli_main",
    # High-Level Unified Python API
    "session",
    "KarbiSession",
    "search",
    "batch_search",
    "batch_lookup",
    "batch_translate",
    "validate_dataset",
    "validate_community_review_csv",
    "DatasetValidationResult",
    "CommunityReviewValidationResult",
    "SearchResult",
    # Multilingual-to-Karbi Translation
    "translate",
    "get_supported_languages",
    "TranslationMatch",
    # Karbi Dictionary
    "lookup",
    "lookup_all",
    "DictionaryEntry",
    # Alphabet and Phonetics
    "get_vowels",
    "get_consonants",
    "get_aspirates",
    "get_diphthongs",
    "get_phonology_summary",
    # Grammar and Classifiers
    "get_classifiers",
    "get_pronouns",
    "get_cardinals",
    "count_with_classifier",
    # Cultural Heritage
    "get_rituals",
    "get_deities",
    "get_cultural_ethics_policy",
    # Digital Book Library API
    "list_books",
    "get_book",
    "get_book_metadata",
    "get_book_chapters",
    "get_passage",
    "get_book_passages",
    "search_books",
    "search_book_text",
    "import_book",
    "validate_book",
    "get_book_statistics",
]
