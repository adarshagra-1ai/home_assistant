import os
import json
from dotenv import load_dotenv

load_dotenv()

import litellm
litellm.suppress_debug_info = True

from schema import TOOLS
from state import (
    load_state,
    save_state,
    load_catalog,
    validate_tool_call,
    update_state,
    get_next_ip,
    get_floor_from_state,
    get_all_floors_from_state,
    get_room_from_state,
    get_all_rooms_from_state,
    get_marketplace_drivers,
    get_driver_config_from_catalog,
    get_installed_drivers_from_state,
    get_loads_from_state,
    get_all_macros_from_state,
    get_state_summary,
)

# ── Config ────────────────────────────────────────────────────

HERE         = os.path.dirname(os.path.abspath(__file__))
STATE_FILE   = os.path.join(HERE, "project_state.json")
CATALOG_FILE = os.path.join(HERE, "marketplace.json")

MODEL         = "openrouter/z-ai/glm-4.5-air:free"
HISTORY_LIMIT = 10
MAX_ROUNDS    = 5

# ── Load resources once at startup ───────────────────────────

with open(os.path.join(HERE, "prompt.txt")) as f:
    _BASE_PROMPT = f.read().strip()

catalog = load_catalog(CATALOG_FILE)


# ── LLM call helper ───────────────────────────────────────────

def _call_llm(messages: list):
    response = litellm.completion(
        model=MODEL,
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
        temperature=0,
        stream=True,
    )
    chunks        = []
    reply_started = False
    for chunk in response:
        chunks.append(chunk)
        delta = chunk.choices[0].delta
        if delta.content:
            if not reply_started:
                print("\n  Agent: ", end="", flush=True)
                reply_started = True
            print(delta.content, end="", flush=True)
    if reply_started:
        print("\n")
    return litellm.stream_chunk_builder(chunks, messages=messages).choices[0].message


def _tool_result(tool_call_id: str, result: dict) -> dict:
    return {
        "role":         "tool",
        "tool_call_id": tool_call_id,
        "content":      json.dumps(result),
    }


# ── Core agent function ───────────────────────────────────────

