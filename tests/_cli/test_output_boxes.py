"""Tests for ScrollingBox base class and subclasses."""

import sys
from io import StringIO
from unittest.mock import patch

from ohmycode._cli.output import (
    MemoryBox,
    ScrollingBox,
    SubAgentBox,
    ThinkingBox,
    _is_interactive,
)


def _make_box_with_fake_stdout(box_cls):
    """Return (box, fake_stdout) with stdout patched to a StringIO."""
    fake = StringIO()
    box = box_cls.__new__(box_cls)
    box_cls.__init__(box)
    return box, fake


# ---------------------------------------------------------------------------
# ScrollingBox hierarchy
# ---------------------------------------------------------------------------


def test_all_subclasses_inherit_scrollingbox():
    assert issubclass(ThinkingBox, ScrollingBox)
    assert issubclass(MemoryBox, ScrollingBox)
    assert issubclass(SubAgentBox, ScrollingBox)


def test_box_headers_are_distinct():
    assert ThinkingBox._header != MemoryBox._header
    assert ThinkingBox._header != SubAgentBox._header
    assert MemoryBox._header != SubAgentBox._header


def test_subagentbox_header_contains_sub_agent():
    assert "Sub-agent" in SubAgentBox._header


def test_thinkingbox_header_contains_thinking():
    assert "Thinking" in ThinkingBox._header


def test_memorybox_header_contains_analyzing():
    assert "Analyzing" in MemoryBox._header


# ---------------------------------------------------------------------------
# ScrollingBox.clear() idempotency
# ---------------------------------------------------------------------------


def test_clear_on_never_drawn_box_does_not_crash():
    box = ThinkingBox()
    with patch.object(sys, "stdout", StringIO()):
        box.clear()
        box.clear()  # second call must not raise


# ---------------------------------------------------------------------------
# SubAgentBox.push_tool()
# ---------------------------------------------------------------------------


def test_push_tool_increments_tool_count():
    box = SubAgentBox()
    with patch.object(sys, "stdout", StringIO()):
        box.push_tool("bash")
        box.push_tool("read_file")
    assert box._tool_count == 2


def test_push_tool_records_tool_name_in_lines():
    box = SubAgentBox()
    with patch.object(sys, "stdout", StringIO()):
        box.push_tool("bash")
    assert any("bash" in line for line in box._lines)


def test_push_tool_formats_with_arrow():
    box = SubAgentBox()
    with patch.object(sys, "stdout", StringIO()):
        box.push_tool("write_file")
    assert any(line.startswith("→") for line in box._lines)


# ---------------------------------------------------------------------------
# SubAgentBox.finish()
# ---------------------------------------------------------------------------


def test_finish_calls_clear():
    box = SubAgentBox()
    cleared = []
    original_clear = box.clear

    def fake_clear():
        cleared.append(True)
        original_clear()

    box.clear = fake_clear
    with patch.object(sys, "stdout", StringIO()), patch("time.sleep"):
        box.finish()

    assert cleared, "finish() must call clear()"


def test_finish_shows_done_line():
    box = SubAgentBox()
    drawn_content = []
    original_draw = box._draw

    def capture_draw():
        drawn_content.append("\n".join(box._lines + ([box._current] if box._current else [])))
        original_draw()

    box._draw = capture_draw
    with patch.object(sys, "stdout", StringIO()), patch("time.sleep"):
        box.push_tool("bash")
        box.finish()

    combined = " ".join(drawn_content)
    assert "done" in combined


def test_finish_includes_tool_count():
    box = SubAgentBox()
    drawn_frames = []
    original_draw = box._draw

    def capture_draw():
        drawn_frames.append(box._build_frame())
        original_draw()

    box._draw = capture_draw
    with patch.object(sys, "stdout", StringIO()), patch("time.sleep"):
        box.push_tool("bash")
        box.push_tool("read")
        box.finish()

    combined = " ".join(drawn_frames)
    assert "2 tools" in combined


# ---------------------------------------------------------------------------
# _is_interactive()
# ---------------------------------------------------------------------------


def test_is_interactive_false_when_stringio():
    with patch.object(sys, "stdout", StringIO()):
        assert _is_interactive() is False


def test_is_interactive_true_when_isatty_returns_true():
    class FakeTTY:
        def isatty(self):
            return True

    with patch.object(sys, "stdout", FakeTTY()):
        assert _is_interactive() is True
