"""Strict classification decisions reference immutable source records."""
from typing import Literal

from pydantic import Field, model_validator

from src.extraction.models import ExtractedDocument, ExtractedTable, Record, SourceReference

CategoryCode = Literal[
    "UNI-01", "UNI-02", "UNI-03", "UNI-04", "UNI-05", "UNI-06",
    "UNI-07", "UNI-08", "UNI-09", "UNI-10", "UNI-11", "UNI-12",
]


class ContentUnit(Record):
    unit_id: str
    kind: Literal["text", "table", "image"]
    text: str
    source: SourceReference
    source_block_ids: list[str]
    table: ExtractedTable | None = None
    disposition: Literal["CLASSIFY", "REVIEW_ONLY"]
    review_reasons: list[str] = Field(default_factory=list)
    source_line_indices: list[int] = Field(default_factory=list)
    context_ids: list[str] = Field(default_factory=list)


class TableTextAlias(Record):
    source_block_id: str
    line_index: int
    table_id: str
    text: str
    source: SourceReference


class Decision(Record):
    unit_id: str
    category_codes: list[CategoryCode]
    ambiguous: bool
    reason: str
    # Evidence IDs must come from the supplied context, not invented sources.
    evidence_ids: list[str]

    @model_validator(mode="after")
    def valid_categories(self):
        if len(self.category_codes) != len(set(self.category_codes)):
            raise ValueError("Duplicate category assignment")
        if (self.ambiguous or not self.category_codes) and not self.reason.strip():
            raise ValueError("Ambiguous/unclassified decisions need a reason")
        return self


class BatchDecisions(Record):
    decisions: list[Decision]


class ClassifiedRecord(Record):
    unit: ContentUnit
    category_codes: list[CategoryCode]
    ambiguous: bool
    reason: str
    evidence_ids: list[str]
    status: Literal["AI_ASSIGNED_UNVERIFIED", "REVIEW_REQUIRED", "NOT_RUN"]


class ProcessingError(Record):
    unit_ids: list[str]
    code: str


class ClassifiedDocument(Record):
    schema_version: str = "1.0"
    document_id: str
    processing_timestamp: str
    model: str | None
    source_extraction_file: str | None = None
    prompt_version: str = "randyll-classification-1"
    status: Literal["COMPLETE_UNVERIFIED", "PARTIAL", "FAILED", "NOT_RUN"]
    categories: dict[str, str]
    # Includes original blocks, cells, metadata, coordinates and review evidence.
    extracted_document: ExtractedDocument
    records: list[ClassifiedRecord]
    table_text_aliases: list[TableTextAlias]
    errors: list[ProcessingError]
