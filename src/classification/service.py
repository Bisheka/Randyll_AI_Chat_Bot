"""Classify source IDs only; all output content is copied from extraction."""
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Literal

from src.extraction.models import ExtractedDocument, Record

from .client import Classifier
from .categories import APPROVED_TITLES
from .models import (
    BatchDecisions, ClassifiedDocument, ClassifiedRecord, ProcessingError,
)
from .preparation import prepare_units


def classify_document(
    document: ExtractedDocument, categories: dict[str, str], *,
    classifier: Classifier | None = None, model: str | None = None,
    batch_size: int = 8, max_payload_characters: int = 60000,
) -> ClassifiedDocument:
    expected_categories = {f"UNI-{i:02d}": title for i, title in enumerate(APPROVED_TITLES, 1)}
    if categories != expected_categories:
        raise ValueError("Exactly the approved category definitions are required")
    if batch_size < 1 or max_payload_characters < 1:
        raise ValueError("Batch size and payload limit must be positive")
    units, aliases = prepare_units(document)
    records = {}
    errors = []
    pending = []
    for unit in units:
        if unit.disposition == "REVIEW_ONLY" or classifier is None:
            records[unit.unit_id] = ClassifiedRecord(
                unit=unit, category_codes=[], ambiguous=unit.disposition == "REVIEW_ONLY",
                reason="; ".join(unit.review_reasons) or "CLASSIFICATION_NOT_RUN",
                evidence_ids=[], status="NOT_RUN" if classifier is None else "REVIEW_REQUIRED",
            )
        else:
            pending.append(unit)

    def table_payload(table):
        # Lossless request projection: page/coordinate system are shared by cells.
        return {
            "table_id": table.table_id, "source": table.source.model_dump(mode="json"),
            "row_count": table.row_count, "column_count": table.column_count,
            "cell_columns": ["row", "column", "original_text", "bbox_or_null"],
            "cells": [[cell.row_index, cell.column_index, cell.text,
                       list(cell.source.bbox) if cell.source else None] for cell in table.cells],
            "continuation_candidate_ids": table.continuation_candidate_ids,
            "status": table.status, "header_status": table.header_status,
        }

    def target_payload(unit):
        target = unit.model_dump(mode="json", exclude={"context_ids", "table"})
        if unit.table is not None:
            target["table"] = table_payload(unit.table)
        return target

    def payload_for(batch):
        context_ids = {identifier for unit in batch for identifier in unit.context_ids}
        return json.dumps({
            "document_id": document.document_id,
            "metadata": document.metadata.model_dump(mode="json"),
            "categories": categories,
            "targets": [target_payload(unit) for unit in batch],
            "context": [{"block_id": block.block_id, "kind": block.kind, "text": block.text,
                         "source": {"page_number": block.source.page_number, "bbox": block.source.bbox}}
                        for block in document.blocks
                        if block.block_id in context_ids],
            "context_tables": [table_payload(table) for table in document.tables
                               if table.table_id not in {unit.unit_id for unit in batch}
                               and any(abs(table.source.page_number-unit.source.page_number) <= 1 for unit in batch)],
        }, ensure_ascii=False, separators=(",", ":"))

    def fail(batch, code):
        errors.append(ProcessingError(unit_ids=[u.unit_id for u in batch], code=code))
        for unit in batch:
            records[unit.unit_id] = ClassifiedRecord(
                unit=unit, category_codes=[], ambiguous=True, reason=code,
                evidence_ids=[], status="REVIEW_REQUIRED",
            )

    # Split by actual serialized size; do not truncate or silently drop context.
    def process(batch):
        if not batch:
            return
        payload = payload_for(batch)
        if len(payload) > max_payload_characters:
            if len(batch) == 1:
                fail(batch, "PAYLOAD_LIMIT_REVIEW_REQUIRED")
            else:
                middle = len(batch) // 2
                process(batch[:middle])
                process(batch[middle:])
            return
        try:
            response = BatchDecisions.model_validate(classifier.classify(payload))
            expected = {u.unit_id for u in batch}
            returned = [decision.unit_id for decision in response.decisions]
            if len(returned) != len(expected) or set(returned) != expected:
                raise ValueError("Response must contain each target exactly once")
            allowed = {b.block_id for b in document.blocks if any(b.block_id in u.context_ids for u in batch)}
            allowed |= {t.table_id for t in document.tables if any(abs(t.source.page_number-u.source.page_number) <= 1 for u in batch)}
            allowed |= expected
            by_id = {decision.unit_id: decision for decision in response.decisions}
            for decision in response.decisions:
                if any(code not in categories for code in decision.category_codes):
                    raise ValueError("Unconfigured category")
                if not set(decision.evidence_ids) <= allowed:
                    raise ValueError("Unknown evidence ID")
                if decision.category_codes and not decision.evidence_ids:
                    raise ValueError("Assigned content requires source evidence")
            for unit in batch:
                decision = by_id[unit.unit_id]
                review = bool(unit.review_reasons or decision.ambiguous or not decision.category_codes)
                records[unit.unit_id] = ClassifiedRecord(
                    unit=unit, category_codes=decision.category_codes,
                    ambiguous=decision.ambiguous, reason=decision.reason,
                    evidence_ids=decision.evidence_ids,
                    status="REVIEW_REQUIRED" if review else "AI_ASSIGNED_UNVERIFIED",
                )
        except Exception as exc:
            # Do not log exception text: SDK errors may contain sensitive payloads.
            fail(batch, f"CLASSIFICATION_FAILED_{type(exc).__name__}")

    for start in range(0, len(pending), batch_size):
        process(pending[start:start + batch_size])
    if classifier is None:
        status = "NOT_RUN"
    elif errors:
        status = "PARTIAL" if any(r.category_codes for r in records.values()) else "FAILED"
    else:
        status = "COMPLETE_UNVERIFIED"
    return ClassifiedDocument(
        document_id=document.document_id,
        processing_timestamp=datetime.now(timezone.utc).isoformat(), model=model,
        status=status, categories=categories, extracted_document=document,
        records=[records[unit.unit_id] for unit in units],
        table_text_aliases=aliases, errors=errors,
    )


