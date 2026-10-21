# Randyll_AI_Chat_Bot

## Set up on Windows

Install dependencies in a project virtual environment so they do not conflict
with packages used by other Python projects:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

Using the virtual-environment Python directly avoids needing to activate it in
PowerShell. Do not install this project's requirements into the global Python
environment.


## Extraction implementation

Python 3.12+. Extraction and Stage 3 classification are implemented.
Semantic certification and the final 12 category PDFs remain future stages.
No API key is needed for extraction.

## Install and run

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m src.extraction input/guideline.pdf --output output/new_run
```

Use an output directory that does not exist. Input documents, generated
outputs, local environments, and `.env` are ignored by Git. The original PDF
is opened read-only. Existing outputs are never overwritten by the CLI.
A failed run may leave a partial directory for diagnosis; use a new directory
for a retry. Runs containing extraction errors return a nonzero exit code.
Review warnings alone do not imply extraction failure or verified correctness.

Outputs:
- `extracted_content.json`: Pydantic-validated original text spans, font details,
  ordered blocks, pages, table cells, one-based source pages and bounding boxes.
- `extraction_report.json`: counts, extraction errors and review status.
- `coverage_report.json`: every unclassified text/image/table record and its source;
  classification is explicitly `NOT_RUN`, with source-page coverage listed.
- `review_regions/`: rendered source regions for table/image/other review findings.

Coordinates are unrotated top-left PDF points. Native text and supplementary
tables intentionally overlap; downstream stages must not render both blindly.
Unknown university/year/intake metadata remains null rather than being inferred
from filenames. The SHA-256 document ID links the extraction to exact input bytes.

## Limits and review

No OCR or semantic rewriting is performed. Headings, paragraphs, lists and
footnotes are retained as raw text spans; their semantic roles and links are not
yet inferred. Reading order follows the PDF's native block order and can require
review on multi-column layouts. Images and vector graphics are flagged.
Borderless tables may not be detected: the original text remains available,
but correct row/column reconstruction is not guaranteed. All detected tables
require manual review, including headers and merged cells. Matching column
counts on adjacent pages produce broad continuation candidates, never merges.
Supplementary tables on rotated pages are flagged and skipped to avoid mixing
coordinate systems. No extraction result establishes semantic completeness.

Tests use generated PDFs for text/numeric preservation, Korean Unicode,
source coordinates, image/sparse pages, tables and continuation candidates,
JSON round trips, invalid inputs, extraction failures, and overwrite protection.
A local sample test also runs when the uploaded guideline is present in `input/`.
The sample itself is not committed. Default tests use no live API calls.


## Stage 3: classification

Configure `OPENAI_API_KEY` and `OPENAI_MODEL` in the server environment, or in a
local ignored `.env` file (see `.env.example`). Select a model supporting OpenAI
structured outputs. No default model is guessed. Never put credentials in source,
commands committed to Git, generated artifacts, or logs. The adapter uses the
OpenAI SDK with a 60-second request timeout and at most two SDK retries for
transient failures. A custom `OPENAI_BASE_URL` is optional for a trusted endpoint.
Classification transmits source text, table data and nearby context to that API.

```bash
# Offline preparation: no model calls or category assignments.
.venv/bin/python -m src.classification output/new_run/extracted_content.json \
  --prepare-only --output output/classification_prepared

# Live classification: requires configured credentials/model and API access.
.venv/bin/python -m src.classification output/new_run/extracted_content.json \
  --output output/classification_live

# Optional live smoke test; enable explicitly with credentials exported.
RUN_LIVE_OPENAI=1 .venv/bin/python -m pytest -q -m live
```

Always choose a new output directory. The CLI refuses existing directories before
making API requests. `config/categories.yaml` must contain exactly the approved
12 code/title pairs; renames and duplicate/missing definitions are rejected.

Outputs are `classified_content.json` and `classification_report.json`.
The classified document embeds the unchanged extracted source snapshot and lists
canonical classification units, source pages/coordinates, full table cells,
source-line aliases, original metadata, review reasons and category decisions.
`source_extraction_file` locates the input artifact; source-region paths in its
snapshot remain relative to that extraction file's parent, not the classification
output folder. Preserve that extraction folder when moving artifacts.

Only category IDs, evidence references, ambiguity and explanations come from the
model. Original content is never accepted from an AI response. Headings, footnotes,
nearby pages and preceding heading candidates are supplied as unmodified context.
All source IDs must match the validated source inventory. Table continuation links
remain candidates; category assignment never merges rows or asserts their scope.

Preparation removes a source line from active text targets only when its region
is inside one table and its whole token sequence is also present in the table.
The line is retained as a source-to-table alias. Partial/ambiguous overlaps,
overlapping table candidates and untranscribed images remain unclassified for
manual review. Token boundaries prevent values such as `100` matching `10000`.
Original text/table overlap remains in the embedded evidence snapshot, which must
not be blindly concatenated for retrieval or presentation. Render/index canonical
records and use aliases for provenance; source snapshots are not extra content.

Reports count canonical units, not raw source blocks. Multi-category counts can
exceed the assigned-unit count. Every unit with no assignment appears in
`unclassified_unit_ids`; ambiguity, review and not-run lists are separate. Source review reasons remain
visible even before API classification. All 12 categories
are reported even with zero coverage. Batch errors preserve every affected unit as
unclassified. Oversized payloads split by unit without truncating source/context;
a single oversized unit remains review-required. The payload limit is a character
budget, not an exact model-token estimate; model context-limit failures are
reported rather than silently dropping data.

Statuses are `NOT_RUN`, `COMPLETE_UNVERIFIED`, `PARTIAL`, or `FAILED`.
`COMPLETE_UNVERIFIED` means requests completed, not that labels are correct or all
units were assigned. Individual records remain `AI_ASSIGNED_UNVERIFIED` or
`REVIEW_REQUIRED`. Preparation-only artifacts are explicitly `NOT_RUN`. All
semantic accuracy remains `NOT_VERIFIED`; no second AI is used as verification.

The sample's Stage 2 risks are documented in [docs/stage2-review.md](docs/stage2-review.md).
No PDF generation or database integration is implemented. For future SQL Server/
Qdrant storage, use document SHA-256 plus local unit ID, retain category arrays and
original table structure, and keep metadata/scope unknown when unsupported.
