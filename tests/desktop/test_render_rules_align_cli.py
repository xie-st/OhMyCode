"""Regression guard: desktop render_rules constants must stay in sync with
``ohmycode/_cli/output.py`` so the two frontends preview the same shape.

If you intentionally diverge the magic numbers, update the CLI source too
and adjust this test.
"""

from __future__ import annotations

from pathlib import Path

from desktop.server import render_rules


_CLI_OUTPUT = Path(__file__).resolve().parents[2] / "ohmycode" / "_cli" / "output.py"


def _cli_source() -> str:
    return _CLI_OUTPUT.read_text(encoding="utf-8")


def test_result_max_lines_matches_cli():
    src = _cli_source()
    assert f"max_lines = {render_rules.RESULT_MAX_LINES}" in src, (
        "ohmycode/_cli/output.py changed its `max_lines = N` constant; "
        "update RESULT_MAX_LINES in desktop/server/render_rules.py to match."
    )


def test_result_max_chars_matches_cli():
    src = _cli_source()
    assert f"len(body) > {render_rules.RESULT_MAX_CHARS}" in src, (
        "ohmycode/_cli/output.py changed its 500-char body cutoff; update "
        "RESULT_MAX_CHARS in desktop/server/render_rules.py to match."
    )


def test_params_max_chars_matches_cli():
    src = _cli_source()
    assert f"len(params_str) > {render_rules.PARAMS_MAX_CHARS}" in src, (
        "ohmycode/_cli/output.py changed its 100-char params cutoff; update "
        "PARAMS_MAX_CHARS in desktop/server/render_rules.py to match."
    )


def test_truncate_params_short_passthrough():
    assert render_rules.truncate_params({"path": "x"}) == '{"path": "x"}'


def test_truncate_params_truncates_long_payload():
    long = {"command": "x" * 200}
    out = render_rules.truncate_params(long)
    assert len(out) == render_rules.PARAMS_MAX_CHARS
    assert out.endswith("...")


def test_truncate_result_short_passthrough():
    preview, truncated = render_rules.truncate_result("hello world")
    assert preview == "hello world"
    assert truncated is False


def test_truncate_result_line_cap():
    text = "\n".join(f"line {i}" for i in range(25))
    preview, truncated = render_rules.truncate_result(text)
    assert truncated is True
    assert preview.startswith("line 0\nline 1")
    assert "25 lines total" in preview


def test_truncate_result_char_cap_on_single_line():
    text = "y" * 800
    preview, truncated = render_rules.truncate_result(text)
    assert truncated is True
    assert len(preview) == render_rules.RESULT_MAX_CHARS
    assert preview.endswith("...")


def test_truncate_result_none_safe():
    preview, truncated = render_rules.truncate_result(None)  # type: ignore[arg-type]
    assert preview == ""
    assert truncated is False
