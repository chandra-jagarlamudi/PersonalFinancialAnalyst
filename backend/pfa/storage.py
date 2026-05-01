"""Content-addressed raw file storage for uploaded statements."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

UPLOAD_DIR_ENV = "UPLOAD_DIR"
_DEFAULT_UPLOAD_DIR = "/data/raw-statements"


def upload_dir() -> Path:
    return Path(os.environ.get(UPLOAD_DIR_ENV, _DEFAULT_UPLOAD_DIR))


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def store(sha256: str, data: bytes) -> Path:
    """Write bytes to content-addressed path; no-op if already present."""
    dest = upload_dir() / sha256[:2] / sha256
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return dest
    fd, tmp_path_str = tempfile.mkstemp(
        dir=dest.parent, prefix=".st-", suffix=".tmp"
    )
    tmp_path = Path(tmp_path_str)
    try:
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp_path, dest)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return dest


def delete_file(file_path: str) -> None:
    """Remove stored file; may raise OSError (permissions, I/O)."""
    p = Path(file_path)
    if p.exists():
        p.unlink()
