"""
state.py
────────
All state management for the Home Configuration Agent.
No full state injection — LLM fetches only what it needs.
Conversation history acts as the cache.

Covers: Floor, Room, Driver, Load operations
"""

import json
import os

HERE       = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "project_state.json")


# ── 1. Load and Save ─────────────────────────────────────────


def get_state_summary(state: dict) -> str:
    floors  = state.get("floors", [])
    rooms   = state.get("rooms", [])
    drivers = state.get("installed_drivers", [])
    loads   = state.get("loads", [])
    macros  = state.get("macros", [])

    if floors:
        max_num      = max(f["floor_number"] for f in floors)
        floor_detail = ", ".join(f"{f['floor_name']} [{f['floor_number']}]" for f in floors)
        floor_str    = f"{len(floors)} floors (max_number={max_num}: {floor_detail})"
    else:
        floor_str = "0 floors"

    return (
        f"{floor_str} | "
        f"{len(rooms)} rooms | "
        f"{len(drivers)} drivers installed | "
        f"{len(loads)} loads | "
        f"{len(macros)} macros"
    )

def init_state() -> dict:
    return {
        "floors":             [],
        "rooms":              [],
        "installed_drivers":  [],
        "loads":              [],
        "macros":             [],
    }


def load_state(path: str) -> dict:
    if not os.path.exists(path):
        return init_state()
    try:
        with open(path) as f:
            data = f.read().strip()
            if not data:
                return init_state()
            return json.loads(data)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [warn] Could not read state file ({e}). Starting fresh.")
        return init_state()


def save_state(state: dict, path: str) -> None:
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def load_catalog(path: str) -> dict:
    if not os.path.exists(path):
        print(f"  [warn] Catalog not found at {path}.")
        return {"drivers": []}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [warn] Could not read catalog ({e}).")
        return {"drivers": []}


# ── 2. ID Generator ───────────────────────────────────────────

def _next_id(items: list, prefix: str) -> str:
    max_num = 0
    field   = f"{prefix}_id"
    for item in items:
        existing = item.get(field, "")
        if existing.startswith(prefix):
            try:
                num = int(existing[len(prefix):])
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    return f"{prefix}{max_num + 1}"


# ── 3. Floor Helpers ──────────────────────────────────────────

def _find_floor(state: dict, floor_name, floor_number):
    floors = state.get("floors", [])
    if floor_name is not None and floor_number is not None:
        by_name   = next((f for f in floors if f["floor_name"].lower() == floor_name.lower()), None)
        by_number = next((f for f in floors if f["floor_number"] == floor_number), None)
        if by_name is None and by_number is None:
            return None
        if by_name is None or by_number is None:
            return "CONFLICT"
        if by_name["floor_id"] != by_number["floor_id"]:
            return "CONFLICT"
        return by_name
    if floor_name is not None:
        return next((f for f in floors if f["floor_name"].lower() == floor_name.lower()), None)
    if floor_number is not None:
        return next((f for f in floors if f["floor_number"] == floor_number), None)
    return None


def _auto_fill_floor(state: dict, floor_name, floor_number):
    floors = state.get("floors", [])
    if floor_number is None:
        floor_number = 0 if not floors else max(f["floor_number"] for f in floors) + 1
    if floor_name is None:
        floor_name = "Ground Floor" if floor_number == 0 else f"Floor {floor_number + 1}"
    return floor_name, floor_number


# ── 4. Room Helpers ───────────────────────────────────────────

def _find_rooms(state: dict, room_name, floor_name, floor_number) -> list:
    rooms          = state.get("rooms", [])
    floor_id_filter = None
    if floor_name is not None or floor_number is not None:
        floor = _find_floor(state, floor_name, floor_number)
        if floor is None or floor == "CONFLICT":
            return []
        floor_id_filter = floor["floor_id"]
    results = []
    for r in rooms:
        name_match  = room_name is None or r["room_name"].lower() == room_name.lower()
        floor_match = floor_id_filter is None or r["floor_id"] == floor_id_filter
        if name_match and floor_match:
            results.append(r)
    return results


def _floor_name_by_id(state: dict, floor_id) -> str:
    for f in state.get("floors", []):
        if f["floor_id"] == floor_id:
            return f["floor_name"]
    return "Unassigned"


