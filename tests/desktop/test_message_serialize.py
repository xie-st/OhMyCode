from desktop.server._message_serialize import deserialize_message, serialize_message
from ohmycode.core.messages import (
    AssistantMessage,
    ImageBlock,
    ToolResultMessage,
    ToolUseBlock,
    UserMessage,
)


def test_message_serialize_round_trips_tool_sequence():
    messages = [
        UserMessage("inspect repo"),
        AssistantMessage(
            "I will read it.",
            tool_calls=[
                ToolUseBlock(
                    tool_use_id="tool-1",
                    tool_name="read",
                    params={"path": "README.md"},
                )
            ],
        ),
        ToolResultMessage("tool-1", "contents", is_error=False),
        AssistantMessage("Done."),
    ]

    restored = [deserialize_message(serialize_message(message)) for message in messages]

    assert restored == messages
    assert restored[1].to_api_dict()["tool_calls"][0]["id"] == "tool-1"
    assert restored[2].to_api_dict()["tool_call_id"] == "tool-1"


def test_message_serialize_round_trips_image_blocks():
    message = UserMessage(
        content=[
            "look at this",
            ImageBlock(media_type="image/png", data="abc123"),
        ]
    )

    restored = deserialize_message(serialize_message(message))

    assert restored == message
    api_content = restored.to_api_dict()["content"]
    assert api_content[1]["image_url"]["url"] == "data:image/png;base64,abc123"
