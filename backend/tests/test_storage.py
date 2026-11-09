import hashlib

from app.services.storage import sha256_hex, store_original


def test_sha256_matches_hashlib_and_is_stable():
    assert sha256_hex(b"abc") == hashlib.sha256(b"abc").hexdigest()
    assert sha256_hex(b"abc") != sha256_hex(b"abd")


def test_store_original_writes_bytes_under_project(tmp_path):
    p = store_original(tmp_path, "proj1", "doc1", "Plan.PDF", b"%PDF-data")
    assert p == tmp_path / "proj1" / "doc1.pdf" and p.read_bytes() == b"%PDF-data"


def test_store_original_ignores_hostile_filename(tmp_path):
    p = store_original(tmp_path, "proj1", "doc1", "../../evil.pdf", b"x")
    assert p.resolve().is_relative_to(tmp_path.resolve())
