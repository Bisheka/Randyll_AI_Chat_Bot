"""Serializable source records. Coordinates use top-left PDF points."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceReference(Record):
    page_number: int = Field(ge=1)
    bbox: tuple[float, float, float, float]
    coordinate_system: Literal["unrotated_top_left_pdf_points"] = (
        "unrotated_top_left_pdf_points"
    )

    @model_validator(mode="after")
    def ordered_bbox(self):
        x0, y0, x1, y1 = self.bbox
        if x1 < x0 or y1 < y0:
            raise ValueError("Bounding box must have ordered coordinates")
        return self


class ReviewFinding(Record):
    code: str
    message: str
    source: SourceReference
    region_file: str | None = None
    status: Literal["REVIEW_REQUIRED"] = "REVIEW_REQUIRED"


class ContentBlock(Record):
    block_id: str
    kind: Literal["text", "image"]
    text: str
    source: SourceReference
    reading_order: int
    # Retain span structure without guessing headings, lists, or footnotes.
    lines: list[dict] = Field(default_factory=list)


class TableCell(Record):
    row_index: int = Field(ge=0)
    column_index: int = Field(ge=0)
    text: str | None
    source: SourceReference | None


class ExtractedTable(Record):
    table_id: str
    source: SourceReference
    cells: list[TableCell]
    row_count: int
    column_count: int
    region_file: str | None = None
    # No speculative header or cross-page merge is treated as established.
    header_status: Literal["UNVERIFIED"] = "UNVERIFIED"
    continuation_candidate_ids: list[str] = Field(default_factory=list)
    status: Literal["REVIEW_REQUIRED"] = "REVIEW_REQUIRED"


class SourcePage(Record):
    page_number: int
    width: float
    height: float
    rotation: int
    text_characters: int
    block_ids: list[str]
    table_ids: list[str]
    status: Literal["EXTRACTED", "REVIEW_REQUIRED"]


class DocumentMetadata(Record):
    university_id: str | None = None
    university_name: str | None = None
    academic_year: int | None = None
    semester: str | None = None
    admission_level: str | None = None
    admission_type: str | None = None
    document_version: str | None = None


class ExtractedDocument(Record):
    schema_version: str = "1.0"
    document_id: str
    input_filename: str
    processing_timestamp: str
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    page_count: int
    pages: list[SourcePage]
    blocks: list[ContentBlock]
    tables: list[ExtractedTable]
    findings: list[ReviewFinding]
    errors: list[str]
    status: Literal["EXTRACTED", "REVIEW_REQUIRED"]
