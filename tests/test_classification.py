"""Offline classification contract tests. Mock labels are not accuracy evidence."""
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.classification.categories import load_categories
from src.classification.client import OpenAIClassifier, OpenAISettings
from src.classification.models import BatchDecisions, ClassifiedDocument, Decision
from src.classification.preparation import prepare_units
from src.classification.service import build_classification_report, classify_document
from src.extraction import extract_pdf
from src.extraction.audit import audit_inventory
from tests.test_extraction import make_pdf


@pytest.fixture
def categories():
    return load_categories(Path("config/categories.yaml"))


@pytest.fixture
def document(tmp_path):
    path = tmp_path / "source.pdf"
    make_pdf(path, table=True, pages=2)
    return extract_pdf(path)


class FakeClassifier:
    def __init__(self, transform=None):
        self.payloads = []
        self.transform = transform

    def classify(self, payload):
        data = json.loads(payload)
        self.payloads.append(data)
        response = {"decisions": [dict(
            unit_id=u["unit_id"], category_codes=["UNI-04", "UNI-05"],
            ambiguous=False, reason="Fixture decision only", evidence_ids=[u["unit_id"]],
        ) for u in data["targets"]]}
        return self.transform(response) if self.transform else BatchDecisions.model_validate(response)


def test_multiple_categories_preserve_all_source(document, categories):
    fake = FakeClassifier()
    result = classify_document(document, categories, classifier=fake, model="mock")
    assert result.status == "COMPLETE_UNVERIFIED"
    assert result.extracted_document == document
    assert any(r.category_codes == ["UNI-04", "UNI-05"] for r in result.records)
    assert all(r.status == "REVIEW_REQUIRED" for r in result.records if r.unit.kind == "table")
    assert ClassifiedDocument.model_validate_json(result.model_dump_json()) == result
    assert fake.payloads[0]["context"]
    report = build_classification_report(result)
    assert report.semantic_accuracy == "NOT_VERIFIED"
    assert report.category_counts["UNI-04"] == report.assigned_unit_count
    assert set(report.category_counts) == set(categories)


def test_dedup_line_inventory_and_source_attribution(document):
    units, aliases = prepare_units(document)
    assert aliases
    active_text = "\n".join(u.text for u in units if u.kind == "text" and u.disposition == "CLASSIFY")
    assert "Science" not in active_text
    assert "Department exception" in active_text
    all_ids = [unit.unit_id for unit in units]
    assert len(all_ids) == len(set(all_ids))
    for block in document.blocks:
        expected = set(range(len(block.lines)))
        tracked = [a.line_index for a in aliases if a.source_block_id == block.block_id]
        tracked += [i for u in units if block.block_id in u.source_block_ids for i in u.source_line_indices]
        assert set(tracked) == expected
        assert len(tracked) == len(set(tracked))
    for alias in aliases:
        table = next(t for t in document.tables if t.table_id == alias.table_id)
        assert table.source.page_number == alias.source.page_number
    assert prepare_units(document) == (units, aliases)


def test_uncertain_overlap_not_silently_dropped(document):
    # Simulate ambiguous extraction, not a valid new fact.
    document.tables[0].cells[0].text = "unmatched content"
    units, _ = prepare_units(document)
    uncertain = [u for u in units if "AMBIGUOUS_TABLE_OVERLAP" in u.review_reasons]
    assert uncertain
    assert all(u.disposition == "REVIEW_ONLY" for u in uncertain)
    assert any("Program" in u.text for u in uncertain)


def test_prepare_only_and_unclassified_report(document, categories):
    result = classify_document(document, categories)
    report = build_classification_report(result)
    assert result.status == "NOT_RUN"
    assert report.assigned_unit_count == 0
    assert len(report.unclassified_unit_ids) == report.unit_count
    assert result.extracted_document == document


