# Home Configuration Agent

A conversational AI agent for configuring home automation projects. Engineers describe what they want in natural language — the agent translates it into precise operations on floors, rooms, drivers, loads, and macros.

## How It Works

The agent receives a system prompt, the conversation history, and tool schemas on each call. It never gets the full project state dumped into context — instead, it fetches only what it needs via read tools, using conversation history as a cache. A lightweight state summary (floor/room/driver counts) is injected into the system prompt each round so common auto-fill values (like the next floor number) are available without an extra read round-trip.

```
Engineer: create 2 floors with 2 rooms each

  ✓ Tool  : create_floor   → Ground Floor [0]
  ✓ Tool  : create_floor   → Floor 2 [1]
  ✓ Tool  : create_room    → Room 1 (Ground Floor)
  ✓ Tool  : create_room    → Room 2 (Ground Floor)
  ✓ Tool  : create_room    → Room 1 (Floor 2)
  ✓ Tool  : create_room    → Room 2 (Floor 2)
```

## Features

- **Floors** — create, rename, renumber, delete
- **Rooms** — create on a floor, rename, reassign, delete
- **Drivers** — search marketplace catalog, install with auto-assigned IP, update config, uninstall
- **Loads** — add device loads to gateway drivers (lights, covers, AC); auto-assigns KNX group addresses and unit IDs
- **Macros** — named sequences of device actions (turn on/off, set temperature, set brightness, etc.)

## Auto-fill Behavior

The agent fills these silently without asking:

| Field | Rule |
|-------|------|
| `floor_number` | 0-based, auto-increments from current max |
| `floor_name` | "Ground Floor" for 0, "Floor N+1" for N |
| `ip_address` | Starts at 192.168.1.100, skips used |
| `group_address` | KNX format, starts at 1/1/1 |
| `unit_id` | Per-gateway, starts at 1 |
| `load_name` | `{room} {load_type} {index}` |
| `macro_name` | "Macro N" |

## Project Structure

```
home_assistant/
├── agent.py          # Main loop: LLM calls, tool dispatch, state save
├── schema.py         # Tool JSON schemas (floors, rooms, drivers, loads, macros)
├── state.py          # All CRUD logic: validation + mutation + read helpers
├── prompt.txt        # System prompt with agent behavior rules
├── marketplace.json  # Driver catalog (KNX, CoolMaster, BenQ, etc.)
└── project_state.json # Persisted state: floors, rooms, drivers, loads, macros
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and add your OpenRouter API key:

```
OPENROUTER_API_KEY=your_key_here
```

## Run

```bash
python agent.py
```

## Configuration

Edit `agent.py` to change the model:

```python
MODEL = "openrouter/z-ai/glm-4.5-air:free"  # swap for any OpenRouter model ID
```

## State

Project state is persisted to `project_state.json` after every write operation. Delete or empty this file to start fresh.
