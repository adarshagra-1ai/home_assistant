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
                "device_id": _s("install_id or load_id."),
                "action":    _s("Action verb: turn_on, turn_off, set_temperature, open, close, etc."),
                "room":      _s("Room name."),
                "value":     _s("Value for parametric actions."),
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
                "device_id":  _s("Current device_id."),
                "action":     _s("Current action verb."),
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
                "device_id": _s("device_id to remove."),
                "action":    _s("Action verb to remove."),
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
        "Fetch a floor by name or number. Only when not in history; use read_all_floors to list.",
        _params({
            "floor_name":   _s("Floor name."),
            "floor_number": _i("Floor number."),
        }),
    ),

    _tool(
        "create_floor",
        "Create a floor. Both fields optional — auto-assign per system prompt rules. For batch: compute all numbers before emitting.",
        _params({
            "floor_name":   _s("Floor name. Auto-filled if not provided."),
            "floor_number": _i("Floor level. Auto-assigned if not provided."),
        }),
    ),

    _tool(
        "read_all_floors",
        "List all floors. Call when listing requested or floor context missing from history.",
    ),

    _tool(
        "update_floor",
        "Rename a floor or change its number. Both identifiers must refer to the same floor.",
        _params({
            "floor_name":       _s("Current floor name."),
            "floor_number":     _i("Current floor number."),
            "new_floor_name":   _s("New name."),
            "new_floor_number": _i("New number."),
        }),
    ),

    _tool(
        "delete_floor",
        "Delete a floor by name/number, or all floors (delete_all). Rooms become unassigned, not deleted.",
        _params({
            "floor_name":   _s("Floor to delete by name."),
            "floor_number": _i("Floor to delete by number."),
            "delete_all":   _b("True to delete all floors."),
        }),
    ),


    # ── Room tools ────────────────────────────────────────────

    _tool(
        "get_room",
        "Fetch a room. Only when not in history. Provide floor to narrow if name is ambiguous.",
        _params({
            "room_name":    _s("Room name."),
            "floor_name":   _s("Floor name to narrow the search."),
            "floor_number": _i("Floor number to narrow the search."),
        }),
    ),

    _tool(
        "create_room",
        "Create a room. Auto-fill room_name as 'Room N' if not provided (N = existing rooms on floor + 1). Use single existing floor automatically; ask if multiple. Emit create_floor first if needed.",
        _params({
            "room_name":    _s("Room name. Auto-filled as 'Room N' if omitted."),
            "floor_name":   _s("Floor name."),
            "floor_number": _i("Floor number."),
        }),
    ),

    _tool(
        "read_all_rooms",
        "List all rooms by floor. Call when listing requested or room context missing from history.",
    ),

    _tool(
        "update_room",
        "Rename a room or reassign to a floor. Ask which floor if name exists on multiple floors.",
        _params({
            "room_name":        _s("Current room name."),
            "floor_name":       _s("Current floor name."),
            "floor_number":     _i("Current floor number."),
            "new_room_name":    _s("New room name."),
            "new_floor_name":   _s("Reassign to this floor by name."),
            "new_floor_number": _i("Reassign to this floor by number."),
        }),
    ),

    _tool(
        "delete_room",
        "Delete a room, all rooms on a floor, or all rooms (delete_all). Ask which floor if name is ambiguous.",
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
        "Search marketplace catalog for drivers. Use to find driver_id before installing.",
        _params({
            "search_query": _s("Filter by name, manufacturer, or description."),
        }), 
    ),

    _tool(
        "get_driver_config",
        "Get config fields for a marketplace driver.",
        _params(
            {"driver_id": _s("Driver ID from the marketplace.")},
            required=["driver_id"],
        ),
    ),

    _tool(
        "install_driver",
        "Install a driver from the catalog. ip_address and port are auto-filled. Ask for room when catalog marks it required.",
        _params(
            {
                "driver_id": _s("Driver ID from the marketplace."),
                "config":    _obj("Config key-value pairs. ip_address auto-filled. Ask for room when required."),
            },
            required=["driver_id", "config"],
        ),
    ),

    _tool(
        "list_installed_drivers",
        "List installed drivers.",
        _params({
            "search_query": _s("Optional filter by driver name."),
        }),
    ),

    _tool(
        "update_driver",
        "Update driver config. Partial update — only provided keys change.",
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
        "Uninstall a driver. Its loads become unassigned, not deleted.",
        _params(
            {"install_id": _s("install_id of the driver to uninstall.")},
            required=["install_id"],
        ),
    ),


    # ── Load tools ────────────────────────────────────────────

    _tool(
        "add_load",
        "Add a load to a gateway. room required in config — always ask. load_name auto-fills as '{room} {type} {N}'. group_address/unit_id auto-filled. Ask which gateway if multiple exist.",
        _params(
            {
                "install_id": _s("Gateway install_id."),
                "load_type":  _s("Load type e.g. 'light', 'cover', 'ac'."),
                "load_name":  _s("Unique name for this load."),
                "config":     _obj("Config including room. group_address and unit_id auto-filled."),
            },
            required=["install_id", "load_type", "load_name", "config"],
        ),
    ),

    _tool(
        "list_loads",
        "List loads for a gateway or all loads. Call when listing requested or to verify before acting.",
        _params({
            "install_id": _s("Gateway install_id. Omit to list all loads."),
        }),
    ),

    _tool(
        "update_load",
        "Rename a load or update its config. Ask which gateway if name is ambiguous.",
        _params(
            {
                "load_name":     _s("Current load name."),
                "install_id":    _s("Gateway install_id."),
                "new_load_name": _s("New load name."),
                "new_config":    _obj("Partial config update — only provided keys change."),
            },
            required=["load_name"],
        ),
    ),

    _tool(
        "remove_load",
        "Remove a load. Ask which gateway if name is ambiguous.",
        _params(
            {
                "load_name":  _s("Load name to remove."),
                "install_id": _s("Gateway install_id."),
            },
            required=["load_name"],
        ),
    ),


    # ── Macro tools ───────────────────────────────────────────

    _tool(
        "create_macro",
        "Create a macro. Resolve device_ids via list_installed_drivers/list_loads first. macro_name auto-fills as 'Macro N'.",
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
        "List all macros.",
    ),

    _tool(
        "update_macro",
        "Update a macro: rename (new_macro_name), add/remove/edit actions. At least one change required.",
        _params(
            {
                "macro_name":     _s("Macro name — identifier."),
                "new_macro_name": _s("New macro name."),
                "add_actions":    _action_arr("Actions to append."),
                "remove_actions": _remove_action_arr("Actions to remove — matched by device_id + action."),
                "edit_actions":   _edit_action_arr("Actions to edit — identified by device_id + action."),
            },
            required=["macro_name"],
        ),
    ),

    _tool(
        "delete_macro",
        "Delete a macro by name or all macros (delete_all).",
        _params({
            "macro_name": _s("Name of the macro to delete."),
            "delete_all": _b("True to delete all macros."),
        }),
    ),

]