def run_agent(conversation_history: list, project_state: dict) -> list:
    messages = [None] + conversation_history  # slot 0 reserved for system message

    for _ in range(MAX_ROUNDS):
        messages[0] = {
            "role":    "system",
            "content": f"{_BASE_PROMPT}\n\nCurrent state: {get_state_summary(project_state)}.",
        }
        choice = _call_llm(messages)

        # ── Plain text reply ──────────────────────────────────
        if not choice.tool_calls:
            reply = (choice.content or "").strip()
            if reply:
                conversation_history.append({"role": "assistant", "content": reply})
            return conversation_history

        messages.append(choice)
        any_write = False

        for tc in choice.tool_calls:
            name = tc.function.name
            try:
                params = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError as e:
                print(f"\n  [error] Bad JSON in '{name}': {e}")
                messages.append(_tool_result(tc.id, {"error": str(e)}))
                continue

            # ── Read-only tools ───────────────────────────────

            if name == "get_floor":
                result = get_floor_from_state(
                    project_state,
                    floor_name=params.get("floor_name"),
                    floor_number=params.get("floor_number"),
                )
                print(f"\n  → Fetching floor: {params}")
                messages.append(_tool_result(tc.id, result))
                continue

            if name == "read_all_floors":
                result = get_all_floors_from_state(project_state)
                messages.append(_tool_result(tc.id, result))
                continue

            if name == "get_room":
                result = get_room_from_state(
                    project_state,
                    room_name=params.get("room_name"),
                    floor_name=params.get("floor_name"),
                    floor_number=params.get("floor_number"),
                )
                print(f"\n  → Fetching room: {params}")
                messages.append(_tool_result(tc.id, result))
                continue

            if name == "read_all_rooms":
                result = get_all_rooms_from_state(project_state)
                messages.append(_tool_result(tc.id, result))
                continue

            if name == "list_marketplace_drivers":
                result = get_marketplace_drivers(catalog, params.get("search_query"))
                print(f"\n  → Searching marketplace: {params.get('search_query', 'all')}")
                messages.append(_tool_result(tc.id, result))
                continue

            if name == "get_driver_config":
                result = get_driver_config_from_catalog(catalog, params.get("driver_id", ""))
                print(f"\n  → Fetching driver config: {params.get('driver_id')}")
                messages.append(_tool_result(tc.id, result))
                continue

            if name == "list_installed_drivers":
                result = get_installed_drivers_from_state(project_state, params.get("search_query"))
                messages.append(_tool_result(tc.id, result))
                continue

            if name == "list_loads":
                result = get_loads_from_state(project_state, params.get("install_id"))
                messages.append(_tool_result(tc.id, result))
                continue

            if name == "read_all_macros":
                result = get_all_macros_from_state(project_state)
                messages.append(_tool_result(tc.id, result))
                continue

            # ── Pre-processing for write tools ────────────────

            # Auto-fill ip_address for install_driver
            if name == "install_driver":
                config = params.setdefault("config", {})
                if "ip_address" not in config or not config["ip_address"]:
                    config["ip_address"] = get_next_ip(project_state)
                else:
                    used = {
                        d.get("config", {}).get("ip_address")
                        for d in project_state.get("installed_drivers", [])
                    }
                    if config["ip_address"] in used:
                        config["ip_address"] = get_next_ip(project_state)

                # Strip any config fields the LLM invented that are not in catalog schema
                driver_record = next(
                    (d for d in catalog.get("drivers", []) if d["driver_id"] == params.get("driver_id")),
                    None,
                )
                if driver_record:
                    valid_fields = {f["field"] for f in driver_record.get("config_schema", [])}
                    params["config"] = {
                        k: v for k, v in params["config"].items()
                        if k in valid_fields
                    }

            # ── Write tools: validate ─────────────────────────

            error = validate_tool_call(project_state, name, params, catalog)

            # NO_FLOOR_EXISTS → auto-create Ground Floor then retry
            if error == "NO_FLOOR_EXISTS":
                print(f"\n  → No floor exists. Auto-creating Ground Floor.")
                update_state(project_state, "create_floor", {}, catalog)
                any_write = True
                print(f"\n  ✓ Tool  : create_floor")
                print(f"    Params: {{}} (auto-created)")
                error = validate_tool_call(project_state, name, params, catalog)

            # FLOOR_AMBIGUOUS → ask engineer which floor
            if error == "FLOOR_AMBIGUOUS":
                floors   = project_state.get("floors", [])
                options  = ", ".join(
                    f"'{f['floor_name']}' (number {f['floor_number']})" for f in floors
                )
                feedback = (
                    f"Multiple floors exist: {options}. "
                    f"Which floor should '{params.get('room_name')}' be created on?"
                )
                messages.append(_tool_result(tc.id, {"error": feedback}))
                continue

            # ROOM_REQUIRED → ask engineer which room
            if error and error.startswith("ROOM_REQUIRED:"):
                subject = error.split(":", 1)[1]
                feedback = f"Which room should the {subject} be installed in?"
                messages.append(_tool_result(tc.id, {"error": feedback}))
                continue

            # GATEWAY_AMBIGUOUS → ask engineer which gateway
            if error == "GATEWAY_AMBIGUOUS":
                gateways = [
                    d for d in project_state.get("installed_drivers", [])
                    if d.get("type") == "gateway"
                ]
                options  = ", ".join(
                    f"'{d['driver_name']}' (install_id={d['install_id']})" for d in gateways
                )
                feedback = (
                    f"Multiple gateways found: {options}. "
                    f"Which gateway does '{params.get('load_name')}' belong to?"
                )
                messages.append(_tool_result(tc.id, {"error": feedback}))
                continue

            # All other validation errors
            if error:
                print(f"\n  [validation] Skipped '{name}': {error}")
                messages.append(_tool_result(tc.id, {"error": error}))
                continue

            # ── Execute ───────────────────────────────────────

            update_state(project_state, name, params, catalog)
            any_write = True

            print(f"\n  ✓ Tool  : {name}")
            print(f"    Params: {json.dumps(params, indent=4)}")

            messages.append(_tool_result(tc.id, {"success": True}))

        # ── Save after writes, continue loop ─────────────────
        if any_write:
            save_state(project_state, STATE_FILE)

    return conversation_history


# ── Main loop ─────────────────────────────────────────────────

if __name__ == "__main__":
    print("Home Configuration Agent\n")

    history:       list = []
    project_state: dict = load_state(STATE_FILE)

    while True:
        try:
            user_input = input("Engineer: ").strip()
            if not user_input:
                continue

            history.append({"role": "user", "content": user_input})
            

            if len(history) > HISTORY_LIMIT:
                history = history[-HISTORY_LIMIT:]

            history = run_agent(history, project_state)

        except KeyboardInterrupt:
            print("\n  Agent stopped.")
            break
        except Exception as e:
            print(f"\n  [error] {e}\n")