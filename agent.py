import os
import json
import time

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


MODEL = "openrouter/owl-alpha"
HISTORY_LIMIT = 10
MAX_ROUNDS    = 5

# ── Load resources once at startup ───────────────────────────

with open(os.path.join(HERE, "prompt.txt")) as f:
    _BASE_PROMPT = f.read().strip()

catalog = load_catalog(CATALOG_FILE)


# ── Tool classification ───────────────────────────────────────

_READ_TOOLS = frozenset({
    "get_floor", "read_all_floors", "get_room", "read_all_rooms",
    "list_marketplace_drivers", "get_driver_config", "list_installed_drivers",
    "list_loads", "read_all_macros",
})

_WRITE_CONFIRMATIONS = {
    "create_floor":     lambda p: f"Created floor '{p['floor_name']}'." if p.get("floor_name") else "Floor created.",
    "update_floor":     lambda _: "Floor updated.",
    "delete_floor":     lambda p: "All floors deleted." if p.get("delete_all") else "Floor deleted.",
    "create_room":      lambda p: f"Created room '{p['room_name']}'.",
    "update_room":      lambda _: "Room updated.",
    "delete_room":      lambda p: "All rooms deleted." if p.get("delete_all") else "Room deleted.",
    "install_driver":   lambda _: "Driver installed.",
    "update_driver":    lambda _: "Driver updated.",
    "uninstall_driver": lambda _: "Driver uninstalled.",
    "add_load":         lambda p: f"Load '{p.get('load_name', 'load')}' added.",
    "update_load":      lambda _: "Load updated.",
    "remove_load":      lambda p: f"Load '{p.get('load_name', 'load')}' removed.",
    "create_macro":     lambda p: f"Macro '{p.get('macro_name', 'Macro')}' created.",
    "update_macro":     lambda _: "Macro updated.",
    "delete_macro":     lambda p: "All macros deleted." if p.get("delete_all") else "Macro deleted.",
}


# ── LLM call helper ───────────────────────────────────────────

def _call_llm(messages: list):
    response = litellm.completion(
        model=MODEL,
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
        temperature=0,
        stream=True,
        stream_options={"include_usage": True},
    )
    chunks        = []
    reply_parts   = []
    for chunk in response:
        chunks.append(chunk)
        delta = chunk.choices[0].delta
        if delta.content:
            reply_parts.append(delta.content)
    full_response = litellm.stream_chunk_builder(chunks, messages=messages)
    usage = full_response.usage
    tokens = getattr(usage, "prompt_tokens", 0) + getattr(usage, "completion_tokens", 0)
    return full_response.choices[0].message, tokens, "".join(reply_parts)


_CREATE_TOOLS = {
    "create_floor":   ("floors",            ["floor_name", "floor_number"]),
    "create_room":    ("rooms",             ["room_name", "floor_id"]),
    "install_driver": ("installed_drivers", ["install_id", "driver_name"]),
    "add_load":       ("loads",             ["load_id", "load_name"]),
    "create_macro":   ("macros",            ["macro_name"]),
}

def _success_result(name: str, params: dict, state: dict) -> dict:
    result = {"success": True}
    if name in _CREATE_TOOLS:
        # Read actual entity — captures auto-filled values (name, number, id)
        collection, fields = _CREATE_TOOLS[name]
        entity = (state.get(collection) or [None])[-1]
        if entity:
            result.update({f: entity[f] for f in fields if f in entity})
    else:
        # Update / delete / uninstall / remove — echo back identifying params
        result.update({k: v for k, v in params.items() if not isinstance(v, (dict, list))})
    return result


def _tool_result(tool_call_id: str, result: dict) -> dict:
    return {
        "role":         "tool",
        "tool_call_id": tool_call_id,
        "content":      json.dumps(result),
    }


# ── Core agent function ───────────────────────────────────────

