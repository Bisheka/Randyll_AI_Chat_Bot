"""Build nonduplicated targets while retaining all original source evidence."""
import re
import unicodedata

from src.extraction.audit import audit_inventory
from src.extraction.models import ExtractedDocument, SourceReference

from .models import ContentUnit, TableTextAlias


def _tokens(text: str) -> list[str]:
    return re.findall(
        r"\d+(?:[,.]\d+)*|[^\W\d_]+|[^\w\s]",
        unicodedata.normalize("NFKC", text),
    )


def _contains_tokens(needle: list[str], haystack: list[str]) -> bool:
    # Token boundaries prevent 100 matching 10000, or part of a program name.
    return bool(needle) and any(
        haystack[start:start + len(needle)] == needle
        for start in range(len(haystack) - len(needle) + 1)
    )


def _overlaps(a, b) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def _contained(a, b, tolerance=1.0) -> bool:
    return (a[0] >= b[0] - tolerance and a[1] >= b[1] - tolerance
            and a[2] <= b[2] + tolerance and a[3] <= b[3] + tolerance)


def prepare_units(document: ExtractedDocument) -> tuple[list[ContentUnit], list[TableTextAlias]]:
    audit = audit_inventory(document)
    if audit["inventory_errors"] or audit["duplicate_native_records"]:
        raise ValueError("Invalid or duplicate extraction source inventory")
    units, aliases = [], []
    for table in document.tables:
        table_overlaps = any(
            other.table_id != table.table_id
            and other.source.page_number == table.source.page_number
            and _overlaps(table.source.bbox, other.source.bbox)
            for other in document.tables
        )
        units.append(ContentUnit(
            unit_id=table.table_id, kind="table", text="", source=table.source,
            source_block_ids=[], table=table,
            disposition="REVIEW_ONLY" if table_overlaps else "CLASSIFY",
            review_reasons=["TABLE_STRUCTURE_UNVERIFIED"] + (
                ["OVERLAPPING_TABLE_CANDIDATES"] if table_overlaps else []
            ),
        ))
    for block in document.blocks:
        if block.kind == "image":
            units.append(ContentUnit(
                unit_id=block.block_id, kind="image", text=block.text, source=block.source,
                source_block_ids=[block.block_id], disposition="REVIEW_ONLY",
                review_reasons=["IMAGE_NOT_TRANSCRIBED"],
            ))
            continue
        safe, uncertain = [], []
        lines = block.lines or [{"bbox": block.source.bbox, "spans": [{"text": block.text}]}]
        for index, line in enumerate(lines):
            text = "".join(span["text"] for span in line["spans"])
            bbox = tuple(line["bbox"])
            overlapping = [
                table for table in document.tables
                if table.source.page_number == block.source.page_number
                and _overlaps(bbox, table.source.bbox)
            ]
            matches = []
            for table in overlapping:
                joined = _tokens("\n".join(cell.text or "" for cell in table.cells))
                if _contained(bbox, table.source.bbox) and _contains_tokens(_tokens(text), joined):
                    matches.append(table)
            if len(matches) == 1 and len(overlapping) == 1:
                aliases.append(TableTextAlias(
                    source_block_id=block.block_id, line_index=index,
                    table_id=matches[0].table_id, text=text,
                    source=SourceReference(page_number=block.source.page_number, bbox=bbox),
                ))
            elif overlapping:
                uncertain.append((index, text))
            else:
                safe.append((index, text))
        for suffix, parts, disposition in [
            ("text", safe, "CLASSIFY"), ("overlap", uncertain, "REVIEW_ONLY")
        ]:
            if parts:
                units.append(ContentUnit(
                    unit_id=f"{block.block_id}:{suffix}", kind="text",
                    text="\n".join(text for _, text in parts), source=block.source,
                    source_block_ids=[block.block_id], disposition=disposition,
                    source_line_indices=[index for index, _ in parts],
                    review_reasons=["AMBIGUOUS_TABLE_OVERLAP"] if uncertain and suffix == "overlap" else [],
                ))
    # Full same/adjacent page context retains headings, footnotes, track exceptions
    # and continuation candidates. It is context only, never extra target content.
    for unit in units:
        unit.context_ids = [
            block.block_id for block in document.blocks
            if abs(block.source.page_number - unit.source.page_number) <= 1
            or (block.source.page_number < unit.source.page_number
                and len(block.text) < 300
                and re.match(r"^\s*(?:\d+[.)]|\[(?:Freshman|Transfer)\])", block.text))
        ]
    return units, aliases