# ── 5. Driver Helpers ─────────────────────────────────────────

def _find_driver(state: dict, install_id: str):
    return next(
        (d for d in state.get("installed_drivers", []) if d["install_id"] == install_id),
        None,
    )


def get_next_ip(state: dict) -> str:
    """Return the next unused IP address starting from 192.168.1.100."""
    used = {
        d.get("config", {}).get("ip_address")
        for d in state.get("installed_drivers", [])
        if d.get("config", {}).get("ip_address")
    }
    base = 100
    while f"192.168.1.{base}" in used:
        base += 1
    return f"192.168.1.{base}"


# ── 6. Load Helpers ───────────────────────────────────────────

def _find_loads(state: dict, load_name: str, install_id=None) -> list:
    loads = state.get("loads", [])
    results = []
    for ld in loads:
        name_match    = ld["load_name"].lower() == load_name.lower()
        gateway_match = install_id is None or ld.get("install_id") == install_id
        if name_match and gateway_match:
            results.append(ld)
    return results


def _next_group_address(state: dict) -> str:
    """Return the next unused KNX group address starting from 1/1/1."""
    used = {
        ld.get("config", {}).get("group_address")
        for ld in state.get("loads", [])
        if ld.get("config", {}).get("group_address")
    }
    a, b, c = 1, 1, 1
    while f"{a}/{b}/{c}" in used:
        c += 1
        if c > 255:
            c = 1
            b += 1
        if b > 255:
            b = 1
            a += 1
    return f"{a}/{b}/{c}"


def _next_unit_id(state: dict, install_id: str) -> int:
    """Return the next unused unit_id for a specific gateway."""
    used = {
        ld.get("config", {}).get("unit_id")
        for ld in state.get("loads", [])
        if ld.get("install_id") == install_id and ld.get("config", {}).get("unit_id") is not None
    }
    uid = 1
    while uid in used:
        uid += 1
    return uid


def _gateway_name_by_id(state: dict, install_id) -> str:
    for d in state.get("installed_drivers", []):
        if d["install_id"] == install_id:
            return d["driver_name"]
    return "Unassigned"


# ── 7. Targeted Reads ─────────────────────────────────────────

def get_floor_from_state(state: dict, floor_name=None, floor_number=None) -> dict:
    result = _find_floor(state, floor_name, floor_number)
    if result == "CONFLICT":
        return {"found": False, "error": f"Floor name '{floor_name}' and floor number {floor_number} refer to different floors."}
    if result is None:
        identifier = f"name '{floor_name}'" if floor_name is not None else f"number {floor_number}"
        return {"found": False, "error": f"No floor found with {identifier}."}
    return {"found": True, "floor": result}


def get_all_floors_from_state(state: dict) -> dict:
    floors = state.get("floors", [])
    return {"total": len(floors), "floors": floors}


def get_room_from_state(state: dict, room_name=None, floor_name=None, floor_number=None) -> dict:
    matches = _find_rooms(state, room_name, floor_name, floor_number)
    if not matches:
        if room_name and (floor_name or floor_number is not None):
            floor_id = f"name '{floor_name}'" if floor_name else f"number {floor_number}"
            return {"found": False, "error": f"No room '{room_name}' found on floor {floor_id}."}
        if room_name:
            return {"found": False, "error": f"No room named '{room_name}' found."}
        return {"found": False, "error": "No rooms found matching the given criteria."}
    if len(matches) == 1:
        room        = matches[0]
        floor_label = _floor_name_by_id(state, room["floor_id"])
        return {"found": True, "room": room, "floor_name": floor_label}
    options = [{"room": r, "floor_name": _floor_name_by_id(state, r["floor_id"])} for r in matches]
    return {
        "found": False, "ambiguous": True,
        "message": f"Multiple rooms named '{room_name}' exist. Please specify the floor.",
        "options": options,
    }


