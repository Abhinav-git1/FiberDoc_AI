"""Extract text, tables and page metadata from PDF / DOCX / XLSX.

PyMuPDF for PDF, python-docx for DOCX, openpyxl for XLSX.
Each ParsedChunk keeps its page (or sheet index) so findings can cite evidence.
"""
from dataclasses import dataclass
from pathlib import Path

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx"}
MAX_CHUNK_CHARS = 1500


@dataclass
class ParsedChunk:
    page: int
    text: str
    kind: str = "text"  # text | table


@dataclass
class ParsedDocument:
    chunks: list[ParsedChunk]
    page_count: int


def validate_upload(filename: str, size_bytes: int, max_mb: int) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    if size_bytes == 0:
        raise ValueError("File is empty")
    if size_bytes > max_mb * 1024 * 1024:
        raise ValueError(f"File exceeds {max_mb} MB limit")


def _split(text: str, page: int, kind: str = "text") -> list[ParsedChunk]:
    """Split on paragraph boundaries into chunks of at most MAX_CHUNK_CHARS."""
    out, buf = [], ""
    for para in (p.strip() for p in text.split("\n\n")):
        if not para:
            continue
        if buf and len(buf) + len(para) > MAX_CHUNK_CHARS:
            out.append(ParsedChunk(page, buf, kind))
            buf = ""
        buf = f"{buf}\n\n{para}".strip()
        while len(buf) > MAX_CHUNK_CHARS:
            out.append(ParsedChunk(page, buf[:MAX_CHUNK_CHARS], kind))
            buf = buf[MAX_CHUNK_CHARS:]
    if buf:
        out.append(ParsedChunk(page, buf, kind))
    return out


def parse_pdf(path: Path) -> ParsedDocument:
    import fitz  # PyMuPDF

    chunks: list[ParsedChunk] = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            chunks += _split(page.get_text("text"), i)
            for table in page.find_tables().tables:
                rows = [" | ".join(c or "" for c in row) for row in table.extract()]
                if rows:
                    chunks += _split("\n".join(rows), i, "table")
        return ParsedDocument(chunks, doc.page_count)


def parse_docx(path: Path) -> ParsedDocument:
    from docx import Document

    d = Document(str(path))
    # DOCX has no fixed pages; treat the whole body as page 1.
    chunks = _split("\n\n".join(p.text for p in d.paragraphs), 1)
    for t in d.tables:
        rows = [" | ".join(c.text.strip() for c in r.cells) for r in t.rows]
        chunks += _split("\n".join(rows), 1, "table")
    return ParsedDocument(chunks, 1)


def parse_xlsx(path: Path) -> ParsedDocument:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    chunks: list[ParsedChunk] = []
    for i, ws in enumerate(wb.worksheets, start=1):  # sheet index stands in for page
        rows = [" | ".join("" if v is None else str(v) for v in row) for row in ws.iter_rows(values_only=True)]
        text = "\n".join(r for r in rows if r.strip(" |"))
        if text:
            chunks += _split(f"[Sheet: {ws.title}]\n{text}", i, "table")
    return ParsedDocument(chunks, len(wb.worksheets))


def parse_document(path: Path) -> ParsedDocument:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return parse_pdf(path)
    if ext == ".docx":
        return parse_docx(path)
    if ext == ".xlsx":
        return parse_xlsx(path)
    raise ValueError(f"Unsupported file type '{ext}'")
