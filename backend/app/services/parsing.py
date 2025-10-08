import io
from typing import List, Tuple
import fitz  # PyMuPDF
import pdfplumber
import pytesseract
from PIL import Image
from docx import Document as DocxDocument

SUPPORTED = {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/plain"}


def parse_pdf(data: bytes) -> List[Tuple[int, str]]:
    results: List[Tuple[int, str]] = []
    # Try text extraction first
    doc = fitz.open(stream=data, filetype="pdf")
    for page_index, page in enumerate(doc):
        text = page.get_text().strip()
        if not text:
            # fallback to OCR for that page
            pix = page.get_pixmap()
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            ocr_text = pytesseract.image_to_string(img)
            results.append((page_index + 1, ocr_text))
        else:
            results.append((page_index + 1, text))
    return results


def parse_docx(data: bytes) -> List[Tuple[int, str]]:
    f = io.BytesIO(data)
    doc = DocxDocument(f)
    paragraphs = []
    for p in doc.paragraphs:
        t = p.text.strip()
        if t:
            paragraphs.append(t)
    joined = "\n".join(paragraphs)
    return [(1, joined)]


def parse_txt(data: bytes) -> List[Tuple[int, str]]:
    return [(1, data.decode(errors="ignore"))]


def parse_file(content_type: str, data: bytes) -> List[Tuple[int, str]]:
    if content_type == "application/pdf":
        return parse_pdf(data)
    if content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return parse_docx(data)
    return parse_txt(data)
