from __future__ import annotations

from ohmycode.context.packet import ContextPacket


def test_empty_packet_renders_short_placeholder():
    packet = ContextPacket.empty()

    rendered = packet.render()

    assert "Current Working Context" in rendered
    assert "No active long-term topic" in rendered


def test_packet_renders_priority_fields():
    packet = ContextPacket(
        topic_id="topic_agent_runtime",
        title="agent runtime",
        summary="single-window agent with async context curator",
        decisions=["keep event log append-only"],
        open_questions=["how visible should routing be?"],
        next_actions=["wire context packet into prompt"],
        related_files=["ohmycode/core/loop.py"],
        version=7,
    )

    rendered = packet.render()

    assert "agent runtime" in rendered
    assert "single-window agent" in rendered
    assert "keep event log append-only" in rendered
    assert "wire context packet into prompt" in rendered
    assert "version: 7" in rendered


def test_packet_trims_low_priority_sections_before_priority_fields():
    packet = ContextPacket(
        topic_id="topic_big",
        title="big topic",
        summary="important summary",
        decisions=["important decision"],
        related_topics=[f"related topic {i}" for i in range(100)],
        global_memory=[f"memory {i}" for i in range(100)],
    )

    rendered = packet.render(max_chars=500)

    assert len(rendered) <= 500
    assert "important summary" in rendered
    assert "important decision" in rendered
