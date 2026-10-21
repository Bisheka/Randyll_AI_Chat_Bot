import hashlib
from pathlib import Path

import fitz
import pytest
from pydantic import ValidationError

from src.extraction import ExtractionError, extract_pdf
from src.extraction.models import ExtractedDocument, SourceReference


def make_pdf(path, *, table=False, pages=1):
    with fitz.open() as doc:
        for number in range(pages):
            page = doc.new_page()
            page.insert_text((40, 40), f"Admission rules page {number+1}: IELTS 6.5; fee 10000; 2027-03-01.")
            page.insert_text((40, 65), "* Department exception: TOPIK level 4 required.")
            if table:
                for x in [40, 180, 320]:
                    page.draw_line((x, 100), (x, 180))
                for y in [100, 140, 180]:
                    page.draw_line((40, y), (320, y))
                for x, y, text in [(50, 120, "Program"), (190, 120, "Fee"), (50, 160, "Science"), (190, 160, "10000")]:
                    page.insert_text((x, y), text)
        doc.save(path)


def test_text_numbers_sources_and_json(tmp_path):
    path = tmp_path / "sample.pdf"
    make_pdf(path, pages=2)
    result = extract_pdf(path)
    assert result.document_id == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result.page_count == 2
    assert {b.source.page_number for b in result.blocks} == {1, 2}
    text = "\n".join(b.text for b in result.blocks)
    for value in ["6.5", "10000", "2027-03-01", "TOPIK level 4", "Department exception"]:
        assert value in text
    assert ExtractedDocument.model_validate_json(result.model_dump_json()) == result


def test_table_cells_and_multipage_candidates(tmp_path):
    path = tmp_path / "tables.pdf"
    make_pdf(path, table=True, pages=2)
    result = extract_pdf(path, review_directory=tmp_path / "regions")
    assert len(result.tables) == 2
    first, second = result.tables
    assert first.row_count == first.column_count == 2
    assert [(c.row_index,c.column_index,c.text) for c in first.cells] == [
        (0,0,"Program"),(0,1,"Fee"),(1,0,"Science"),(1,1,"10000")]
    assert all(c.source is not None for c in first.cells)
    assert second.table_id in first.continuation_candidate_ids
    assert first.status == "REVIEW_REQUIRED"
    assert (tmp_path / first.region_file).is_file()
    assert "Science" in "".join(b.text for b in result.blocks)


def test_sparse_image_and_unicode(tmp_path):
    path = tmp_path / "unicode.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 40), "한국어 입학 안내", fontname="korea")
        image = fitz.Pixmap(fitz.csRGB, fitz.IRect(0,0,20,20), False)
        image.clear_with(255)
        page.insert_image(fitz.Rect(100,100,200,200), pixmap=image)
        doc.new_page()
        doc.save(path)
    result = extract_pdf(path)
    assert "한국어" in "".join(b.text for b in result.blocks)
    assert any(b.kind == "image" for b in result.blocks)
    assert {f.code for f in result.findings} >= {"IMAGE_CONTENT", "INSUFFICIENT_TEXT"}
    assert result.pages[1].status == "REVIEW_REQUIRED"


@pytest.mark.parametrize("contents", [b"", b"not a PDF"])
def test_invalid_pdf(tmp_path, contents):
    path = tmp_path / "invalid.pdf"
    path.write_bytes(contents)
    with pytest.raises(ExtractionError):
        extract_pdf(path)


def test_missing_pdf(tmp_path):
    with pytest.raises(ExtractionError):
        extract_pdf(tmp_path / "missing.pdf")


def test_no_asset_overwrite(tmp_path):
    path = tmp_path / "source.pdf"
    make_pdf(path)
    directory = tmp_path / "existing"
    directory.mkdir()
    with pytest.raises(FileExistsError):
        extract_pdf(path, review_directory=directory)


def test_invalid_source_reference():
    with pytest.raises(ValidationError):
        SourceReference(page_number=0, bbox=(0,0,1,1))
    with pytest.raises(ValidationError):
        SourceReference(page_number=1, bbox=(5,0,1,1))


def test_table_failure_retains_native_text(tmp_path, monkeypatch):
    import pdfplumber
    path = tmp_path / "source.pdf"
    make_pdf(path)
    def fail(self):
        raise ValueError("Broken table extraction")
    monkeypatch.setattr(pdfplumber.page.Page, "find_tables", fail)
    result = extract_pdf(path)
    assert result.errors
    assert "IELTS 6.5" in "".join(b.text for b in result.blocks)
    assert any(f.code == "TABLE_EXTRACTION_FAILED" for f in result.findings)


def test_uploaded_sample_if_available():
    path = Path("input/2.ENG2027-SpringSemesterFreshmanTransferAdmissionGuideline.pdf")
    if not path.exists():
        pytest.skip("User sample is not distributed with the repository")
    result = extract_pdf(path)
    assert result.page_count == 18
    assert [p.page_number for p in result.pages] == list(range(1, 19))
    assert not result.errors
    assert len(result.tables) == 27
    with fitz.open(path) as source:
        for index, page in enumerate(source):
            expected = page.get_text("dict", flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)
            expected_lines = [
                "".join(s["text"] for s in line["spans"])
                for block in expected["blocks"] for line in block.get("lines", [])
            ]
            actual = [
                "".join(s["text"] for s in line["spans"])
                for block in result.blocks if block.source.page_number == index+1
                for line in block.lines
            ]
            assert actual == expected_lines


def test_coverage_includes_every_extracted_record(tmp_path):
    from src.extraction.reporting import CoverageReport, build_coverage_report
    path = tmp_path / "tables.pdf"
    make_pdf(path, table=True, pages=2)
    document = extract_pdf(path)
    coverage = build_coverage_report(document)
    assert coverage.classification_status == "NOT_RUN"
    assert coverage.covered_page_numbers == [1, 2]
    assert coverage.missing_page_numbers == []
    assert {item.content_id for item in coverage.unclassified_items} == (
        {block.block_id for block in document.blocks}
        | {table.table_id for table in document.tables}
    )
    assert CoverageReport.model_validate_json(coverage.model_dump_json()) == coverage


def test_cli_output_and_overwrite_protection(tmp_path):
    import json
    import subprocess
    import sys
    path = tmp_path / "sample.pdf"
    make_pdf(path)
    output = tmp_path / "new-output"
    command = [sys.executable, "-m", "src.extraction", str(path), "--output", str(output)]
    first = subprocess.run(command, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    saved = {p.name: p.read_bytes() for p in output.glob("*.json")}
    assert set(saved) == {"extracted_content.json", "extraction_report.json", "coverage_report.json"}
    coverage = json.loads(saved["coverage_report.json"])
    assert coverage["classification_status"] == "NOT_RUN"
    assert coverage["unclassified_items"]
    second = subprocess.run(command, capture_output=True, text=True)
    assert second.returncode == 2
    assert {p.name: p.read_bytes() for p in output.glob("*.json")} == saved


def test_committed_category_configuration():
    import yaml
    data = yaml.safe_load(Path("config/categories.yaml").read_text())
    categories = data["categories"]
    assert len(categories) == 12
    assert [category["code"] for category in categories] == [
        f"UNI-{number:02d}" for number in range(1, 13)
    ]
    assert all(category["name"] for category in categories)
