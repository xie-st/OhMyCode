import asyncio
import importlib
import sys


def test_desktop_server_uses_proactor_policy_on_windows(monkeypatch):
    calls = []

    class FakeProactorPolicy:
        pass

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        asyncio,
        "WindowsProactorEventLoopPolicy",
        FakeProactorPolicy,
        raising=False,
    )
    monkeypatch.setattr(asyncio, "set_event_loop_policy", calls.append)

    sys.modules.pop("desktop.server.main", None)
    try:
        importlib.import_module("desktop.server.main")
    finally:
        sys.modules.pop("desktop.server.main", None)

    assert len(calls) == 1
    assert isinstance(calls[0], FakeProactorPolicy)
