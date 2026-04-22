"""Tests for the shared read_lines_numbered utility."""

from __future__ import annotations

from pathlib import Path

import pytest

from ohmycode.core.file_utils import read_lines_numbered


def test_full_file(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"line1\nline2\nline3\n")
    text, truncated = read_lines_numbered(f)
    assert truncated is False
    assert "1\tline1" in text
    assert "2\tline2" in text
    assert "3\tline3" in text


def test_offset(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"line1\nline2\nline3\n")
    text, truncated = read_lines_numbered(f, offset=2)
    assert truncated is False
    assert "1\t" not in text
    assert "2\tline2" in text
    assert "3\tline3" in text


def test_limit(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"line1\nline2\nline3\n")
    text, truncated = read_lines_numbered(f, limit=2)
    assert truncated is False
    assert "1\tline1" in text
    assert "2\tline2" in text
    assert "3\t" not in text


def test_offset_and_limit(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"line1\nline2\nline3\nline4\n")
    text, truncated = read_lines_numbered(f, offset=2, limit=2)
    assert truncated is False
    assert "1\t" not in text
    assert "2\tline2" in text
    assert "3\tline3" in text
    assert "4\t" not in text


def test_max_lines_truncation(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"\n".join(f"line{i}".encode() for i in range(10)) + b"\n")
    text, truncated = read_lines_numbered(f, max_lines=5)
    assert truncated is True
    assert "5\tline4" in text
    assert "6\t" not in text


def test_max_bytes_truncation(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"A" * 200)
    text, truncated = read_lines_numbered(f, max_bytes=10)
    assert truncated is True
    assert len(text) < 200


def test_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_lines_numbered(tmp_path / "missing.txt")


def test_non_utf8_file(tmp_path):
    f = tmp_path / "b.bin"
    f.write_bytes(b"\xff\xfe" + b"hello")
    text, truncated = read_lines_numbered(f)
    assert truncated is False
    assert "1\t" in text


def test_empty_file(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("")
    text, truncated = read_lines_numbered(f)
    assert truncated is False
    assert text == ""
