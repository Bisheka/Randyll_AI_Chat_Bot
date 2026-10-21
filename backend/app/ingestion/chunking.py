"""Semantic chunking: split on numbered section headings, keep each heading with
its body / table rows / footnotes. Small fragments merge into the previous chunk."""
import re

HEADING = re.compile(r"^\s*(\d{1,2})\.\s+(\S.{2,120})$")
MAX_CHARS, MIN_CHARS = 1400, 120

def chunk_page(text: str) -> list[tuple[str | None, str]]:
    lines = [l.rstrip() for l in (text or "").splitlines()]
    sections, head, buf = [], None, []
    def flush():
        if buf and "".join(buf).strip():
            sections.append((head, "\n".join(buf).strip()))
    for l in lines:
        m = HEADING.match(l)
        if m and not re.search(r"\d{4}[./]", l):  # not a date
            flush(); head, buf = l.strip(), []
        else:
            buf.append(l)
    flush()
    out: list[tuple[str | None, str]] = []
    for h, body in sections:
        full = body if (h and body.startswith(h)) else (f"{h}\n{body}" if h else body)
        if out and len(full) < MIN_CHARS and len(out[-1][1]) + len(full) < MAX_CHARS:
            ph, pb = out[-1]; out[-1] = (ph, pb + "\n" + full)
        elif len(full) > MAX_CHARS:  # hard-split only very long sections, on line bounds
            cur = ""
            for line in full.splitlines():
                if len(cur) + len(line) > MAX_CHARS and cur:
                    out.append((h, cur.strip())); cur = ""
                cur += line + "\n"
            if cur.strip(): out.append((h, cur.strip()))
        else:
            out.append((h, full))
    return [(h, b) for h, b in out if len(b) >= 40]
