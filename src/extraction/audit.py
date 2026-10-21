"""Source-inventory checks; these do not establish semantic accuracy."""
from collections import Counter
from math import isfinite

from .models import ExtractedDocument


def audit_inventory(document: ExtractedDocument) -> dict:
    blocks = {block.block_id: block for block in document.blocks}
    tables = {table.table_id: table for table in document.tables}
    errors = []
    if document.page_count < 1:
        errors.append("Document must have at least one page")
    if len(blocks) != len(document.blocks) or len(tables) != len(document.tables):
        errors.append("Duplicate source IDs")
    if set(blocks) & set(tables):
        errors.append("Block/table ID collision")
    if [page.page_number for page in document.pages] != list(range(1, document.page_count + 1)):
        errors.append("Missing, duplicated, or unordered source pages")
    for page in document.pages:
        expected_blocks = [b.block_id for b in document.blocks if b.source.page_number == page.page_number]
        expected_tables = [t.table_id for t in document.tables if t.source.page_number == page.page_number]
        if page.block_ids != expected_blocks or page.table_ids != expected_tables:
            errors.append(f"Page {page.page_number}: source inventory mismatch")
    page_map = {page.page_number: page for page in document.pages}
    references = [record.source for record in [*document.blocks, *document.tables, *document.findings]]
    references += [cell.source for table in document.tables for cell in table.cells if cell.source]
    for source in references:
        page = page_map.get(source.page_number)
        if page is None:
            errors.append("Source page out of bounds")
            continue
        x0, y0, x1, y1 = source.bbox
        if (not all(isfinite(value) for value in source.bbox)
                or x0 < -2 or y0 < -2 or x1 > page.width + 2 or y1 > page.height + 2):
            errors.append(f"Page {source.page_number}: coordinates outside page bounds")
    for record in document.blocks:
        source = record.source
        if not 1 <= source.page_number <= document.page_count:
            errors.append("Source page out of bounds")
        expected = f"p{source.page_number:04d}-"
        if not record.block_id.startswith(expected):
            errors.append("Block ID/page mismatch")
    for table in document.tables:
        if not table.table_id.startswith(f"p{table.source.page_number:04d}-"):
            errors.append("Table ID/page mismatch")
        if any(cell.source and cell.source.page_number != table.source.page_number for cell in table.cells):
            errors.append("Table cell/page mismatch")
    exact_duplicates = Counter(
        (b.source.page_number, b.source.bbox, b.kind, b.text) for b in document.blocks
    )
    return {
        "document_id": document.document_id,
        "inventory_errors": errors,
        "duplicate_native_records": sum(n - 1 for n in exact_duplicates.values()),
        "block_ids_unique": len(blocks) == len(document.blocks),
        "table_ids_unique": len(tables) == len(document.tables),
        "stable_id_scope": "document SHA-256 + local ID; same bytes and extraction version required",
        "semantic_accuracy": "NOT_VERIFIED",
    }
