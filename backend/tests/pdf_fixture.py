"""Tiny text-only PDF writer for tests (no third-party dependency)."""


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[list[str]]) -> bytes:
    objects = []
    kids = []
    font_number = 3
    for index, lines in enumerate(pages):
        page_number = 4 + index * 2
        content_number = page_number + 1
        kids.append(page_number)
        stream = "BT /F1 12 Tf 72 740 Td " + " ".join(f"({_escape(line)}) Tj 0 -16 Td" for line in lines) + " ET"
        objects.append((page_number, f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                                     f"/Resources << /Font << /F1 {font_number} 0 R >> >> /Contents {content_number} 0 R >>"))
        objects.append((content_number, f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"))
    objects = [(1, "<< /Type /Catalog /Pages 2 0 R >>"),
               (2, f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>"),
               (3, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")] + objects
    output = b"%PDF-1.4\n"
    offsets = {}
    for number, body in sorted(objects):
        offsets[number] = len(output)
        output += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(output)
    count = max(offsets) + 1
    output += f"xref\n0 {count}\n0000000000 65535 f \n".encode()
    for number in range(1, count):
        output += f"{offsets[number]:010d} 00000 n \n".encode()
    output += f"trailer\n<< /Size {count} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return output
