# 1Claw — Multi-Agent Platform Design Document

## Overview
1Claw is a mobile-first multi-agent platform that keeps multiple Hermes AI agent profiles **simultaneously online** 24/7. Users connect via a Flutter mobile/desktop app through a WebSocket long connection — no SSH required.

## Architecture

```
┌─────────────────────────────────────────────┐
│              Mobile/Desktop App              │
│          Flutter (iOS/Android/macOS/Win)     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐     │
│  │  🤖 AI   │ │  ✍️Writer │ │  💻Coder │     │
│  │ Assistant│ │          │ │          │     │
│  └──────────┘ └──────────┘ └──────────┘     │
│           Metro-style Card Grid              │
└──────────────────┬──────────────────────────┘
                   │ WebSocket (wss://)
                   │ JSON protocol
                   │ Auto-reconnect + Heartbeat
┌──────────────────▼──────────────────────────┐
│          1Claw Server (Go Gateway)            │
│                                              │
│  ┌──────────────────────────────────────┐    │
│  │         WebSocket Hub                 │    │
│  │  Client <-> Profile Routing Engine   │    │
│  └──────────────────────────────────────┘    │
│              │          │                    │
│    ┌─────────▼──┐ ┌─────▼────────┐         │
│    │Profile Mgr │ │  Agent Bridge│          │
│    │ (CRUD,     │ │  (Hermes     │          │
│    │  status)   │ │   Interface) │          │
│    └────────────┘ └─────┬────────┘          │
│                         │                    │
└─────────────────────────┼────────────────────┘
                          │
              ┌───────────▼───────────┐
              │   Hermes Agent Kernel  │
              │  (External Process)    │
              │                        │
              │  Profile: default      │
              │  Profile: writer       │
              │  Profile: coder        │
              └────────────────────────┘
```

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | Flutter + Dart | Cross-platform UI (iOS/Android/macOS/Windows) |
| Backend | Go 1.22+ | WebSocket gateway, profile management |
| Communication | WebSocket | Real-time bidirectional messaging |
| Agent Kernel | Hermes | Multi-profile AI agent engine |
| Config | YAML | Server and profile configuration |
| State Management | Provider (Flutter) | Reactive UI state |

## WebSocket Protocol

### Message Types (Client → Server)

```json
{
  "type": "chat",
  "profile_id": "assistant",
  "content": "Hello, how are you?",
  "id": "msg_001"
}

{
  "type": "switch_profile",
  "profile_id": "writer"
}

{
  "type": "ping"
}

{
  "type": "get_status"
}
```

### Message Types (Server → Client)

```json
{
  "type": "chat",
  "profile_id": "assistant",
  "content": "I'm doing great!",
  "id": "msg_001",
  "timestamp": "2026-04-28T12:00:00Z"
}

{
  "type": "status",
  "profiles": [
    {"id": "assistant", "name": "AI Assistant", "emoji": "🤖", "online": true},
    {"id": "writer", "name": "Creative Writer", "emoji": "✍️", "online": true}
  ]
}

{
  "type": "error",
  "message": "Profile not found",
  "code": "PROFILE_NOT_FOUND"
}

{
  "type": "pong"
}
```

## Data Models

### Profile
- id: string (unique identifier)
- name: string (display name)
- emoji: string (card emoji)
- description: string (brief description)
- hermesProfile: string (Hermes profile name)
- online: bool (current status)
- color: string (card color hex)
- createdAt: timestamp
- updatedAt: timestamp

### Chat Message
- id: string (unique)
- profileId: string
- content: string
- role: "user" | "agent"
- timestamp: datetime

## Component Tree (Flutter)

```
App
├── MaterialApp (Theme: dark/light)
│   └── HomeScreen
│       ├── ConnectionIndicator
│       ├── ProfileGrid
│       │   └── AgentCard (× N profiles)
│       └── FAB → SettingsScreen
│   └── ChatScreen
│       ├── ChatHeader (profile info)
│       ├── MessageList
│       │   └── ChatBubble (× N messages)
│       └── MessageInput
└── SettingsScreen
    ├── ServerConfig
    ├── ThemeToggle
    └── About
```

## REST API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/status | Server health + profile status |
| GET | /api/profiles | List all profiles |
| POST | /api/profiles | Create profile |
| PUT | /api/profiles/:id | Update profile |
| DELETE | /api/profiles/:id | Delete profile |
| GET | /ws | WebSocket upgrade |

## Project Structure

### Server (1claw-server)
```
1claw-server/
├── main.go
├── go.mod / go.sum
├── config.yaml
├── internal/
│   ├── ws/          — WebSocket hub + client
│   ├── agent/       — Agent bridge + profile manager
│   ├── api/         — REST API handlers
│   ├── config/      — Config loader
│   └── model/       — Shared types
├── Dockerfile
├── README.md
└── DESIGN.md
```

### App (claw_app)
```
claw_app/
├── lib/
│   ├── main.dart
│   ├── app.dart
│   ├── config/constants.dart
│   ├── models/      — Data models
│   ├── services/    — WebSocket + API
│   ├── providers/   — State management
│   ├── screens/     — UI pages
│   └── widgets/     — Reusable components
├── test/            — Unit + widget tests
├── pubspec.yaml
└── DESIGN.md
```
