from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import io
import re

import fitz  # PyMuPDF
import pytesseract
from PIL import Image, ImageFilter, ImageOps


# Helps on Windows if Tesseract is installed but not added to PATH.
WINDOWS_TESSERACT_EXE = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
if WINDOWS_TESSERACT_EXE.exists():
    pytesseract.pytesseract.tesseract_cmd = str(WINDOWS_TESSERACT_EXE)


CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
LATIN_RE = re.compile(r"[A-Za-z]")

BAD_MONGOLIAN_HINTS = [
    "cypr", "cypryyn", "xyyn", "xyynu", "xyp", "xypa", "6ono", "6aixa",
    "rexHonor", "rToon", "Ayp", "Ygup", "UlyT", "lllyT", "tlJY", "lllYT",
    "Moxron", "uJ", "uI", "gaap", "cap", "cyp", "yHA", "6af",
]


def normalize_block_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = text.replace("\r", "\n")
    # Join hyphenated line breaks: эрсдэ-\nлийг -> эрсдэлийг
    text = re.sub(r"-\n(?=\w)", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_text_to_blocks(text: str) -> List[str]:
    text = normalize_block_text(text)
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) >= 2:
        return paragraphs

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    blocks: List[str] = []
    buffer: List[str] = []
    length = 0

    for line in lines:
        buffer.append(line)
        length += len(line) + 1

        if length >= 650:
            blocks.append(" ".join(buffer).strip())
            buffer = []
            length = 0

    if buffer:
        blocks.append(" ".join(buffer).strip())

    return blocks


def text_stats(text: str) -> Dict[str, float]:
    sample = text[:5000]
    cyr = len(CYRILLIC_RE.findall(sample))
    lat = len(LATIN_RE.findall(sample))
    letters = cyr + lat

    return {
        "cyrillic": cyr,
        "latin": lat,
        "letters": letters,
        "cyr_ratio": cyr / max(letters, 1),
        "latin_ratio": lat / max(letters, 1),
        "bad_hits": sum(sample.count(h) for h in BAD_MONGOLIAN_HINTS),
    }


def looks_like_bad_mongolian_extraction(text: str) -> bool:
    """
    Detect PDFs where Mongolian visually displays correctly, but copy/extract text becomes
    latin-looking garbage such as: 'Qeeg 6onoecponuH ryxafi xyynt ...'.
    """
    cleaned = normalize_block_text(text)

    if len(cleaned) < 80:
        return True

    stats = text_stats(cleaned)

    if stats["cyr_ratio"] < 0.15 and stats["bad_hits"] >= 2:
        return True

    if stats["latin_ratio"] > 0.85 and stats["bad_hits"] >= 1 and len(cleaned) > 300:
        return True

    return False


def extract_text_blocks_normal(page: fitz.Page) -> List[str]:
    raw_blocks = page.get_text("blocks", sort=True)
    blocks: List[str] = []

    for block in raw_blocks:
        text = block[4] if len(block) > 4 else ""
        text = normalize_block_text(text)
        if text:
            blocks.append(text)

    return blocks


def render_page_to_image(page: fitz.Page, zoom: float = 4.0) -> Image.Image:
    """
    Render PDF page to a high-resolution image for OCR.
    zoom=4.0 is slower, but helps with small Mongolian Cyrillic text.
    """
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    return Image.open(io.BytesIO(pix.tobytes("png")))


def preprocess_for_ocr(image: Image.Image) -> Image.Image:
    """
    Light preprocessing for Tesseract. Avoid aggressive thresholding because it can
    damage Mongolian Cyrillic strokes.
    """
    image = image.convert("L")
    image = ImageOps.autocontrast(image)
    image = image.filter(ImageFilter.SHARPEN)
    return image


def ocr_page_tesseract(page: fitz.Page, zoom: float = 4.0) -> str:
    image = render_page_to_image(page, zoom=zoom)
    image = preprocess_for_ocr(image)

    config = "--oem 1 --psm 6 -c preserve_interword_spaces=1"

    text = pytesseract.image_to_string(
        image,
        lang="mon+eng",
        config=config,
    )

    return normalize_block_text(text)


def extract_pdf_pages(pdf_path: str | Path, force_ocr: bool = False) -> List[Dict[str, Any]]:
    """
    Extract PDF pages.

    - Normal digital PDFs: use embedded text.
    - Broken Mongolian-font PDFs or scanned PDFs: use Tesseract OCR.
    - Use force_ocr=True for PDFs where copy-paste text is garbage.
    """
    pdf_path = Path(pdf_path)
    doc = fitz.open(pdf_path)
    pages: List[Dict[str, Any]] = []

    for i, page in enumerate(doc):
        page_no = i + 1

        normal_blocks = extract_text_blocks_normal(page)
        normal_text = "\n\n".join(normal_blocks)

        use_ocr = force_ocr or looks_like_bad_mongolian_extraction(normal_text)

        if use_ocr:
            ocr_text = ocr_page_tesseract(page, zoom=4.0)
            blocks = split_text_to_blocks(ocr_text)
            method = "tesseract"
        else:
            blocks = normal_blocks
            method = "text"

        if blocks:
            pages.append(
                {
                    "page": page_no,
                    "blocks": blocks,
                    "extraction_method": method,
                }
            )

    doc.close()
    return pages
