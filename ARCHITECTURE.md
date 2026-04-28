# 1Claw — Architecture & Technical Reference

## Overview

```
┌─────────────────────┐     WebSocket      ┌──────────────────────┐
│   Flutter App        │ ◄──────────────►  │   Go Server (1claw)  │
│   (iOS/Android/      │     JSON protocol  │                      │
│    macOS/Windows)    │                    │   ┌──────────────┐   │
└─────────────────────┘                    │   │  MockBridge   │   │
                                           │   │  (dev only)   │   │
                                           │   └──────┬───────┘   │
                                           │   ┌──────▼───────┐   │
                                           │   │ HermesBridge  │   │
                                           │   │  (production)  │   │
                                           │   └──────┬───────┘   │
                                           │          │ stdin/    │
                                           │          │ stdout    │
                                           │          │ (JSON)    │
                                           │   ┌──────▼───────┐   │
                                           │   │ Python Bridge  │   │
                                           │   │ (subprocess)   │   │
                                           │   └──────┬───────┘   │
                                           └──────────┼───────────┘
                                                      │
                                           ┌──────────▼───────────┐
                                           │   AIAgent (Hermes)   │
                                           │   • deepseek-v4-flash │
                                           │   • ~/.hermes/profiles│
                                           │   • state.db memory   │
                                           └──────────────────────┘
```

## Repositories

| Repo | GitLab | Purpose |
|------|--------|---------|
| **1claw** (top) | `john/1claw` | Submodules + design docs |
| **1claw-server** | `john/1claw-server` | Go WebSocket gateway |
| **1claw-app** | `john/1claw-app` | Flutter multi-agent UI |

## Bridges

The server supports two agent backends via the `agent.Provider` interface:

### 1. MockBridge (development)
- Simple echo: `"[Name] You said: {message}"`
- No external dependencies
- Use with `--mock` flag
- Instant startup, always works

### 2. HermesBridge (production)
- Spawns `scripts/hermes_bridge.py` as a subprocess
- Communicates via **JSON-over-stdin/stdout** (line-delimited)
- Each profile gets a real `AIAgent` instance
- Lazy initialization: echo first, real AI in background thread

#### Protocol (Go → Python Bridge)

```json
{"type": "init", "profiles": [...]}
{"type": "chat", "profile_id": "dev", "content": "Hello", "id": "msg_001"}
{"type": "status"}
{"type": "start_profile", "profile_id": "dev"}
{"type": "shutdown"}
```

#### Protocol (Python Bridge → Go)

```json
{"type": "ready", "profile_count": 8}
{"type": "chat", "profile_id": "dev", "content": "Hi!", "id": "msg_001"}
{"type": "status", "profiles": [...]}
{"type": "agent_starting", "profile_id": "dev"}
{"type": "agent_ready", "profile_id": "dev", "status": "real"}
{"type": "error", "code": "...", "message": "..."}
```

## Profile Discovery

At startup, the Go server scans `~/.hermes/profiles/` for profile directories:

```
~/.hermes/
├── config.yaml              ← Default profile (root)
├── .env                     ← Global API keys
├── state.db                 ← Session memory (SQLite)
└── profiles/
    ├── dev/
    │   ├── config.yaml      ← Model, provider, api_key, base_url
    │   ├── .env             ← Profile-specific env vars
    │   └── AGENTS.md        ← Persona / identity instructions
    ├── 1claw/
    ├── assist/
    └── ...
```

Each profile is assigned a deterministic emoji + color via FNV hash of the name.

## Lazy Agent Initialization

To avoid slow startup (each AIAgent takes 10-60s to init), 1Claw uses a two-phase approach:

1. **Phase 1 (instant):** All profiles get an echo agent. Server starts in < 5s.
2. **Phase 2 (on demand):** When user taps a card or sends `start_profile`, background thread creates real AIAgent.

```
User taps "dev" card
  → WS sends {"type": "start_profile", "profile_id": "dev"}
  → Go forwards to Python bridge
  → Bridge sends {"type": "agent_starting", "profile_id": "dev"}
  → UI shows "Starting..." status
  → Thread runs AIAgent(provider="deepseek", model="deepseek-v4-flash", ...)
  → On success: {"type": "agent_ready", "profile_id": "dev"}
  → UI updates to "Online", next chat goes to real AI
  → On failure: echo agent remains, error logged
```

## Environment & Config Loading

The Python bridge loads credentials in this order:

1. **`~/.hermes/.env`** — global API keys
2. **`/etc/environment`** — system-wide env
3. **`~/.hermes/profiles/<name>/.env`** — per-profile env
4. **`~/.hermes/profiles/<name>/config.yaml`** — model/provider/api_key/base_url

The `_load_profile_config()` helper reads the profile's `config.yaml` and passes values to `AIAgent(provider=..., api_key=..., base_url=..., model=...)`.

**Critical:** `HERMES_PROFILE` env var must be set before creating each AIAgent so it loads the correct persona/AGENTS.md from the profile directory.

## Thread Safety

The Python bridge runs in a separate process. Multiple background threads initialize different profiles concurrently.

### stdout isolation
AIAgent's spinner/activity feed writes to `sys.stdout`, which would corrupt the JSON protocol. Solution:
- Save `_original_stdout = sys.stdout` at module level
- Before calling AIAgent code: `sys.stdout = sys.stderr`
- Restore after: `sys.stdout = _original_stdout`
- The `_send()` method always writes to `_original_stdout` directly (thread-safe)

### HERMES_PROFILE race
`os.environ` is process-global. When multiple threads set `HERMES_PROFILE` simultaneously, one thread may read the wrong value. Fix:
- Save old value before setting
- Use try/finally to restore
- Window is small (just during `AIAgent.__init__` which reads it once)

## WebSocket Protocol (Flutter ↔ Go)

### Client → Server

| Type | Purpose |
|------|---------|
| `chat` | Send message to an agent |
| `switch_profile` | Change active profile |
| `ping` | Heartbeat |
| `get_status` | Request profile status |
| `start_profile` | Trigger real AI init for a profile |

### Server → Client

| Type | Purpose |
|------|---------|
| `status` | Profile list with online/status |
| `chat` | Agent response |
| `pong` | Heartbeat response |
| `error` | Error with code + message |

## How to Run

```bash
# 1. Start the Go server (auto-detects Hermes)
cd 1claw-server
make build
./1claw-server

# 2. Or use mock mode (no API keys needed)
./1claw-server --mock

# 3. Run the Flutter app
cd 1claw-app
flutter run -d linux
```

## Debugging

Check the server log for bridge initialization:

```bash
# Real-time bridge logs
tail -f /tmp/server*.log | grep "hermes-bridge"

# Check which agents are real vs echo
# All profiles online=echo, then background threads upgrade to real
# Look for "✅" (real) or "⚠️" (failed, keeping echo)

# Force start a specific agent via WebSocket
python3 -c "
import asyncio, json, websockets
async def t():
    async with websockets.connect('ws://localhost:8080/ws') as ws:
        await asyncio.wait_for(ws.recv(), timeout=5)
        await ws.send(json.dumps({'type':'start_profile','profile_id':'dev'}))
        print(await asyncio.wait_for(ws.recv(), timeout=30))
asyncio.run(t())
"
```
