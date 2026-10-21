"""Classify validated extraction JSON; never generate PDFs."""
import argparse
from pathlib import Path

from dotenv import load_dotenv

from src.extraction.models import ExtractedDocument
from src.extraction.audit import audit_inventory
from .categories import load_categories
from .client import OpenAIClassifier, OpenAISettings
from .service import build_classification_report, classify_document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--categories", type=Path, default=Path("config/categories.yaml"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--prepare-only", action="store_true", help="Inventory units without API calls")
    args = parser.parse_args()
    try:
        document = ExtractedDocument.model_validate_json(args.input.read_text(encoding="utf-8"))
        audit = audit_inventory(document)
        if audit["inventory_errors"] or audit["duplicate_native_records"]:
            raise ValueError("Invalid extraction inventory")
        categories = load_categories(args.categories)
        client = None
        model = None
        if not args.prepare_only:
            load_dotenv(Path.cwd() / ".env", override=False)
            settings = OpenAISettings.from_environment()
            model = settings.model
            client = OpenAIClassifier(settings)
        # Refuse collisions before making any billable requests.
        args.output.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error("Output directory exists; choose a new directory")
    except Exception as exc:
        # Only explicitly safe configuration errors may be shown.
        parser.error(f"Cannot initialize classification ({type(exc).__name__}); check input JSON, category config, OPENAI_API_KEY and OPENAI_MODEL")
    result = classify_document(document, categories, classifier=client, model=model)
    result.source_extraction_file = str(args.input.resolve())
    report = build_classification_report(result)
    for name, data in [("classified_content.json", result), ("classification_report.json", report)]:
        with (args.output / name).open("x", encoding="utf-8") as stream:
            stream.write(data.model_dump_json(indent=2))
    print(report.model_dump_json(indent=2))
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