@pytest.mark.parametrize("change", [
    lambda r: r["decisions"].pop(),
    lambda r: r["decisions"].append(r["decisions"][0]),
    lambda r: r["decisions"][0].update(unit_id="invented"),
    lambda r: r["decisions"][0].update(category_codes=["UNI-99"]),
    lambda r: r["decisions"][0].update(evidence_ids=["invented"]),
    lambda r: r["decisions"][0].update(evidence_ids=[]),
    lambda r: r["decisions"][0].update(text="AI rewrite"),
])
def test_invalid_model_output_is_rejected(document, categories, change):
    def transform(response):
        change(response)
        return response
    result = classify_document(document, categories, classifier=FakeClassifier(transform))
    assert result.errors
    assert not any(record.category_codes for record in result.records)
    assert result.status == "FAILED"


def test_api_failure_preserves_records_and_redacts_error(document, categories):
    class Broken:
        def classify(self, payload):
            raise RuntimeError("sensitive-secret must not be logged")
    result = classify_document(document, categories, classifier=Broken())
    assert result.status == "FAILED"
    assert result.extracted_document == document
    assert "sensitive-secret" not in result.model_dump_json()
    assert all(not r.category_codes for r in result.records)


def test_ambiguous_and_unclassified_decisions(document, categories):
    def transform(response):
        for d in response["decisions"]:
            d.update(category_codes=[], ambiguous=True, reason="Cannot establish scope")
        return response
    result = classify_document(document, categories, classifier=FakeClassifier(transform))
    report = build_classification_report(result)
    assert not result.errors
    assert report.assigned_unit_count == 0
    assert len(report.ambiguous_unit_ids) == report.unit_count
    assert all(r.status == "REVIEW_REQUIRED" for r in result.records)


def test_oversized_payload_is_not_truncated(document, categories):
    fake = FakeClassifier()
    result = classify_document(document, categories, classifier=fake, max_payload_characters=1)
    assert not fake.payloads
    assert result.errors
    assert all(e.code == "PAYLOAD_LIMIT_REVIEW_REQUIRED" for e in result.errors)


def test_category_changes_rejected(tmp_path, categories):
    path = tmp_path / "categories.yaml"
    path.write_text("categories: []")
    with pytest.raises(ValueError):
        load_categories(path)
    with pytest.raises(ValueError):
        classify_document(None, {"UNI-01": "Renamed"})


def test_settings_require_configuration_and_hide_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    with pytest.raises(ValueError):
        OpenAISettings.from_environment()
    monkeypatch.setenv("OPENAI_API_KEY", "private-fixture-key")
    monkeypatch.setenv("OPENAI_MODEL", "mock")
    assert "private-fixture-key" not in repr(OpenAISettings.from_environment())


def test_sdk_adapter_structured_response_and_refusal(monkeypatch):
    import src.classification.client as module
    captured = []
    message = SimpleNamespace(refusal=None, parsed=BatchDecisions(decisions=[]))
    def parse(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])
    client = SimpleNamespace(beta=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse))))
    monkeypatch.setattr(module, "OpenAI", lambda **kwargs: client)
    adapter = OpenAIClassifier(OpenAISettings(api_key="fixture", model="mock"))
    assert adapter.classify("{}") == BatchDecisions(decisions=[])
    assert captured[0]["response_format"] is BatchDecisions
    message.refusal = "Refused"
    with pytest.raises(ValueError):
        adapter.classify("{}")


