"""
Core submodule of the Karbi language library.
Contains data models, schema validation logic, JSONL loading, and batch dataset validation.
"""

from karbi.core.bilingual import (
    BilingualEntry,
    BilingualSourceImporter,
    LanguageDirection,
    UncertaintyFlag,
)
from karbi.core.dataset import (
    DatasetError,
    DatasetValidationResult,
    DatasetValidator,
    validate_dataset_files,
)
from karbi.core.loader import (
    JSONLLoadError,
    LoadedRecord,
    load_jsonl_file,
)
from karbi.core.models import (
    AccessLevel,
    DialectMetadata,
    EvidenceRecord,
    Example,
    Headword,
    LexiconEntry,
    OrthographyMetadata,
    Provenance,
    ReviewAuditRecord,
    ReviewerRegistration,
    ReviewerRole,
    Sense,
    SourceRecord,
    SourceType,
    Status,
)
from karbi.core.validator import LexiconValidator, ValidationError

__all__ = [
    # Models & Enums
    "AccessLevel",
    "DialectMetadata",
    "EvidenceRecord",
    "Example",
    "Headword",
    "LexiconEntry",
    "OrthographyMetadata",
    "Provenance",
    "ReviewAuditRecord",
    "ReviewerRegistration",
    "ReviewerRole",
    "Sense",
    "SourceRecord",
    "SourceType",
    "Status",
    # Validation
    "LexiconValidator",
    "ValidationError",
    # Loader
    "JSONLLoadError",
    "LoadedRecord",
    "load_jsonl_file",
    # Dataset Validation
    "DatasetError",
    "DatasetValidationResult",
    "DatasetValidator",
    "validate_dataset_files",
    # Bilingual Ingestion & Review
    "BilingualEntry",
    "BilingualSourceImporter",
    "LanguageDirection",
    "UncertaintyFlag",
]
