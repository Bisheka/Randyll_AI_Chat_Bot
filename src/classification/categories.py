"""Load and protect the approved category definitions."""
from pathlib import Path

import yaml

APPROVED_TITLES = (
    "University Information", "Programs & Departments", "Admission Types & Pathways",
    "Eligibility Requirements", "Language Requirements", "Application Schedule & Deadlines",
    "Required Documents & Authentication", "Tuition, Fees & Financial Requirements",
    "Scholarships & Financial Benefits", "Evaluation & Selection Process",
    "Application & Enrollment Process", "Admission Policies & Restrictions",
)


def load_categories(path: Path) -> dict[str, str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    expected = {f"UNI-{i:02d}": name for i, name in enumerate(APPROVED_TITLES, 1)}
    entries = data.get("categories") if isinstance(data, dict) else None
    if not isinstance(entries, list) or len(entries) != 12:
        raise ValueError("Exactly 12 approved category definitions are required")
    if any(not isinstance(row, dict) or set(row) != {"code", "name"} for row in entries):
        raise ValueError("Each category must have only code and name")
    actual = {row["code"]: row["name"] for row in entries}
    if actual != expected:
        raise ValueError("Category definitions differ from the 12 approved categories")
    return actual
