"""
schema.py
─────────
Tool schemas for the Home Configuration Agent.
Pure data — no logic, no imports.

Floor tools  (5): get_floor, create_floor, read_all_floors, update_floor, delete_floor
Room tools   (5): get_room, create_room, read_all_rooms, update_room, delete_room
Driver tools (6): list_marketplace_drivers, get_driver_config, install_driver,
                  list_installed_drivers, update_driver, uninstall_driver
Load tools   (4): add_load, list_loads, update_load, remove_load
"""


def _s(description):
    return {"type": "string",  "description": description}

def _i(description):
    return {"type": "integer", "description": description}

def _b(description):
    return {"type": "boolean", "description": description}

def _obj(description):
    return {"type": "object",  "description": description, "additionalProperties": True}

def _action_arr(description):
    return {
        "type": "array",
        "description": description,
        "items": {
            "type": "object",
            "properties": {
                "device_id": _s("install_id (direct driver) or load_id (gateway load)."),
                "action":    _s("Action verb: turn_on, turn_off, set_temperature, set_brightness, open, close, etc."),
                "room":      _s("Room name — optional context."),
                "value":     _s("Value for parametric actions e.g. '20' for temperature, '80' for brightness."),
            },
            "required": ["device_id", "action"],
            "additionalProperties": False,
        },
        "minItems": 1,
    }

def _edit_action_arr(description):
    return {
        "type": "array",
        "description": description,
        "items": {
            "type": "object",
            "properties": {
                "device_id":  _s("Current device_id — identifies the action to edit."),
                "action":     _s("Current action verb — identifies the action to edit."),
                "new_action": _s("New action verb."),
                "new_room":   _s("New room name."),
                "new_value":  _s("New value."),
            },
            "required": ["device_id", "action"],
            "additionalProperties": False,
        },
        "minItems": 1,
    }

def _remove_action_arr(description):
    return {
        "type": "array",
        "description": description,
        "items": {
            "type": "object",
            "properties": {
                "device_id": _s("device_id of the action to remove."),
                "action":    _s("Action verb of the action to remove."),
            },
            "required": ["device_id", "action"],
            "additionalProperties": False,
        },
        "minItems": 1,
    }

def _params(properties, required=None):
    return {
        "type": "object",
        "properties": properties,
        "required": required if required is not None else [],
        "additionalProperties": False,
    }

def _tool(name, description, parameters=None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": (
                {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                }
                if parameters is None
                else parameters
            ),
        },
    }


# ── Floor tools ───────────────────────────────────────────────

