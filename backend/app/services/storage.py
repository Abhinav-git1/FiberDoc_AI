"""Original-upload storage and checksums, so every finding can be traced to the exact file reviewed."""
import hashlib
from pathlib import Path


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def store_original(root: Path, project_id: str, document_id: str, filename: str, data: bytes) -> Path:
    """Write the upload to <root>/<project_id>/<document_id><ext>. The client filename is never used in the
    path (only its extension), so it cannot escape `root`."""
    dest_dir = root / project_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{document_id}{Path(filename).suffix.lower()}"
    dest.write_bytes(data)
    return dest
