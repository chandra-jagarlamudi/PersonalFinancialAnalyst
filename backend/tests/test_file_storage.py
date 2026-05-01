"""Unit tests for content-addressed file storage (no DB required)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pfa.storage import delete_file, sha256_hex, store


@pytest.fixture(autouse=True)
def _set_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))


def test_sha256_hex_matches_hashlib():
    data = b"hello world"
    assert sha256_hex(data) == hashlib.sha256(data).hexdigest()


def test_store_writes_to_content_addressed_path(tmp_path):
    data = b"statement bytes"
    h = sha256_hex(data)
    path = store(h, data)
    assert path == tmp_path / h[:2] / h
    assert path.read_bytes() == data


def test_store_is_idempotent(tmp_path):
    data = b"idempotent"
    h = sha256_hex(data)
    p1 = store(h, data)
    # Overwrite with different bytes to prove second store is a no-op.
    p1.write_bytes(b"tampered")
    store(h, data)
    assert p1.read_bytes() == b"tampered"


def test_delete_file_removes_existing_file(tmp_path):
    f = tmp_path / "test.csv"
    f.write_bytes(b"x")
    delete_file(str(f))
    assert not f.exists()


def test_delete_file_noop_when_missing(tmp_path):
    delete_file(str(tmp_path / "nonexistent.csv"))  # must not raise