def get_all_rooms_from_state(state: dict) -> dict:
    rooms     = state.get("rooms", [])
    floors    = state.get("floors", [])
    floor_map = {f["floor_id"]: f["floor_name"] for f in floors}
    groups    = {}
    unassigned = []
    for r in rooms:
        fid = r.get("floor_id")
        if fid is None or fid not in floor_map:
            unassigned.append(r)
        else:
            groups.setdefault(floor_map[fid], []).append(r)
    result = {"total": len(rooms), "by_floor": dict(groups)}
    if unassigned:
        result["by_floor"]["Unassigned"] = unassigned
    return result


def get_marketplace_drivers(catalog: dict, search_query: str = None) -> dict:
    drivers = catalog.get("drivers", [])
    if search_query:
        words = search_query.lower().split()
        drivers = [
            d for d in drivers
            if all(
                word in (
                    d["name"] + " " + d["manufacturer"] + " " + d.get("description", "")
                ).lower()
                for word in words
            )
        ]
    return {"total": len(drivers), "drivers": drivers}


def get_driver_config_from_catalog(catalog: dict, driver_id: str) -> dict:
    driver = next((d for d in catalog.get("drivers", []) if d["driver_id"] == driver_id), None)
    if driver is None:
        return {"found": False, "error": f"Driver '{driver_id}' not found in marketplace."}
    return {"found": True, "driver": driver}


def get_installed_drivers_from_state(state: dict, search_query: str = None) -> dict:
    drivers = state.get("installed_drivers", [])
    if search_query:
        q = search_query.lower()
        drivers = [d for d in drivers if q in d["driver_name"].lower()]
    return {"total": len(drivers), "drivers": drivers}


def get_loads_from_state(state: dict, install_id: str = None) -> dict:
    loads = state.get("loads", [])
    drivers = state.get("installed_drivers", [])
    gateway_map = {d["install_id"]: d["driver_name"] for d in drivers}

    if install_id is not None:
        loads = [ld for ld in loads if ld.get("install_id") == install_id]
        return {"total": len(loads), "loads": loads}

    # Group by gateway name with unassigned at bottom
    groups     = {}
    unassigned = []
    for ld in loads:
        gid = ld.get("install_id")
        if gid is None or gid not in gateway_map:
            unassigned.append(ld)
        else:
            groups.setdefault(gateway_map[gid], []).append(ld)
    result = {"total": len(loads), "by_gateway": dict(groups)}
    if unassigned:
        result["by_gateway"]["Unassigned"] = unassigned
    return result


# ── Macro helpers ─────────────────────────────────────────────

def _find_macro(state: dict, macro_name: str):
    """Find a macro by name (case-insensitive). Returns macro dict or None."""
    return next(
        (m for m in state.get("macros", []) if m["macro_name"].lower() == macro_name.lower()),
        None,
    )


def _device_exists(state: dict, device_id: str) -> bool:
    """Check if a device_id exists in installed drivers or loads."""
    for d in state.get("installed_drivers", []):
        if d["install_id"] == device_id:
            return True
    for ld in state.get("loads", []):
        if ld["load_id"] == device_id:
            return True
    return False


def _auto_fill_macro_name(state: dict) -> str:
    """Auto-assign macro name as 'Macro N' where N is total macros + 1."""
    count = len(state.get("macros", []))
    return f"Macro {count + 1}"


def get_all_macros_from_state(state: dict) -> dict:
    """Return all macros. Called when LLM selects read_all_macros."""
    macros = state.get("macros", [])
    return {"total": len(macros), "macros": macros}


# ── 8. Validation ─────────────────────────────────────────────

