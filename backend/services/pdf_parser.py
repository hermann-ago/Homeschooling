"""
PDF text extraction service using pdfplumber.
"""
import io
import pdfplumber


def extract_text_from_pdf(file_bytes: bytes) -> tuple[str, int]:
    """
    Extract text and page count from a PDF file.

    Args:
        file_bytes: Raw PDF file bytes.

    Returns:
        Tuple of (extracted_text, page_count).
    """
    text_parts = []
    page_count = 0

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        page_count = len(pdf.pages)
        # Extract text only from the first 15 pages (usually contains Table of Contents)
        for page in pdf.pages[:15]:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

    full_text = "\n\n".join(text_parts)
    return full_text, page_count
