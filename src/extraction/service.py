"""Extract original text and table candidates; never infer missing facts."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import fitz
import pdfplumber

from .models import (
    ContentBlock, ExtractedDocument, ExtractedTable, ReviewFinding,
    SourcePage, SourceReference, TableCell,
)


class ExtractionError(RuntimeError):
    """A source PDF cannot be opened or extracted."""


def extract_pdf(
    path: str | Path, *, review_directory: Path | None = None,
    minimum_text_characters: int = 40,
) -> ExtractedDocument:
    """Extract all pages. Review assets are optional, never overwrite assets.

    Native text blocks remain authoritative. Table extraction is supplementary
    and deliberately overlaps text blocks, rather than deleting source content.
    """
    path = Path(path)
    if minimum_text_characters < 0:
        raise ValueError("minimum_text_characters must be nonnegative")
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        document = fitz.open(path)
    except (OSError, fitz.FileDataError, ValueError) as exc:
        raise ExtractionError(f"Cannot open PDF: {path.name}") from exc
    if document.needs_pass or not document.is_pdf or not len(document):
        document.close()
        raise ExtractionError("Expected a nonempty, unencrypted PDF")
    if review_directory is not None:
        try:
            review_directory.mkdir(parents=True, exist_ok=False)
        except OSError:
            document.close()
            raise
    pages, blocks, tables, findings, errors = [], [], [], [], []

    def source(number, bbox):
        return SourceReference(page_number=number, bbox=tuple(bbox))

    def review(page, number, bbox, code, message):
        region_file = None
        if review_directory is not None:
            filename = f"page-{number:03d}-{len(findings):04d}.png"
            target = review_directory / filename
            try:
                # Render with the page's display rotation to match source regions.
                clip = fitz.Rect(bbox) * page.rotation_matrix
                page.get_pixmap(clip=clip, matrix=fitz.Matrix(1.5, 1.5)).save(target)
                region_file = f"{review_directory.name}/{filename}"
            except Exception as exc:
                errors.append(f"Page {number}: review rendering failed ({type(exc).__name__})")
        findings.append(ReviewFinding(
            code=code, message=message, source=source(number, bbox),
            region_file=region_file,
        ))
        return region_file

    try:
        with pdfplumber.open(path) as supplementary:
            for index, page in enumerate(document):
                number = index + 1
                page_bbox = tuple(page.rect * page.derotation_matrix)
                first_finding = len(findings)
                page_blocks, page_tables = [], []
                text = ""
                try:
                    # Exclude image bytes while retaining image metadata/regions.
                    raw = page.get_text("dict", flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)
                    for position, block in enumerate(raw["blocks"]):
                        lines = block.get("lines", [])
                        block_text = "\n".join(
                            "".join(span["text"] for span in line["spans"])
                            for line in lines
                        )
                        block_id = f"p{number:04d}-b{position:04d}"
                        blocks.append(ContentBlock(
                            block_id=block_id, kind="text", text=block_text,
                            source=source(number, block["bbox"]),
                            reading_order=position, lines=json.loads(json.dumps(lines)),
                        ))
                        page_blocks.append(block_id)
                        text += block_text
                    for image_index, image in enumerate(page.get_image_info()):
                        bbox = image["bbox"]
                        block_id = f"p{number:04d}-image{image_index:04d}"
                        blocks.append(ContentBlock(
                            block_id=block_id, kind="image", text="",
                            source=source(number, bbox), reading_order=len(page_blocks),
                        ))
                        page_blocks.append(block_id)
                        review(page, number, bbox, "IMAGE_CONTENT",
                               "Image content has not been transcribed; manual review required.")
                    if len(text.strip()) < minimum_text_characters:
                        review(page, number, page_bbox, "INSUFFICIENT_TEXT",
                               "Sparse extractable text; inspect for scanned or non-text content. No OCR performed.")
                    if "\ufffd" in text:
                        review(page, number, page_bbox, "UNICODE_REPLACEMENT",
                               "Replacement characters indicate possible character mapping loss.")
                    if page.get_drawings():
                        review(page, number, page_bbox, "VECTOR_CONTENT",
                               "Vector graphics may encode diagrams, outlines, or table rules; inspect page.")
                except Exception as exc:
                    errors.append(f"Page {number}: native extraction failed ({type(exc).__name__})")
                    review(page, number, page_bbox, "TEXT_EXTRACTION_FAILED", errors[-1])
                try:
                    # pdfplumber's rotated coordinates differ from native coordinates.
                    if page.rotation:
                        review(page, number, page_bbox, "ROTATED_TABLE_REVIEW",
                               "Supplementary table extraction skipped on rotated page; native text retained.")
                    else:
                        for candidate in supplementary.pages[index].find_tables():
                            rows = candidate.extract()
                            table_id = f"p{number:04d}-t{len(page_tables):04d}"
                            region = review(page, number, candidate.bbox, "TABLE_STRUCTURE_UNVERIFIED",
                                            "Verify headers, merged cells, footnotes and row/column relationships against this source region.")
                            cells = []
                            for row_index, row in enumerate(rows):
                                for column_index, value in enumerate(row):
                                    bbox = candidate.rows[row_index].cells[column_index]
                                    cells.append(TableCell(
                                        row_index=row_index, column_index=column_index,
                                        text=value, source=source(number, bbox) if bbox else None,
                                    ))
                            tables.append(ExtractedTable(
                                table_id=table_id, source=source(number, candidate.bbox),
                                cells=cells, row_count=len(rows),
                                column_count=max((len(row) for row in rows), default=0),
                                region_file=region,
                            ))
                            page_tables.append(table_id)
                except Exception as exc:
                    errors.append(f"Page {number}: table extraction failed ({type(exc).__name__})")
                    review(page, number, page_bbox, "TABLE_EXTRACTION_FAILED", errors[-1])
                pages.append(SourcePage(
                    page_number=number, width=page_bbox[2]-page_bbox[0],
                    height=page_bbox[3]-page_bbox[1], rotation=page.rotation,
                    text_characters=len(text.strip()), block_ids=page_blocks,
                    table_ids=page_tables,
                    status="REVIEW_REQUIRED" if len(findings)>first_finding else "EXTRACTED",
                ))
    except Exception as exc:
        raise ExtractionError("PDF processing failed") from exc
    finally:
        document.close()
    # Broad candidates only: identical column counts never establish a merge.
    for previous, following in zip(pages, pages[1:]):
        for left in tables:
            if left.table_id not in previous.table_ids:
                continue
            for right in tables:
                if right.table_id in following.table_ids and left.column_count == right.column_count:
                    left.continuation_candidate_ids.append(right.table_id)
                    right.continuation_candidate_ids.append(left.table_id)
    return ExtractedDocument(
        document_id=digest, input_filename=path.name,
        processing_timestamp=datetime.now(timezone.utc).isoformat(),
        page_count=len(pages), pages=pages, blocks=blocks, tables=tables,
        findings=findings, errors=errors,
        status="REVIEW_REQUIRED" if findings or errors else "EXTRACTED",
    )