def validate_tool_call(state: dict, tool_name: str, params: dict, catalog: dict = None) -> str | None:

    # ── Floor validation ──────────────────────────────────────

    if tool_name == "create_floor":
        floor_name, floor_number = _auto_fill_floor(
            state, params.get("floor_name"), params.get("floor_number")
        )
        for f in state.get("floors", []):
            if f["floor_name"].lower() == floor_name.lower():
                return f"Floor name '{floor_name}' already exists."
            if f["floor_number"] == floor_number:
                return f"Floor number {floor_number} is already used by '{f['floor_name']}'."
        return None

    if tool_name == "update_floor":
        floor_name       = params.get("floor_name")
        floor_number     = params.get("floor_number")
        new_floor_name   = params.get("new_floor_name")
        new_floor_number = params.get("new_floor_number")
        if floor_name is None and floor_number is None:
            return "Provide floor_name or floor_number to identify the floor."
        if new_floor_name is None and new_floor_number is None:
            return "Provide new_floor_name or new_floor_number."
        target = _find_floor(state, floor_name, floor_number)
        if target == "CONFLICT":
            return f"Floor name '{floor_name}' and floor number {floor_number} refer to different floors."
        if target is None:
            return f"No floor found with {'name' if floor_name else 'number'} '{floor_name or floor_number}'."
        for f in state.get("floors", []):
            if f["floor_id"] == target["floor_id"]:
                continue
            if new_floor_name and f["floor_name"].lower() == new_floor_name.lower():
                return f"Floor name '{new_floor_name}' already exists."
            if new_floor_number is not None and f["floor_number"] == new_floor_number:
                return f"Floor number {new_floor_number} is already used by '{f['floor_name']}'."
        return None

    if tool_name == "delete_floor":
        if params.get("delete_all"):
            return None
        floor_name   = params.get("floor_name")
        floor_number = params.get("floor_number")
        if floor_name is None and floor_number is None:
            return "Provide floor_name or floor_number to identify the floor."
        target = _find_floor(state, floor_name, floor_number)
        if target == "CONFLICT":
            return f"Floor name '{floor_name}' and floor number {floor_number} refer to different floors."
        if target is None:
            return f"No floor found with {'name' if floor_name else 'number'} '{floor_name or floor_number}'."
        return None

    # ── Room validation ───────────────────────────────────────

    if tool_name == "create_room":
        room_name    = params.get("room_name")
        floor_name   = params.get("floor_name")
        floor_number = params.get("floor_number")
        if not room_name:
            return "room_name is required."
        if floor_name is not None or floor_number is not None:
            floor = _find_floor(state, floor_name, floor_number)
            if floor == "CONFLICT":
                return f"Floor name '{floor_name}' and floor number {floor_number} refer to different floors."
            if floor is None:
                return f"No floor found with {'name' if floor_name else 'number'} '{floor_name or floor_number}'."
            for r in state.get("rooms", []):
                if r["floor_id"] == floor["floor_id"] and r["room_name"].lower() == room_name.lower():
                    return f"Room '{room_name}' already exists on '{floor['floor_name']}'."
        else:
            floors = state.get("floors", [])
            if len(floors) == 0:
                return "NO_FLOOR_EXISTS"
            if len(floors) > 1:
                return "FLOOR_AMBIGUOUS"
            floor = floors[0]
            for r in state.get("rooms", []):
                if r["floor_id"] == floor["floor_id"] and r["room_name"].lower() == room_name.lower():
                    return f"Room '{room_name}' already exists on '{floor['floor_name']}'."
        return None

    if tool_name == "update_room":
        room_name    = params.get("room_name")
        floor_name   = params.get("floor_name")
        floor_number = params.get("floor_number")
        new_room_name    = params.get("new_room_name")
        new_floor_name   = params.get("new_floor_name")
        new_floor_number = params.get("new_floor_number")
        if room_name is None and floor_name is None and floor_number is None:
            return "Provide room_name or floor identifier."
        if new_room_name is None and new_floor_name is None and new_floor_number is None:
            return "Provide new_room_name or new floor identifier."
        matches = _find_rooms(state, room_name, floor_name, floor_number)
        if not matches:
            return f"No room named '{room_name}' found."
        if len(matches) > 1:
            return f"Multiple rooms named '{room_name}' exist on different floors. Please also provide the floor name or number."
        target    = matches[0]
        new_floor = None
        if new_floor_name is not None or new_floor_number is not None:
            new_floor = _find_floor(state, new_floor_name, new_floor_number)
            if new_floor == "CONFLICT":
                return f"Floor name '{new_floor_name}' and floor number {new_floor_number} refer to different floors."
            if new_floor is None:
                return f"No floor found with {'name' if new_floor_name else 'number'} '{new_floor_name or new_floor_number}'."
        dest_floor_id = new_floor["floor_id"] if new_floor else target["floor_id"]
        check_name    = new_room_name if new_room_name is not None else target["room_name"]
        for r in state.get("rooms", []):
            if r["room_id"] == target["room_id"]:
                continue
            if r["floor_id"] == dest_floor_id and r["room_name"].lower() == check_name.lower():
                return f"Room '{check_name}' already exists on '{_floor_name_by_id(state, dest_floor_id)}'."
        return None

    if tool_name == "delete_room":
        if params.get("delete_all"):
            return None
        room_name    = params.get("room_name")
        floor_name   = params.get("floor_name")
        floor_number = params.get("floor_number")
        if room_name is None and floor_name is None and floor_number is None:
            return "Provide room_name, floor identifier, or delete_all."
        if room_name is None and (floor_name is not None or floor_number is not None):
            floor = _find_floor(state, floor_name, floor_number)
            if floor == "CONFLICT":
                return f"Floor name '{floor_name}' and floor number {floor_number} refer to different floors."
            if floor is None:
                return f"No floor found with {'name' if floor_name else 'number'} '{floor_name or floor_number}'."
            return None
        matches = _find_rooms(state, room_name, floor_name, floor_number)
        if not matches:
            return f"No room named '{room_name}' found."
        if len(matches) > 1 and floor_name is None and floor_number is None:
            return f"Multiple rooms named '{room_name}' exist on different floors. Please also provide the floor name or number."
        return None

    # ── Driver validation ─────────────────────────────────────

    if tool_name == "install_driver":
        driver_id = params.get("driver_id")
        config    = params.get("config", {})
        drivers   = catalog.get("drivers", []) if catalog else []
        driver    = next((d for d in drivers if d["driver_id"] == driver_id), None)
        if driver is None:
            return f"Driver '{driver_id}' not found in marketplace."
        for field in driver.get("config_schema", []):
            if field.get("required") and field["field"] not in config:
                if field["field"] == "room":
                    return f"ROOM_REQUIRED:{driver['name']}"
                return f"Missing required config field: '{field['label']}'."
        ip = config.get("ip_address")
        if ip:
            for d in state.get("installed_drivers", []):
                if d.get("config", {}).get("ip_address") == ip:
                    return f"IP address '{ip}' is already used by '{d['driver_name']}'."
        return None

    if tool_name == "update_driver":
        install_id = params.get("install_id")
        new_config = params.get("new_config")
        if not install_id:
            return "Provide install_id to identify the driver."
        if not new_config:
            return "Provide new_config with the fields to update."
        driver = _find_driver(state, install_id)
        if driver is None:
            return f"No installed driver found with install_id '{install_id}'."
        new_ip = new_config.get("ip_address")
        if new_ip:
            for d in state.get("installed_drivers", []):
                if d["install_id"] != install_id and d.get("config", {}).get("ip_address") == new_ip:
                    return f"IP address '{new_ip}' is already used by '{d['driver_name']}'."
        return None

    if tool_name == "uninstall_driver":
        install_id = params.get("install_id")
        if not install_id:
            return "Provide install_id to uninstall a driver."
        if _find_driver(state, install_id) is None:
            return f"No installed driver found with install_id '{install_id}'."
        return None

    # ── Load validation ───────────────────────────────────────

    if tool_name == "add_load":
        install_id = params.get("install_id")
        load_type  = params.get("load_type")
        load_name  = params.get("load_name", "")
        config     = params.get("config", {})
        if not install_id:
            return "Provide install_id to identify the gateway."
        gateway = _find_driver(state, install_id)
        if gateway is None:
            return f"No installed driver found with install_id '{install_id}'."
        if gateway.get("type") != "gateway":
            return f"'{gateway['driver_name']}' is not a gateway driver."
        driver_record = None
        if catalog:
            driver_record = next(
                (d for d in catalog.get("drivers", []) if d["driver_id"] == gateway["driver_id"]),
                None,
            )
        supported = [lt["type"] for lt in (driver_record or {}).get("load_types", [])]
        if load_type not in supported:
            return f"Load type '{load_type}' not supported by '{gateway['driver_name']}'. Supported: {', '.join(supported)}."
        lt_record = next(
            (lt for lt in (driver_record or {}).get("load_types", []) if lt["type"] == load_type),
            None,
        )
        if lt_record:
            for field in lt_record.get("config_schema", []):
                if field.get("required") and field["field"] not in config:
                    if field["field"] == "room":
                        return f"ROOM_REQUIRED:{load_type}"
                    # group_address and unit_id are auto-filled — not an error
        existing_loads = [ld for ld in state.get("loads", []) if ld.get("install_id") == install_id]
        if any(ld["load_name"].lower() == load_name.lower() for ld in existing_loads):
            return f"Load name '{load_name}' already exists on '{gateway['driver_name']}'."
        return None

    if tool_name == "update_load":
        load_name  = params.get("load_name")
        install_id = params.get("install_id")
        new_load_name = params.get("new_load_name")
        new_config    = params.get("new_config")
        if not load_name:
            return "Provide load_name to identify the load."
        if new_load_name is None and new_config is None:
            return "Provide new_load_name or new_config."
        matches = _find_loads(state, load_name, install_id)
        if not matches:
            return f"No load named '{load_name}' found."
        if len(matches) > 1:
            return "GATEWAY_AMBIGUOUS"
        target = matches[0]
        if new_load_name is not None:
            gw_loads = [ld for ld in state.get("loads", []) if ld.get("install_id") == target.get("install_id")]
            for ld in gw_loads:
                if ld["load_id"] != target["load_id"] and ld["load_name"].lower() == new_load_name.lower():
                    return f"Load name '{new_load_name}' already exists on '{_gateway_name_by_id(state, target.get('install_id'))}'."
        return None

    if tool_name == "remove_load":
        load_name  = params.get("load_name")
        install_id = params.get("install_id")
        if not load_name:
            return "Provide load_name to identify the load."
        matches = _find_loads(state, load_name, install_id)
        if not matches:
            return f"No load named '{load_name}' found."
        if len(matches) > 1:
            return "GATEWAY_AMBIGUOUS"
        return None

    # ── Macro validation ──────────────────────────────────────

    if tool_name == "create_macro":
        macro_name = params.get("macro_name")
        actions    = params.get("actions", [])
        if not actions:
            return "Provide at least one action."
        if macro_name and _find_macro(state, macro_name):
            return f"Macro name '{macro_name}' already exists."
        for i, act in enumerate(actions, 1):
            if not _device_exists(state, act.get("device_id", "")):
                return f"Action {i}: device '{act.get('device_id')}' not found. Please install the device first."
        return None

    if tool_name == "update_macro":
        macro_name     = params.get("macro_name")
        new_macro_name = params.get("new_macro_name")
        add_actions    = params.get("add_actions")
        remove_actions = params.get("remove_actions")
        edit_actions   = params.get("edit_actions")
        if not macro_name:
            return "Provide macro_name to identify the macro."
        if new_macro_name is None and not add_actions and not remove_actions and not edit_actions:
            return "Provide at least one change."
        target = _find_macro(state, macro_name)
        if target is None:
            return f"No macro named '{macro_name}' found."
        if new_macro_name:
            existing = _find_macro(state, new_macro_name)
            if existing and existing["macro_id"] != target["macro_id"]:
                return f"Macro name '{new_macro_name}' already exists."
        if add_actions:
            for i, act in enumerate(add_actions, 1):
                if not _device_exists(state, act.get("device_id", "")):
                    return f"add_actions[{i}]: device '{act.get('device_id')}' not found."
        existing_actions = target.get("actions", [])
        if remove_actions:
            for act in remove_actions:
                if not any(
                    a.get("device_id") == act.get("device_id") and a.get("action") == act.get("action")
                    for a in existing_actions
                ):
                    return (
                        f"Action device_id='{act.get('device_id')}' action='{act.get('action')}' "
                        f"not found in macro '{macro_name}'."
                    )
        if edit_actions:
            for entry in edit_actions:
                if not any(
                    a.get("device_id") == entry.get("device_id") and a.get("action") == entry.get("action")
                    for a in existing_actions
                ):
                    return (
                        f"Action device_id='{entry.get('device_id')}' action='{entry.get('action')}' "
                        f"not found in macro '{macro_name}'."
                    )
        return None

    if tool_name == "delete_macro":
        if params.get("delete_all"):
            return None
        macro_name = params.get("macro_name")
        if not macro_name:
            return "Provide macro_name or set delete_all to true."
        if _find_macro(state, macro_name) is None:
            return f"No macro named '{macro_name}' found."
        return None

    return None


