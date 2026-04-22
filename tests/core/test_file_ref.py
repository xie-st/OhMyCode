"""Tests for @ file reference expansion and path completion."""

from __future__ import annotations

from pathlib import Path

import pytest

from ohmycode.core.file_ref import (
    MAX_FILE_BYTES,
    MAX_FILE_LINES,
    expand_file_refs,
    get_at_completions,
)


# ── expand_file_refs ──────────────────────────────────────────────────────────


def test_expand_single_ref(tmp_path):
    (tmp_path / "hello.py").write_text("print('hello')\n")
    expanded, _, warnings = expand_file_refs("look at @hello.py please", str(tmp_path))
    assert warnings == []
    assert '<file path="hello.py">' in expanded
    assert "1\tprint('hello')" in expanded
    assert "</file>" in expanded
    assert "@hello.py" not in expanded


def test_expand_multiple_refs(tmp_path):
    (tmp_path / "a.py").write_text("a = 1\n")
    (tmp_path / "b.py").write_text("b = 2\n")
    expanded, _, warnings = expand_file_refs("compare @a.py and @b.py", str(tmp_path))
    assert warnings == []
    assert 'path="a.py"' in expanded
    assert 'path="b.py"' in expanded


def test_expand_missing_file_leaves_token(tmp_path):
    expanded, _, warnings = expand_file_refs("look at @nonexistent.py", str(tmp_path))
    assert "@nonexistent.py" in expanded
    assert len(warnings) == 1
    assert "not found" in warnings[0].lower()


def test_expand_no_refs(tmp_path):
    text = "hello world"
    expanded, _, warnings = expand_file_refs(text, str(tmp_path))
    assert expanded == text
    assert warnings == []


def test_expand_truncation_by_size(tmp_path):
    (tmp_path / "big.txt").write_bytes(b"x" * (MAX_FILE_BYTES + 1000))
    expanded, _, warnings = expand_file_refs("@big.txt", str(tmp_path))
    assert warnings == []
    assert "truncated" in expanded.lower()


def test_expand_truncation_by_lines(tmp_path):
    content = "\n".join(f"line {i}" for i in range(MAX_FILE_LINES + 100))
    (tmp_path / "long.txt").write_text(content)
    expanded, _, warnings = expand_file_refs("@long.txt", str(tmp_path))
    assert warnings == []
    assert "truncated" in expanded.lower()


def test_expand_subdirectory(tmp_path):
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "main.py").write_text("main\n")
    expanded, _, warnings = expand_file_refs("@src/main.py", str(tmp_path))
    assert warnings == []
    assert 'path="src/main.py"' in expanded
    assert "1\tmain" in expanded


def test_expand_non_utf8_file(tmp_path):
    (tmp_path / "bin.dat").write_bytes(b"\xff\xfe binary \x00 data")
    expanded, _, warnings = expand_file_refs("@bin.dat", str(tmp_path))
    assert warnings == []
    assert 'path="bin.dat"' in expanded


def test_expand_line_numbers_correct(tmp_path):
    (tmp_path / "lines.txt").write_text("alpha\nbeta\ngamma\n")
    expanded, _imgs, _ = expand_file_refs("@lines.txt", str(tmp_path))
    assert "1\talpha" in expanded
    assert "2\tbeta" in expanded
    assert "3\tgamma" in expanded


def test_expand_preserves_surrounding_text(tmp_path):
    (tmp_path / "f.py").write_text("x = 1\n")
    expanded, _imgs, _ = expand_file_refs("before @f.py after", str(tmp_path))
    assert expanded.startswith("before")
    assert "after" in expanded


def test_expand_multiple_errors_all_reported(tmp_path):
    text = "see @missing1.py and @missing2.py"
    expanded, _, warnings = expand_file_refs(text, str(tmp_path))
    assert "@missing1.py" in expanded
    assert "@missing2.py" in expanded
    assert len(warnings) == 2


# ── get_at_completions ────────────────────────────────────────────────────────


def test_completions_lists_files(tmp_path):
    (tmp_path / "main.py").write_text("")
    (tmp_path / "README.md").write_text("")
    (tmp_path / ".hidden").write_text("")
    results = get_at_completions("", str(tmp_path))
    names = [r[0] for r in results]
    assert "main.py" in names
    assert "README.md" in names
    assert ".hidden" not in names


def test_completions_filters_by_prefix(tmp_path):
    (tmp_path / "main.py").write_text("")
    (tmp_path / "utils.py").write_text("")
    results = get_at_completions("mai", str(tmp_path))
    names = [r[0] for r in results]
    assert "main.py" in names
    assert "utils.py" not in names


def test_completions_subdir(tmp_path):
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "api.py").write_text("")
    results = get_at_completions("src/", str(tmp_path))
    names = [r[0] for r in results]
    assert "src/api.py" in names


def test_completions_caps_at_50(tmp_path):
    for i in range(60):
        (tmp_path / f"file{i:03d}.py").write_text("")
    results = get_at_completions("", str(tmp_path))
    assert len(results) <= 50


def test_completions_dirs_marked(tmp_path):
    (tmp_path / "subdir").mkdir()
    (tmp_path / "file.py").write_text("")
    results = get_at_completions("", str(tmp_path))
    dir_entries = [(p, m) for p, m in results if m == "dir"]
    assert any(p.endswith("/") for p, _ in dir_entries)


def test_completions_empty_dir(tmp_path):
    results = get_at_completions("", str(tmp_path))
    assert results == []


def test_completions_nonexistent_subdir(tmp_path):
    results = get_at_completions("nosuchdir/", str(tmp_path))
    assert results == []


# ── image @ references ────────────────────────────────────────────────────────


def test_expand_image_returns_placeholder(tmp_path):
    img = tmp_path / "photo.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    expanded, image_blocks, warnings = expand_file_refs("look at @photo.png", str(tmp_path))
    assert warnings == []
    assert len(image_blocks) == 1
    assert image_blocks[0].media_type == "image/png"
    assert "[image: photo.png]" in expanded
    assert "@photo.png" not in expanded


def test_expand_image_jpeg(tmp_path):
    img = tmp_path / "shot.jpg"
    img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)
    expanded, image_blocks, warnings = expand_file_refs("@shot.jpg", str(tmp_path))
    assert warnings == []
    assert len(image_blocks) == 1
    assert image_blocks[0].media_type == "image/jpeg"


def test_expand_image_too_large(tmp_path):
    img = tmp_path / "huge.png"
    img.write_bytes(b"\x00" * (5 * 1024 * 1024 + 1))
    expanded, image_blocks, warnings = expand_file_refs("@huge.png", str(tmp_path))
    assert len(image_blocks) == 0
    assert len(warnings) == 1
    assert "@huge.png" in expanded  # token left unchanged


def test_expand_mixed_text_and_image(tmp_path):
    (tmp_path / "code.py").write_text("x = 1\n")
    img = tmp_path / "img.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
    expanded, image_blocks, warnings = expand_file_refs(
        "@code.py and @img.png", str(tmp_path)
    )
    assert warnings == []
    assert 'path="code.py"' in expanded
    assert "[image: img.png]" in expanded
    assert len(image_blocks) == 1
