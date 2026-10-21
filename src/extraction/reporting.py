"""Deterministic extraction coverage, without semantic classification."""
from typing import Literal

from pydantic import Field

from .models import ExtractedDocument, Record, SourceReference


class UnclassifiedItem(Record):
    content_id: str
    kind: Literal["text", "image", "table"]
    source: SourceReference
    reason: Literal["CLASSIFICATION_NOT_RUN"] = "CLASSIFICATION_NOT_RUN"


class CoverageReport(Record):
    document_id: str
    classification_status: Literal["NOT_RUN"] = "NOT_RUN"
    source_page_count: int = Field(ge=1)
    covered_page_numbers: list[int]
    missing_page_numbers: list[int]
    unclassified_items: list[UnclassifiedItem]
    note: str = (
        "Every extracted block and supplementary table is listed. Tables overlap "
        "native text. Coverage records extraction inventory, not semantic accuracy "
        "or proof that every visible mark was captured. No categories assigned."
    )


def build_coverage_report(document: ExtractedDocument) -> CoverageReport:
    """Inventory every record, including content outside any future category."""
    covered = sorted({page.page_number for page in document.pages})
    return CoverageReport(
        document_id=document.document_id,
        source_page_count=document.page_count,
        covered_page_numbers=covered,
        missing_page_numbers=sorted(set(range(1, document.page_count + 1)) - set(covered)),
        unclassified_items=[
            UnclassifiedItem(content_id=block.block_id, kind=block.kind, source=block.source)
            for block in document.blocks
        ] + [
            UnclassifiedItem(content_id=table.table_id, kind="table", source=table.source)
            for table in document.tables
        ],
    )
