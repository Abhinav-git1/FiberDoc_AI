import pytest

from app.services.document_parser import parse_docx, parse_xlsx, validate_upload


def test_validate_upload_rejects_bad_type_empty_and_large():
    with pytest.raises(ValueError):
        validate_upload("x.exe", 10, 25)
    with pytest.raises(ValueError):
        validate_upload("x.pdf", 0, 25)
    with pytest.raises(ValueError):
        validate_upload("x.pdf", 26 * 1024 * 1024, 25)
    validate_upload("x.PDF", 10, 25)


def test_docx_roundtrip(tmp_path):
    from docx import Document

    d = Document()
    d.add_paragraph("Design summary: 144-count cable.")
    p = tmp_path / "a.docx"
    d.save(p)
    assert "144-count" in parse_docx(p).chunks[0].text


def test_xlsx_roundtrip(tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    wb.active.append(["Route", "Fibers"])
    wb.active.append(["A", 96])
    p = tmp_path / "a.xlsx"
    wb.save(p)
    out = parse_xlsx(p)
    assert out.page_count == 1 and "A | 96" in out.chunks[0].text
