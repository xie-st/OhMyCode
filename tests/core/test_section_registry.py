"""Tests for the system-prompt section registry introduced in the kernel-plugins refactor."""

from __future__ import annotations

from ohmycode.core.sections import (
    SectionContext,
    assemble_sections,
    auto_import_sections,
    register_section,
)
from ohmycode.core.system_prompt import build_system_prompt


def test_assemble_orders_by_weight():
    auto_import_sections()

    class _Custom:
        name = "custom_marker"
        order = 35  # between memory (30) and environment (40)

        def render(self, ctx):
            return "<<custom>>"

    register_section(_Custom())

    prompt = build_system_prompt(
        mode="auto",
        cwd="/tmp",
        memory_content="dummy",
    )
    # Memory (order 30) should come before custom (35), which should come
    # before Environment (40).
    memory_pos = prompt.index("# Memory")
    custom_pos = prompt.index("<<custom>>")
    env_pos = prompt.index("# Environment")
    assert memory_pos < custom_pos < env_pos


def test_section_filter_drops_unregistered_names_silently():
    """Names not in the registry are skipped, not raised."""
    auto_import_sections()
    prompt = build_system_prompt(
        mode="auto",
        cwd="/tmp",
        sections=["role", "this_section_does_not_exist", "mode"],
    )
    assert "OhMyCode" in prompt
    assert "AUTO mode" in prompt


def test_section_filter_can_disable_environment():
    auto_import_sections()
    prompt = build_system_prompt(
        mode="auto",
        cwd="/tmp",
        sections=["role", "mode", "tools"],
    )
    assert "# Environment" not in prompt
    assert "AUTO mode" in prompt


def test_default_assembly_includes_all_baseline_sections():
    auto_import_sections()
    prompt = build_system_prompt(
        mode="default",
        cwd="/tmp",
        project_instructions="Use TDD always.",
        memory_content="- user (1): prefers_vim",
        memory_dir="/home/u/mem",
        system_prompt_append="Custom footer.",
    )
    # Baseline: role, project instructions, memory, environment, mode, tools, append
    assert "OhMyCode" in prompt
    assert "Use TDD always." in prompt
    assert "# Memory" in prompt
    assert "# Environment" in prompt
    assert "DEFAULT mode" in prompt
    assert "Custom footer." in prompt

    # Order check: role first, append last.
    assert prompt.index("OhMyCode") < prompt.index("Custom footer.")


def test_assemble_sections_skips_none_returns():
    """A section returning None should not produce a blank stanza."""
    ctx = SectionContext(mode="auto", cwd="/tmp")  # nothing optional set
    out = assemble_sections(ctx, names=["project_instructions"])
    assert out == ""
