"""Metadata is read from the categorized PDF's own header (never guessed).
Anything unparseable is flagged needs_review instead of being invented."""
import re, hashlib
from pathlib import Path

HEADER = re.compile(
    r"University\s*\n(.+?)\s*\nGuideline\s*\n(.+?)\s*\nAcademic year / semester\s*\n(.+?)\s*\n"
    r"Category\s*\n(UNI-\d{2})\s*-\s*(.+?)\s*\nSource pages \(original PDF\)\s*\n(.+?)\s*\n"
    r"Source file\s*\n(.+?)\s*\nStatus\s*\n(\S+)", re.S)
CAT_FILE = re.compile(r"(UNI-\d{2})", re.I)  # anywhere: KNU_2027S_Grad_UNI-01_... is valid

def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

def parse(text: str, path: Path) -> dict:
    reasons, m = [], HEADER.search(text or "")
    d = {"university_name": None, "guideline": None, "academic_year": None, "semester": None,
         "category_code": None, "category_name": None, "original_source_pages": None,
         "original_source_file": None, "pdf_status": None}
    if m:
        uni, guide, yearsem, cat, catname, pages, srcfile, status = [g.strip() for g in m.groups()]
        d.update(university_name=uni, guideline=guide, category_code=cat.upper(),
                 category_name=catname, original_source_pages=pages,
                 original_source_file=srcfile, pdf_status=status)
        ym = re.search(r"(20\d{2})", yearsem)
        d["academic_year"] = int(ym.group(1)) if ym else None
        d["semester"] = "SPRING" if re.search(r"spring|1st|1학기", yearsem, re.I) else \
                        "FALL" if re.search(r"fall|2nd|2학기", yearsem, re.I) else None
    fm = CAT_FILE.search(path.name)
    if fm:
        if d["category_code"] and d["category_code"] != fm.group(1).upper():
            reasons.append(f"filename category {fm.group(1)} != header {d['category_code']}")
        d["category_code"] = d["category_code"] or fm.group(1).upper()
    if not d["university_name"] or not d["category_code"] or not d["academic_year"]:
        # Alternate header layout (e.g. Kongju/KNU): loose labelled lines.
        t = text or ""
        if not d["university_name"]:
            u = re.search(r"^University\s*\n(.+)", t, re.M)
            if u: d["university_name"] = u.group(1).strip()
        if not d["category_code"]:
            c = re.search(r"Category\s*\n(UNI-\d{2})\s*-\s*([^\n]+)", t)
            if c: d.update(category_code=c.group(1).upper(), category_name=c.group(2).strip())
        intake = re.search(r"Intake\s*\n([^\n]+)", t)
        scope = intake.group(1) if intake else t[:1200]
        if not d["academic_year"]:
            y = re.search(r"(20\d{2})", scope)
            d["academic_year"] = int(y.group(1)) if y else None
        if not d["semester"]:
            d["semester"] = "SPRING" if re.search(r"spring", scope, re.I) else \
                            "FALL" if re.search(r"fall", scope, re.I) else None
        if not d.get("guideline"):
            sg = re.search(r"Source guide\s*\n([^\n]+)", t)
            if sg: d["guideline"] = sg.group(1).strip()
    g = (d.get("guideline") or path.parent.name)
    # "undergraduate" contains "graduate" — check it first / use word boundaries
    d["degree_level"] = "undergraduate" if re.search(r"undergraduate|freshman|transfer|bachelor", g, re.I) else \
                        "graduate" if re.search(r"\bgraduate\b|master|doctoral|ph\.?d", g, re.I) else None
    types = [t for t, p in (("freshman", r"freshman"), ("transfer", r"transfer")) if re.search(p, g, re.I)]
    d["admission_type"] = "+".join(types) if types else \
        ("graduate" if d["degree_level"] == "graduate" else "international_special" if re.search(r"special|외국인", g) else None)
    for k in ("university_name", "category_code", "academic_year", "semester", "degree_level"):
        if not d.get(k):
            reasons.append(f"missing {k}")
    d["university_id"] = slug(d["university_name"]) if d["university_name"] else slug(path.parent.name)
    d["needs_review"] = bool(reasons)
    d["review_reasons"] = reasons
    return d

def doc_id(path: Path, sha: str) -> str:
    return f"{slug(path.parent.name)}__{slug(path.stem)}"

def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()