# ── 9. State Mutation ─────────────────────────────────────────

def update_state(state: dict, tool_name: str, params: dict, catalog: dict = None) -> None:

    # ── Floor mutations ───────────────────────────────────────

    if tool_name == "create_floor":
        floor_name, floor_number = _auto_fill_floor(
            state, params.get("floor_name"), params.get("floor_number")
        )
        floors = state.setdefault("floors", [])
        floors.append({
            "floor_id":     _next_id(floors, "floor"),
            "floor_name":   floor_name,
            "floor_number": floor_number,
        })

    if tool_name == "update_floor":
        target = _find_floor(state, params.get("floor_name"), params.get("floor_number"))
        if target and target != "CONFLICT":
            if params.get("new_floor_name") is not None:
                target["floor_name"] = params["new_floor_name"]
            if params.get("new_floor_number") is not None:
                target["floor_number"] = params["new_floor_number"]

    if tool_name == "delete_floor":
        if params.get("delete_all"):
            for r in state.get("rooms", []):
                r["floor_id"] = None
            state["floors"].clear()
        else:
            target = _find_floor(state, params.get("floor_name"), params.get("floor_number"))
            if target and target != "CONFLICT":
                deleted_id = target["floor_id"]
                state["floors"].remove(target)
                for r in state.get("rooms", []):
                    if r["floor_id"] == deleted_id:
                        r["floor_id"] = None

    # ── Room mutations ────────────────────────────────────────

    if tool_name == "create_room":
        floor_name   = params.get("floor_name")
        floor_number = params.get("floor_number")
        floors       = state.get("floors", [])
        if floor_name is not None or floor_number is not None:
            floor = _find_floor(state, floor_name, floor_number)
        elif len(floors) == 1:
            floor = floors[0]
        else:
            floor = None
        rooms = state.setdefault("rooms", [])
        rooms.append({
            "room_id":   _next_id(rooms, "room"),
            "room_name": params["room_name"],
            "floor_id":  floor["floor_id"] if floor else None,
        })

    if tool_name == "update_room":
        matches = _find_rooms(state, params.get("room_name"), params.get("floor_name"), params.get("floor_number"))
        if matches:
            target = matches[0]
            if params.get("new_room_name") is not None:
                target["room_name"] = params["new_room_name"]
            if params.get("new_floor_name") is not None or params.get("new_floor_number") is not None:
                new_floor = _find_floor(state, params.get("new_floor_name"), params.get("new_floor_number"))
                if new_floor and new_floor != "CONFLICT":
                    target["floor_id"] = new_floor["floor_id"]

    if tool_name == "delete_room":
        if params.get("delete_all"):
            state["rooms"].clear()
            return
        room_name    = params.get("room_name")
        floor_name   = params.get("floor_name")
        floor_number = params.get("floor_number")
        if room_name is None and (floor_name is not None or floor_number is not None):
            floor = _find_floor(state, floor_name, floor_number)
            if floor and floor != "CONFLICT":
                state["rooms"] = [r for r in state.get("rooms", []) if r["floor_id"] != floor["floor_id"]]
            return
        matches   = _find_rooms(state, room_name, floor_name, floor_number)
        match_ids = {r["room_id"] for r in matches}
        state["rooms"] = [r for r in state.get("rooms", []) if r["room_id"] not in match_ids]

    # ── Driver mutations ──────────────────────────────────────

    if tool_name == "install_driver":
        installed  = state.setdefault("installed_drivers", [])
        install_id = _next_id(installed, "install")
        driver_id  = params["driver_id"]
        driver_name = driver_id
        driver_type = "direct"
        if catalog:
            driver = next((d for d in catalog.get("drivers", []) if d["driver_id"] == driver_id), None)
            if driver:
                driver_name = driver["name"]
                driver_type = driver["type"]
                # Apply catalog defaults for optional fields
                config = params.get("config", {})
                for field in driver.get("config_schema", []):
                    if not field.get("required") and field["field"] not in config and "default" in field:
                        config[field["field"]] = field["default"]
                params["config"] = config
        installed.append({
            "install_id":  install_id,
            "driver_id":   driver_id,
            "driver_name": driver_name,
            "type":        driver_type,
            "config":      params.get("config", {}),
        })

    if tool_name == "update_driver":
        target = _find_driver(state, params["install_id"])
        if target:
            target["config"].update(params["new_config"])

    if tool_name == "uninstall_driver":
        install_id = params["install_id"]
        state["installed_drivers"] = [
            d for d in state.get("installed_drivers", [])
            if d["install_id"] != install_id
        ]
        # Loads become unassigned
        for ld in state.get("loads", []):
            if ld.get("install_id") == install_id:
                ld["install_id"] = None

    # ── Load mutations ────────────────────────────────────────

    if tool_name == "add_load":
        install_id = params["install_id"]
        load_type  = params["load_type"]
        config     = params.get("config", {})

        # Find the load type schema from catalog to know which fields exist
        gateway     = _find_driver(state, install_id)
        lt_record   = None
        if catalog and gateway:
            driver_record = next(
                (d for d in catalog.get("drivers", []) if d["driver_id"] == gateway["driver_id"]),
                None,
            )
            lt_record = next(
                (lt for lt in (driver_record or {}).get("load_types", []) if lt["type"] == load_type),
                None,
            )

        schema_fields = {f["field"] for f in (lt_record or {}).get("config_schema", [])}

        # Auto-fill only fields that exist in this load type's schema
        if "group_address" in schema_fields and "group_address" not in config:
            config["group_address"] = _next_group_address(state)

        if "unit_id" in schema_fields and "unit_id" not in config:
            config["unit_id"] = _next_unit_id(state, install_id)

        # Strip any LLM-invented fields not in schema (keep room since LLM fills it)
        if schema_fields:
            config = {k: v for k, v in config.items() if k in schema_fields}

        loads = state.setdefault("loads", [])
        loads.append({
            "load_id":    _next_id(loads, "load"),
            "install_id": install_id,
            "load_type":  load_type,
            "load_name":  params["load_name"],
            "config":     config,
        })

    if tool_name == "update_load":
        matches = _find_loads(state, params["load_name"], params.get("install_id"))
        if matches:
            target = matches[0]
            if params.get("new_load_name") is not None:
                target["load_name"] = params["new_load_name"]
            if params.get("new_config"):
                target["config"].update(params["new_config"])

    if tool_name == "remove_load":
        matches   = _find_loads(state, params["load_name"], params.get("install_id"))
        match_ids = {ld["load_id"] for ld in matches}
        state["loads"] = [ld for ld in state.get("loads", []) if ld["load_id"] not in match_ids]

    # ── Macro mutations ───────────────────────────────────────

    if tool_name == "create_macro":
        macro_name = params.get("macro_name")
        if not macro_name:
            macro_name = _auto_fill_macro_name(state)
        macros = state.setdefault("macros", [])
        macros.append({
            "macro_id":   _next_id(macros, "macro"),
            "macro_name": macro_name,
            "actions":    params.get("actions", []),
        })

    if tool_name == "update_macro":
        target = _find_macro(state, params["macro_name"])
        if target is None:
            return

        if params.get("new_macro_name"):
            target["macro_name"] = params["new_macro_name"]

        actions = target["actions"]

        # Edit actions first
        for entry in (params.get("edit_actions") or []):
            for act in actions:
                if act.get("device_id") == entry["device_id"] and act.get("action") == entry["action"]:
                    if entry.get("new_action") is not None:
                        act["action"] = entry["new_action"]
                    if entry.get("new_room") is not None:
                        act["room"] = entry["new_room"]
                    if entry.get("new_value") is not None:
                        act["value"] = entry["new_value"]
                    break

        # Remove actions
        for rem in (params.get("remove_actions") or []):
            actions[:] = [
                a for a in actions
                if not (a.get("device_id") == rem["device_id"] and a.get("action") == rem["action"])
            ]

        # Add actions
        for add in (params.get("add_actions") or []):
            actions.append(add)

    if tool_name == "delete_macro":
        if params.get("delete_all"):
            state["macros"].clear()
        else:
            macro_name = params["macro_name"]
            state["macros"] = [
                m for m in state.get("macros", [])
                if m["macro_name"].lower() != macro_name.lower()
            ]