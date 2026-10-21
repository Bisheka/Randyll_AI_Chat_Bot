"""Run with python -m src.extraction INPUT.pdf --output NEW_DIRECTORY."""
import argparse
import json
from pathlib import Path

from .service import ExtractionError, extract_pdf
from .reporting import build_coverage_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error("Input file does not exist")
    try:
        args.output.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error("Output directory already exists; choose a new directory")
    try:
        result = extract_pdf(args.input, review_directory=args.output / "review_regions")
    except ExtractionError as exc:
        (args.output / "extraction_failure.json").write_text(
            json.dumps({"status": "FAILED", "error": str(exc)}), encoding="utf-8"
        )
        parser.exit(1, f"Extraction failed: {exc}\n")
    (args.output / "extracted_content.json").write_text(
        result.model_dump_json(indent=2), encoding="utf-8"
    )
    coverage = build_coverage_report(result)
    (args.output / "coverage_report.json").write_text(
        coverage.model_dump_json(indent=2), encoding="utf-8"
    )
    summary = {
        "input_filename": result.input_filename,
        "processing_timestamp": result.processing_timestamp,
        "document_id": result.document_id, "status": result.status,
        "classification_status": "NOT_RUN",
        "unclassified_items": len(coverage.unclassified_items),
        "coverage_report": "coverage_report.json",
        "pages": result.page_count, "blocks": len(result.blocks),
        "tables": len(result.tables), "review_findings": len(result.findings),
        "errors": result.errors,
        "note": "Extraction only. Classification and categorized PDFs are not yet implemented.",
    }
    (args.output / "extraction_report.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
