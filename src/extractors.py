"""Universal document extraction for the RLCD-calibrated routing system.

Step 1 turns arbitrary study material into one uniform record so that every
downstream component (taxonomy, calibrator, ...) only ever sees a single
shape: :class:`ExtractedDoc`.

Supported formats
-----------------
* ``.pdf``  -- PyMuPDF (``fitz``): metadata title, table of contents, layout
  based headings and the full page text.
* ``.docx`` -- python-docx: core-property title, heading paragraphs and body
  paragraphs.
* ``.pptx`` -- python-pptx: core-property / slide titles and every text frame.

Any unreadable or unsupported file raises :class:`DocumentExtractionError`
with a clear, actionable message instead of leaking a third-party traceback.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from statistics import median

import pymupdf as fitz  # PyMuPDF
import docx  # python-docx
from pptx import Presentation

__all__ = [
    "DocumentExtractionError",
    "ExtractedDoc",
    "extract_document",
]

# A span is treated as a heading when its font is at least this many points
# larger than, or this ratio above, the median body font size.
_HEADING_ABS_DELTA = 0.75
_HEADING_SIZE_RATIO = 1.15
_BOLD_FLAG = 1 << 4  # PyMuPDF span flag bit 4 == bold


class DocumentExtractionError(Exception):
    """Raised when a document cannot be read or parsed.

    The message is always prefixed with the offending path so callers can
    route or log the failure without extra bookkeeping.
    """

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Could not extract '{path}': {reason}")


@dataclass
class ExtractedDoc:
    """Format-independent representation of a study document."""

    path: str
    file_type: str
    title: str
    clean_text: str
    headings: list[str]
    word_count: int


# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #
def _clean_text(raw: str) -> str:
    """Collapse noisy whitespace while preserving paragraph breaks."""
    if not raw:
        return ""

    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u200b", "").replace("\t", " ")

    cleaned_lines: list[str] = []
    previous_blank = False
    for line in text.split("\n"):
        line = re.sub(r"[ ]{2,}", " ", line).strip()
        if line:
            cleaned_lines.append(line)
            previous_blank = False
        elif not previous_blank:
            cleaned_lines.append("")
            previous_blank = True

    return "\n".join(cleaned_lines).strip()


def _count_words(text: str) -> int:
    return len(text.split())


def _fallback_title(path: str) -> str:
    stem = os.path.splitext(os.path.basename(path))[0]
    return stem.replace("_", " ").replace("-", " ").strip() or os.path.basename(path)


def _dedupe_preserving_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.casefold()
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def _pdf_layout_headings(doc: "fitz.Document") -> list[str]:
    """Infer headings from font size / boldness across the whole document."""
    gathered: list[tuple[float, int, str]] = []  # (size, bold, text)
    sizes: list[float] = []

    for page in doc:
        try:
            page_dict = page.get_text("dict")
        except Exception:  # pragma: no cover - defensive
            continue
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:  # 0 == text block
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = (span.get("text") or "").strip()
                    if not text:
                        continue
                    size = float(span.get("size", 0.0) or 0.0)
                    bold = 1 if int(span.get("flags", 0)) & _BOLD_FLAG else 0
                    gathered.append((size, bold, text))
                    sizes.append(size)

    if not sizes:
        return []

    body_size = median(sizes)
    threshold = max(body_size + _HEADING_ABS_DELTA, body_size * _HEADING_SIZE_RATIO)

    headings: list[str] = []
    for size, bold, text in gathered:
        if len(text) > 120:
            continue
        if size >= threshold or (bold and size >= body_size - 0.01 and len(text) <= 80):
            headings.append(text)

    return _dedupe_preserving_order(headings)


def _extract_pdf(path: str) -> tuple[str, list[str], str]:
    with fitz.open(path) as doc:
        if doc.is_encrypted and not doc.authenticate(""):
            raise DocumentExtractionError(path, "PDF is encrypted and needs a password")

        metadata_title = ((doc.metadata or {}).get("title") or "").strip()

        headings: list[str] = []
        try:
            for _level, entry, _page in doc.get_toc(simple=True) or []:
                entry = (entry or "").strip()
                if entry:
                    headings.append(entry)
        except Exception:
            pass
        headings.extend(_pdf_layout_headings(doc))

        pages: list[str] = []
        for page in doc:
            try:
                pages.append(page.get_text("text"))
            except Exception:  # pragma: no cover - defensive
                continue

    return metadata_title, _dedupe_preserving_order(headings), "\n\n".join(pages)


# --------------------------------------------------------------------------- #
# DOCX
# --------------------------------------------------------------------------- #
def _docx_heading_style(paragraph: "docx.text.paragraph.Paragraph") -> bool:
    style = getattr(paragraph, "style", None)
    name = (getattr(style, "name", "") or "").strip().casefold()
    return name == "title" or name.startswith("heading") or name.startswith("subtitle")


def _extract_docx(path: str) -> tuple[str, list[str], str]:
    document = docx.Document(path)

    try:
        metadata_title = (document.core_properties.title or "").strip()
    except Exception:
        metadata_title = ""

    headings: list[str] = []
    body: list[str] = []

    for paragraph in document.paragraphs:
        text = (paragraph.text or "").strip()
        if not text:
            continue
        if _docx_heading_style(paragraph):
            headings.append(text)
        body.append(text)

    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                text = (cell.text or "").strip()
                if text:
                    body.append(text)

    if not headings:
        # No explicit heading styles: fall back to the very first paragraph.
        headings = body[:1]

    return metadata_title, _dedupe_preserving_order(headings), "\n".join(body)


# --------------------------------------------------------------------------- #
# PPTX
# --------------------------------------------------------------------------- #
def _extract_pptx(path: str) -> tuple[str, list[str], str]:
    presentation = Presentation(path)

    try:
        metadata_title = (presentation.core_properties.title or "").strip()
    except Exception:
        metadata_title = ""

    headings: list[str] = []
    body: list[str] = []

    for slide in presentation.slides:
        slide_title = ""
        title_shape = None
        try:
            title_shape = slide.shapes.title
        except Exception:
            title_shape = None

        if title_shape is not None and title_shape.has_text_frame:
            slide_title = (title_shape.text_frame.text or "").strip()
            if slide_title:
                headings.append(slide_title)

        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            text = (shape.text_frame.text or "").strip()
            if text:
                body.append(text)

    return metadata_title, _dedupe_preserving_order(headings), "\n".join(body)


def _extract_plain_text(file_path: str) -> tuple[str, list[str], str]:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    title = lines[0] if lines else os.path.splitext(os.path.basename(file_path))[0]
    headings = [line.lstrip("#").strip() for line in lines if line.startswith("#") and len(line) > 1]
    return title, headings, text


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
_EXTRACTORS = {
    "pdf": _extract_pdf,
    "docx": _extract_docx,
    "pptx": _extract_pptx,
}


def extract_document(file_path: str) -> ExtractedDoc:
    """Extract a PDF/DOCX/PPTX file into a uniform :class:`ExtractedDoc`.

    Raises
    ------
    DocumentExtractionError
        If the path is missing, the extension is unsupported, or parsing the
        file fails for any reason.
    """
    if not isinstance(file_path, str) or not file_path:
        raise DocumentExtractionError(str(file_path), "file path is empty")

    if not os.path.exists(file_path):
        raise DocumentExtractionError(file_path, "file does not exist")
    if not os.path.isfile(file_path):
        raise DocumentExtractionError(file_path, "path is not a regular file")

    file_type = os.path.splitext(file_path)[1].lstrip(".").casefold()
    extractor = _EXTRACTORS.get(file_type)
    if extractor is None:
        supported = ", ".join(sorted(_EXTRACTORS))
        raise DocumentExtractionError(
            file_path, f"unsupported file type '.{file_type}' (supported: {supported})"
        )

    try:
        metadata_title, headings, raw_text = extractor(file_path)
    except DocumentExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001 - deliberately normalised
        raise DocumentExtractionError(file_path, f"{type(exc).__name__}: {exc}") from exc

    clean_text = _clean_text(raw_text)
    headings = [h for h in (_clean_text(h) for h in headings) if h]

    if not clean_text:
        raise DocumentExtractionError(file_path, "no extractable text found")

    title = _clean_text(metadata_title) or (headings[0] if headings else "")
    if not title:
        title = _fallback_title(file_path)

    return ExtractedDoc(
        path=file_path,
        file_type=file_type,
        title=title,
        clean_text=clean_text,
        headings=headings,
        word_count=_count_words(clean_text),
    )