def test_classification_cli_preparation_and_no_overwrite(tmp_path, document):
    source = tmp_path / "extracted.json"
    source.write_text(document.model_dump_json())
    output = tmp_path / "classified"
    cmd = [sys.executable, "-m", "src.classification", str(source), "--prepare-only", "--output", str(output)]
    first = subprocess.run(cmd, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    saved = {p.name: p.read_bytes() for p in output.iterdir()}
    assert set(saved) == {"classified_content.json", "classification_report.json"}
    ClassifiedDocument.model_validate_json(saved["classified_content.json"])
    second = subprocess.run(cmd, capture_output=True, text=True)
    assert second.returncode == 2
    assert saved == {p.name: p.read_bytes() for p in output.iterdir()}


def test_audit_rejects_broken_inventory(document, categories):
    assert not audit_inventory(document)["inventory_errors"]
    document.pages[0].block_ids = []
    assert audit_inventory(document)["inventory_errors"]
    with pytest.raises(ValueError):
        classify_document(document, categories)


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("RUN_LIVE_OPENAI") != "1", reason="Live API calls require explicit opt-in")
def test_optional_live_api(tmp_path, categories):
    if not os.environ.get("OPENAI_API_KEY") or not os.environ.get("OPENAI_MODEL"):
        pytest.skip("Live credentials/model not configured")
    path = tmp_path / "small.pdf"
    make_pdf(path)
    doc = extract_pdf(path)
    settings = OpenAISettings.from_environment()
    result = classify_document(doc, categories, classifier=OpenAIClassifier(settings), model=settings.model)
    assert not result.errors
    assert result.status == "COMPLETE_UNVERIFIED"
    assert any(r.category_codes for r in result.records)
    assert result.extracted_document == doc


def test_partial_api_failure_keeps_successful_assignments(document, categories):
    fake = FakeClassifier()
    class Intermittent:
        calls = 0
        def classify(self, payload):
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("private diagnostic")
            return fake.classify(payload)
    result = classify_document(document, categories, classifier=Intermittent(), batch_size=1)
    assert result.status == "PARTIAL"
    assert len(result.errors) == 1
    assert any(r.category_codes for r in result.records)
    assert any(r.reason == "CLASSIFICATION_FAILED_TimeoutError" for r in result.records)


def test_sample_mocked_end_to_end_if_available(categories):
    path = Path("output/sample_2027_spring_integrated_01/extracted_content.json")
    if not path.exists():
        pytest.skip("Local sample artifact unavailable")
    from src.extraction.models import ExtractedDocument
    document = ExtractedDocument.model_validate_json(path.read_text())
    fake = FakeClassifier()
    result = classify_document(document, categories, classifier=fake, model="mock-not-real-classification")
    assert not result.errors
    assert result.status == "COMPLETE_UNVERIFIED"
    assert result.extracted_document == document
    assert len(result.records) == 194
    assert len(result.table_text_aliases) == 548
    assert all(len(json.dumps(p, ensure_ascii=False, separators=(",", ":"))) <= 60000 for p in fake.payloads)
    units, aliases = prepare_units(document)
    for block in document.blocks:
        if block.kind != "text":
            continue
        mapped = [a.line_index for a in aliases if a.source_block_id == block.block_id]
        mapped += [i for u in units if block.block_id in u.source_block_ids for i in u.source_line_indices]
        assert sorted(mapped) == list(range(len(block.lines)))
    print(f"Mock sample requests: {len(fake.payloads)}; no semantic accuracy asserted")


def test_numeric_dedup_uses_complete_tokens():
    from src.classification.preparation import _contains_tokens, _tokens
    assert not _contains_tokens(_tokens("100"), _tokens("10000"))
    assert not _contains_tokens(_tokens("5.5"), _tokens("15.5"))
    assert _contains_tokens(_tokens("IELTS 5.5"), _tokens("IELTS\n5.5 or higher"))


def test_source_ids_and_coordinates_repeatable(tmp_path):
    path = tmp_path / "repeatable.pdf"
    make_pdf(path, table=True, pages=2)
    first, second = extract_pdf(path), extract_pdf(path)
    assert first.blocks == second.blocks
    assert first.tables == second.tables
    assert not audit_inventory(first)["inventory_errors"]
    first.blocks[0].source.bbox = (0, 0, 10000, 10000)
    assert audit_inventory(first)["inventory_errors"]