TOOLS = [

    _tool(
        "get_floor",
        (
            "Fetch a single floor by name or number to verify it exists. "
            "Call ONLY when floor is not already in conversation history. "
            "Never call to list floors — use read_all_floors for that."
        ),
        _params({
            "floor_name":   _s("Name of the floor to fetch."),
            "floor_number": _i("Number of the floor to fetch."),
        }),
    ),

    _tool(
        "create_floor",
        (
            "Create a new floor. floor_name and floor_number are both optional — "
            "auto-assign floor_number from 0 upward using the max_number in the system "
            "'Current state' header, floor_name as 'Ground Floor' when floor_number is 0, "
            "otherwise 'Floor N' where N is floor_number plus 1. "
            "For batch creation compute ALL floor numbers before emitting any call. "
            "Never ask the engineer for these values."
        ),
        _params({
            "floor_name":   _s("Floor name. Auto-filled if not provided."),
            "floor_number": _i("Floor level. Auto-assigned if not provided."),
        }),
    ),

    _tool(
        "read_all_floors",
        (
            "List all floors. Call when engineer explicitly says "
            "show, list, display, or read floors. "
            "Also call internally when floor list is needed for auto-fill "
            "or context resolution and it is not in conversation history."
        ),
    ),

    _tool(
        "update_floor",
        (
            "Rename a floor or change its number. "
            "Identify using floor_name or floor_number or both — they must refer to the same floor. "
            "Provide new_floor_name or new_floor_number or both as new values."
        ),
        _params({
            "floor_name":       _s("Current floor name — identifier."),
            "floor_number":     _i("Current floor number — identifier."),
            "new_floor_name":   _s("New name to assign."),
            "new_floor_number": _i("New number to assign."),
        }),
    ),

    _tool(
        "delete_floor",
        (
            "Delete one floor or all floors. "
            "Single: provide floor_name or floor_number or both — must refer to the same floor. "
            "All: set delete_all to true. "
            "Deleting a floor does NOT delete its rooms — they become unassigned."
        ),
        _params({
            "floor_name":   _s("Floor to delete by name."),
            "floor_number": _i("Floor to delete by number."),
            "delete_all":   _b("True to delete all floors."),
        }),
    ),


    # ── Room tools ────────────────────────────────────────────

    _tool(
        "get_room",
        (
            "Fetch a single room to verify it exists. "
            "Call ONLY when room is not already in conversation history. "
            "Provide floor_name or floor_number to narrow down when same name "
            "exists on multiple floors. Never call to list rooms."
        ),
        _params({
            "room_name":    _s("Name of the room to fetch."),
            "floor_name":   _s("Floor name to narrow the search."),
            "floor_number": _i("Floor number to narrow the search."),
        }),
    ),

    _tool(
        "create_room",
        (
            "Create a room on a floor. room_name is required. "
            "If engineer provides names use them. "
            "If engineer requests N rooms without names auto-fill as "
            "'Room 1', 'Room 2' etc. counting from existing rooms on that floor plus 1. "
            "If no floor given and one floor exists use it automatically. "
            "If no floor given and multiple floors exist ask which floor. "
            "If floor does not exist emit create_floor before create_room in the same response. "
            "Duplicate names allowed on different floors."
        ),
        _params(
            {
                "room_name":    _s("Room name."),
                "floor_name":   _s("Floor name where room will be created."),
                "floor_number": _i("Floor number where room will be created."),
            },
            required=["room_name"],
        ),
    ),

    _tool(
        "read_all_rooms",
        (
            "List all rooms grouped by floor. "
            "Unassigned rooms appear under 'Unassigned'. "
            "Call when engineer explicitly says show, list, display, or read rooms. "
            "Also call internally when room list is needed for auto-fill "
            "or context resolution and it is not in conversation history."
        ),
    ),

    _tool(
        "update_room",
        (
            "Rename a room or reassign it to a different floor. "
            "Identify using room_name and optionally floor_name or floor_number. "
            "If room_name exists on multiple floors and no floor given ask which floor. "
            "Provide new_room_name to rename, new_floor_name or new_floor_number to reassign."
        ),
        _params({
            "room_name":        _s("Current room name — identifier."),
            "floor_name":       _s("Current floor name — narrows identification."),
            "floor_number":     _i("Current floor number — narrows identification."),
            "new_room_name":    _s("New room name."),
            "new_floor_name":   _s("Reassign to this floor by name."),
            "new_floor_number": _i("Reassign to this floor by number."),
        }),
    ),

    _tool(
        "delete_room",
        (
            "Delete rooms. "
            "Single room: room_name plus optional floor identifier. "
            "All rooms on a floor: floor_name or floor_number alone, no room_name. "
            "All rooms: delete_all true. "
            "If room_name exists on multiple floors and no floor given ask which floor."
        ),
        _params({
            "room_name":    _s("Room to delete."),
            "floor_name":   _s("Floor name — deletes all rooms on this floor if no room_name."),
            "floor_number": _i("Floor number — deletes all rooms on this floor if no room_name."),
            "delete_all":   _b("True to delete all rooms."),
        }),
    ),


    # ── Driver tools ──────────────────────────────────────────

    _tool(
        "list_marketplace_drivers",
        (
            "Search and list available drivers in the marketplace catalog. "
            "Call this when the engineer asks to install a driver and you need "
            "to find the correct driver_id, OR when engineer explicitly says "
            "browse, search, show, or list marketplace drivers."
        ),
        _params({
            "search_query": _s("Filter by name, manufacturer, or description."),
        }),
    ),

    _tool(
        "get_driver_config",
        (
            "Return the configuration fields for a specific marketplace driver. "
            "Call when engineer asks to see a driver's config fields, "
            "or when you need to know required fields before installing."
        ),
        _params(
            {"driver_id": _s("Driver ID from the marketplace catalog.")},
            required=["driver_id"],
        ),
    ),

    _tool(
        "install_driver",
        (
            "Install a marketplace driver with its configuration. "
            "driver_id must come from the marketplace catalog. "
            "ip_address is auto-filled starting from 192.168.1.100, skipping used IPs. "
            "port uses the catalog default if not provided. "
            "room must be asked from the engineer when the catalog marks it required — "
            "never assume or auto-fill room. "
            "Multiple drivers of the same type are allowed if they have different IPs."
        ),
        _params(
            {
                "driver_id": _s("Driver ID from the marketplace catalog."),
                "config":    _obj("Config key-value pairs. ip_address auto-filled. Ask for room when required."),
            },
            required=["driver_id", "config"],
        ),
    ),

    _tool(
        "list_installed_drivers",
        (
            "List all installed drivers. "
            "Call ONLY when engineer explicitly says show, list, or search installed drivers."
        ),
        _params({
            "search_query": _s("Optional filter by driver name."),
        }),
    ),

    _tool(
        "update_driver",
        (
            "Update an installed driver's configuration. "
            "install_id identifies which driver to update. "
            "new_config contains only the fields being changed — partial update."
        ),
        _params(
            {
                "install_id": _s("install_id of the driver to update."),
                "new_config": _obj("Fields to update — only provided keys are changed."),
            },
            required=["install_id", "new_config"],
        ),
    ),

    _tool(
        "uninstall_driver",
        (
            "Remove an installed driver. "
            "Loads belonging to this gateway become unassigned — they are not deleted. "
            "install_id identifies which driver to remove."
        ),
        _params(
            {"install_id": _s("install_id of the driver to uninstall.")},
            required=["install_id"],
        ),
    ),


    # ── Load tools ────────────────────────────────────────────

    _tool(
        "add_load",
        (
            "Add a device load to an installed gateway driver. "
            "install_id identifies the gateway. "
            "load_type must be supported by that gateway per the catalog. "
            "load_name is required — if not provided auto-fill as "
            "'{room} {load_type} {index}' e.g. 'Living Room Light 1'. "
            "room is required in config — always ask the engineer which room. "
            "group_address and unit_id are auto-filled by the system — do not ask. "
            "If no gateway installed ask engineer to install one first. "
            "If multiple gateways and install_id not specified ask which gateway."
        ),
        _params(
            {
                "install_id": _s("Gateway install_id."),
                "load_type":  _s("Load type supported by this gateway e.g. 'light', 'cover', 'ac'."),
                "load_name":  _s("Unique name for this load."),
                "config":     _obj("Config including room. group_address and unit_id auto-filled."),
            },
            required=["install_id", "load_type", "load_name", "config"],
        ),
    ),

    _tool(
        "list_loads",
        (
            "List loads. "
            "If install_id given → list loads for that gateway only. "
            "If no install_id → list all loads including unassigned ones. "
            "Unassigned loads appear under 'Unassigned' label. "
            "Call for explicit listing or to verify loads before acting."
        ),
        _params({
            "install_id": _s("Gateway install_id. Omit to list all loads."),
        }),
    ),

    _tool(
        "update_load",
        (
            "Rename a load or update its config. "
            "Identify by load_name and optionally install_id. "
            "If same load_name exists on multiple gateways and no install_id given "
            "ask which gateway. "
            "new_load_name to rename, new_config for partial config update."
        ),
        _params(
            {
                "load_name":     _s("Current load name — identifier."),
                "install_id":    _s("Gateway install_id — narrows identification."),
                "new_load_name": _s("New load name."),
                "new_config":    _obj("Partial config update — only provided keys change."),
            },
            required=["load_name"],
        ),
    ),

    _tool(
        "remove_load",
        (
            "Remove a load from a gateway. "
            "Identify by load_name and optionally install_id. "
            "If same load_name exists on multiple gateways and no install_id given "
            "ask which gateway."
        ),
        _params(
            {
                "load_name":  _s("Load name to remove."),
                "install_id": _s("Gateway install_id — narrows identification."),
            },
            required=["load_name"],
        ),
    ),


    # ── Macro tools ───────────────────────────────────────────

    _tool(
        "create_macro",
        (
            "Create a named macro with a list of device actions. "
            "Before calling this, call list_installed_drivers and/or list_loads "
            "to resolve device names and rooms to exact device_ids. "
            "macro_name is optional — auto-fill as 'Macro N' if not provided. "
            "Each action needs device_id (install_id or load_id), action verb, "
            "optional room name, optional value for parametric actions. "
            "If a device is not found in installed drivers or loads reply: "
            "'Device not found. Please install it first.'"
        ),
        _params(
            {
                "macro_name": _s("Macro name. Auto-filled as 'Macro N' if not provided."),
                "actions":    _action_arr("List of actions (minimum 1)."),
            },
            required=["actions"],
        ),
    ),

    _tool(
        "read_all_macros",
        (
            "List all macros with their actions. "
            "Call ONLY when engineer explicitly says show, list, display, or read macros."
        ),
    ),

    _tool(
        "update_macro",
        (
            "Update an existing macro. Identify by macro_name. "
            "Supports: rename (new_macro_name), add actions (add_actions), "
            "remove actions (remove_actions — identified by device_id + action pair), "
            "edit actions (edit_actions — identified by device_id + action pair, "
            "provide new_action, new_room, or new_value to change). "
            "At least one of new_macro_name, add_actions, remove_actions, "
            "edit_actions must be provided."
        ),
        _params(
            {
                "macro_name":     _s("Name of the macro to update — identifier."),
                "new_macro_name": _s("New macro name."),
                "add_actions":    _action_arr("Actions to append to the macro."),
                "remove_actions": _remove_action_arr("Actions to remove — matched by device_id + action."),
                "edit_actions":   _edit_action_arr("Actions to edit — identified by device_id + action."),
            },
            required=["macro_name"],
        ),
    ),

    _tool(
        "delete_macro",
        (
            "Delete a specific macro by name or delete all macros. "
            "Single: provide macro_name. All: set delete_all to true."
        ),
        _params({
            "macro_name": _s("Name of the macro to delete."),
            "delete_all": _b("True to delete all macros."),
        }),
    ),

]