def run_agent(conversation_history: list, project_state: dict) -> tuple:
    messages     = [None] + conversation_history  # slot 0 reserved for system message
    sys_dirty    = True
    total_tokens = 0

    for _ in range(MAX_ROUNDS):
        if sys_dirty:
            messages[0] = {
                "role":    "system",
                "content": f"{_BASE_PROMPT}\n\nCurrent state: {get_state_summary(project_state)}.",
            }
            sys_dirty = False

        choice, tokens, streamed_text = _call_llm(messages)
        total_tokens += tokens

        # ── Plain text reply ──────────────────────────────────
        if not choice.tool_calls:
            reply = (choice.content or streamed_text or "").strip()
            if not reply:
                print("\n  [warn] Model returned empty response. Try rephrasing.\n")
                return conversation_history, total_tokens
            print(f"Messages:\n{json.dumps(messages, indent=2, default=str)}\n")
            print(f"\n  Agent: {reply}\n")
            conversation_history.append({"role": "assistant", "content": reply})
            return conversation_history, total_tokens

        messages.append(choice)
        any_write        = False
        had_read         = False
        had_error        = False
        completed_writes = []

        for tc in choice.tool_calls:
            name = tc.function.name
            if name in _READ_TOOLS:
                had_read = True
            try:
                params = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError as e:
                print(f"\n  [error] Bad JSON in '{name}': {e}")
                messages.append(_tool_result(tc.id, {"error": str(e)}))
                had_error = True
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

            # Auto-fill room_name for create_room
            if name == "create_room" and not params.get("room_name"):
                floor_name   = params.get("floor_name")
                floor_number = params.get("floor_number")
                floors       = project_state.get("floors", [])
                if floor_name is not None or floor_number is not None:
                    target = next(
                        (f for f in floors
                         if (floor_name   is None or f["floor_name"]   == floor_name) and
                            (floor_number is None or f["floor_number"] == floor_number)),
                        None,
                    )
                elif len(floors) == 1:
                    target = floors[0]
                else:
                    target = None
                if target:
                    count = sum(1 for r in project_state.get("rooms", []) if r.get("floor_id") == target["floor_id"])
                else:
                    count = len(project_state.get("rooms", []))
                params["room_name"] = f"Room {count + 1}"

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
                had_error = True
                continue

            # ROOM_REQUIRED → ask engineer which room
            if error and error.startswith("ROOM_REQUIRED:"):
                subject = error.split(":", 1)[1]
                feedback = f"Which room should the {subject} be installed in?"
                messages.append(_tool_result(tc.id, {"error": feedback}))
                had_error = True
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
                had_error = True
                continue

            # All other validation errors
            if error:
                print(f"\n  [validation] Skipped '{name}': {error}")
                messages.append(_tool_result(tc.id, {"error": error}))
                had_error = True
                continue

            # ── Execute ───────────────────────────────────────

            update_state(project_state, name, params, catalog)
            any_write = True
            completed_writes.append((name, params))

            print(f"\n  ✓ Tool  : {name}")
            print(f"    Params: {json.dumps(params, indent=4)}")

            messages.append(_tool_result(tc.id, _success_result(name, params, project_state)))

        # ── Save after writes ─────────────────────────────────
        if any_write:
            save_state(project_state, STATE_FILE)
            sys_dirty = True
            # Skip second LLM call for pure write rounds — generate confirmation directly
            if not had_read and not had_error:
                parts = [_WRITE_CONFIRMATIONS[n](p) for n, p in completed_writes if n in _WRITE_CONFIRMATIONS]
                reply = " ".join(parts)
                if reply:
                    print(f"Messages:\n{json.dumps(messages, indent=2, default=str)}\n")
                    print(f"\n  Agent: {reply}\n")
                    conversation_history.append({"role": "assistant", "content": reply})
                return conversation_history, total_tokens

    return conversation_history, total_tokens


# ── Main loop ─────────────────────────────────────────────────

if __name__ == "__main__":
    print("Home Configuration Agent\n")

    history:       list = []
    project_state: dict = load_state(STATE_FILE)

    while True:
        try:
            print("=" * 50)
            user_input = input("Engineer: ").strip()
            print("=" * 50)
            if not user_input:
                continue

            history.append({"role": "user", "content": user_input})

            start = time.time()
            history, tokens = run_agent(history, project_state)
            elapsed = time.time() - start
            print(f"  Time: [{elapsed:.2f}s | Token: {tokens} tokens]\n")

        except KeyboardInterrupt:
            print("\n  Agent stopped.")
            break
        except Exception as e:
            print(f"\n  [error] {e}\n")