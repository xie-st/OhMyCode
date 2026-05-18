# OhMyCode Desktop (MVP)

Two-window desktop prototype for OhMyCode:

- **Window A** runs the normal coding conversation through the existing OhMyCode `ConversationLoop`.
- **Window B** observes Window A and gives learning-focused explanations during safe waiting windows.

## Run

```powershell
# backend
python -m uvicorn desktop.server.main:app --port 8765 --reload

# frontend
cd desktop/web
npm install
npm run dev
# open http://localhost:5173
```

The backend WebSocket is `ws://localhost:8765/ws`. Vite proxies `/ws` and `/api` from `localhost:5173`.

## Architecture

- FastAPI WebSocket server on port 8765.
- React + Vite + Tailwind v3 + zustand frontend on port 5173.
- One active `DesktopSession` per browser connection.
- Window A and Window B each own a separate `ConversationLoop` and provider instance.
- Window A events are serialized to the browser and also observed by Window B.
- Window B uses a smaller model when the provider mapping is known.

## Features

- Window A streams text, tool calls, tool results, and turn completion events.
- Window B is triggered by long tool waits, turn boundaries, and repeated errors.
- Window B trigger guardrails include a 60s cooldown, 10min/5x cap, typing mute, and 3s delayed tool trigger.
- GUI permission requests support Allow once, Always allow, Deny, and Esc=Deny.
- Esc outside a permission dialog cancels the current Window A turn.
- Profile data is stored under `~/.ohmycode/projects/<slug>/profile/profile.json`.
- Profile UI lets the user inspect evidence, delete individual evidence, or clear the profile.

## Test

```powershell
python -m pytest tests/desktop/ -v
```

Recent M4.1 baseline: 46 desktop tests and 390 total tests passed. M4.2 adds cancel-on-disconnect coverage.

## Known Gaps

- Only one browser tab/client is supported.
- Window B trigger tuning still needs browser demo verification.
- Frontend test coverage is not yet wired into CI.
- Browser e2e coverage is still pending.
