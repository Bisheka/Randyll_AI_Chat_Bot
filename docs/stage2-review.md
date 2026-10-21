# Stage 2 sample review

Source: `2.ENG2027-SpringSemesterFreshmanTransferAdmissionGuideline.pdf`
SHA-256: `0ba01748960ddac1dc249d19f66cbc7e56396ef912c29f8cb9d1f140dd5afad0`

## Findings

All 46 findings were triaged using the extracted records and rendered page
layout overview. This is risk triage, not a line-by-line human certification of
all table relationships or numerical conditions.

| Severity | Count | Reason |
| --- | ---: | --- |
| High | 26 | Unverified admission-related table structure on pages 3–14 |
| Medium | 2 | Contact table on page 17 and graphical dormitory process on page 18 |
| Low | 18 | Three logo/location images and 15 layout/vector findings |

No critical extraction failure or native-text loss was confirmed. High severity
means a relationship could alter an admission answer; it does not mean its value
has been proven wrong. All high-risk tables remain `REVIEW_REQUIRED`.

## Admission-sensitive issues

- Page 8: keep the three intake columns separate, including document deadlines,
  payment periods and Korean Standard Time footnotes. Do not infer unstated years.
- Pages 3–7 and 9: retain department-specific language requirements, freshman/
  transfer and track distinctions, and transfer-credit footnote exceptions.
- Page 10: preserve the bank-balance value with issuance, validity and residency
  conditions. Matching a number does not establish its relationship is correct.
- Page 12: the source explicitly labels tuition figures as a **2026 Fall baseline
  subject to increase**. Do not relabel them as confirmed 2027 fees.
- Pages 13–14: merged TOPIK/GPA scholarship matrices and first/subsequent-semester
  conditions require manual verification. Do not flatten merged cells by guessing.

## Coverage, duplication and provenance

The original inventory has 407 text/image blocks and 27 supplementary tables,
with no duplicate native records or missing page references. The original text
and tables deliberately overlap. This snapshot is evidence, not a flat rendering
list. Classification preparation creates 194 canonical units and 548 source-line
to-table aliases. Fourteen uncertain text-overlap units, three images and six
overlapping table candidates are withheld from API classification for review.
Every native text line maps exactly once to a residual unit or table alias;
original source blocks and cells remain unchanged in the output snapshot.

The numeric-token comparison found no native numbers missing from the matching
candidate table regions. This check does not validate header/row relationships,
detect a mistaken value in the original guideline, or prove semantic completeness.

Block/table IDs and content matched the earlier extraction of the same source.
Use `(document SHA-256, local block/unit ID)` as a storage key. Local IDs alone are
not globally unique and are not guaranteed stable across document edits or
extraction-library versions. One-based source pages and source coordinates are
checked against the page inventory. All 46 source review images exist.

Generated detailed reports and PDFs are ignored by Git. The per-finding severity
inventory is in the local `output/stage2_review_02/stage2_review.json` artifact.
