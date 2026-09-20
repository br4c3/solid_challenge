from __future__ import annotations

import io
from dataclasses import asdict, dataclass
from typing import Iterable, List, Tuple

from pypdf import PdfReader

from .extractor import extract_labeled_specs


@dataclass(slots=True)
class ExtractedField:
    field: str
    value: float
    unit: str
    page: int
    evidence: str
    confidence: str = "REVIEW_REQUIRED"


def extract_fields_from_pages(pages: Iterable[str], category: str = "") -> List[ExtractedField]:
    output: List[ExtractedField] = []
    seen                         = set()
    for page_number, text in enumerate(pages, start=1):
        for item in extract_labeled_specs(text, category):
            if item.field in seen: continue
            output.append(ExtractedField(item.field, item.value, item.unit, page_number, item.evidence))
            seen.add(item.field)
    return output


def extract_pdf_pages(content: bytes, use_ocr: bool = True) -> Tuple[List[str], str]:
    reader = PdfReader(io.BytesIO(content))
    pages  = [page.extract_text() or "" for page in reader.pages]
    weak   = [index for index, text in enumerate(pages) if len("".join(text.split())) < 80]
    if not weak or not use_ocr: return pages, "PDF_TEXT"

    try:
        import fitz
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        if len(weak) == len(pages):
            raise RuntimeError("OCR dependencies are missing. Install backend/requirements.txt.") from exc
        return pages, "PDF_TEXT(OCR_UNAVAILABLE)"

    document = fitz.open(stream=content, filetype="pdf")
    try:
        for index in weak:
            pixmap       = document[index].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image        = Image.open(io.BytesIO(pixmap.tobytes("png")))
            pages[index] = pytesseract.image_to_string(image, lang="eng")
    except Exception as exc:
        if len(weak) == len(pages): raise RuntimeError(f"OCR failed: {exc}") from exc
        return pages, "PDF_TEXT(OCR_FAILED)"
    return pages, "OCR" if len(weak) == len(pages) else "PDF_TEXT+OCR"


def parse_datasheet_pdf(content: bytes, category: str = "", use_ocr: bool = True) -> List[dict]:
    pages, _ = extract_pdf_pages(content, use_ocr)
    return [asdict(field) for field in extract_fields_from_pages(pages, category)]
