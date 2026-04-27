"""Tests for system_prompt — build_system_prompt and find_project_instructions."""

from __future__ import annotations

import pytest

from ohmycode.core.system_prompt import build_system_prompt, find_project_instructions


# ---- build_system_prompt ----

def test_build_contains_identity():
    prompt = build_system_prompt(mode="auto", cwd="/tmp")
    assert "OhMyCode" in prompt


def test_build_mode_auto():
    prompt = build_system_prompt(mode="auto", cwd="/tmp")
    assert "AUTO mode" in prompt


def test_build_mode_default():
    prompt = build_system_prompt(mode="default", cwd="/tmp")
    assert "DEFAULT mode" in prompt


def test_build_mode_plan():
    prompt = build_system_prompt(mode="plan", cwd="/tmp")
    assert "PLAN mode" in prompt


def test_build_unknown_mode_falls_back():
    prompt = build_system_prompt(mode="bogus", cwd="/tmp")
    assert "DEFAULT mode" in prompt


def test_build_includes_project_instructions():
    prompt = build_system_prompt(
        mode="auto", cwd="/tmp", project_instructions="Use TDD always."
    )
    assert "Use TDD always." in prompt
    assert "Project Instructions" in prompt


def test_build_includes_memory():
    prompt = build_system_prompt(mode="auto", cwd="/tmp", memory_content="User prefers vim.")
    assert "User prefers vim." in prompt
    assert "Memory" in prompt


def test_memory_section_includes_usage_guidance_when_entries_exist():
    prompt = build_system_prompt(
        mode="auto",
        cwd="/tmp",
        memory_content="- user (1): prefers_vim",
        memory_dir="/home/u/.ohmycode/projects/abc/memory",
    )
    assert "/home/u/.ohmycode/projects/abc/memory" in prompt
    assert "When to consult memory" in prompt


def test_memory_section_omits_guidance_when_empty():
    prompt = build_system_prompt(
        mode="auto",
        cwd="/tmp",
        memory_content="# Memory Index\n(no memories yet)",
        memory_dir="/home/u/.ohmycode/projects/abc/memory",
    )
    assert "When to consult memory" not in prompt


def test_build_includes_append():
    prompt = build_system_prompt(
        mode="auto", cwd="/tmp", system_prompt_append="Custom footer."
    )
    assert "Custom footer." in prompt


def test_build_no_optional_sections():
    prompt = build_system_prompt(mode="auto", cwd="/tmp")
    assert "Project Instructions" not in prompt
    assert "# Memory" not in prompt


def test_build_includes_cwd():
    prompt = build_system_prompt(mode="auto", cwd="/my/project")
    assert "/my/project" in prompt


# ---- find_project_instructions ----

def test_find_claude_md_in_current_dir(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# My Project Rules")
    result = find_project_instructions(str(tmp_path))
    assert "My Project Rules" in result


def test_find_ohmycode_md_in_current_dir(tmp_path):
    (tmp_path / "OHMYCODE.md").write_text("# OhMyCode Rules")
    result = find_project_instructions(str(tmp_path))
    assert "OhMyCode Rules" in result


def test_find_claude_md_preferred_over_ohmycode(tmp_path):
    """CLAUDE.md is checked first, so it wins if both exist."""
    (tmp_path / "CLAUDE.md").write_text("claude wins")
    (tmp_path / "OHMYCODE.md").write_text("ohmycode loses")
    result = find_project_instructions(str(tmp_path))
    assert "claude wins" in result


def test_find_traverses_parent(tmp_path):
    child = tmp_path / "src" / "deep"
    child.mkdir(parents=True)
    (tmp_path / "CLAUDE.md").write_text("root instructions")
    result = find_project_instructions(str(child))
    assert "root instructions" in result


def test_find_returns_empty_if_none(tmp_path):
    child = tmp_path / "empty_project"
    child.mkdir()
    result = find_project_instructions(str(child))
    assert result == ""