class ClassificationReport(Record):
    document_id: str
    status: Literal["COMPLETE_UNVERIFIED", "PARTIAL", "FAILED", "NOT_RUN"]
    model: str | None
    category_counts: dict[str, int]
    unit_count: int
    assigned_unit_count: int
    unclassified_unit_ids: list[str]
    ambiguous_unit_ids: list[str]
    review_required_unit_ids: list[str]
    not_run_unit_ids: list[str]
    suppressed_table_text_line_count: int
    processing_errors: list[ProcessingError]
    semantic_accuracy: Literal["NOT_VERIFIED"] = "NOT_VERIFIED"
    note: str = "Multi-category counts may exceed assigned units. All source records remain in extracted_document."


def build_classification_report(result: ClassifiedDocument) -> ClassificationReport:
    counts = Counter(code for record in result.records for code in record.category_codes)
    return ClassificationReport(
        document_id=result.document_id, status=result.status, model=result.model,
        category_counts={code: counts[code] for code in result.categories},
        unit_count=len(result.records),
        assigned_unit_count=sum(bool(r.category_codes) for r in result.records),
        unclassified_unit_ids=[r.unit.unit_id for r in result.records if not r.category_codes],
        ambiguous_unit_ids=[r.unit.unit_id for r in result.records if r.ambiguous],
        review_required_unit_ids=[r.unit.unit_id for r in result.records
                                  if r.status == "REVIEW_REQUIRED" or r.unit.review_reasons],
        not_run_unit_ids=[r.unit.unit_id for r in result.records if r.status == "NOT_RUN"],
        suppressed_table_text_line_count=len(result.table_text_aliases),
        processing_errors=result.errors,
    )
