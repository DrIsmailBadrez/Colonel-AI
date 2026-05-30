"""System prompt template for Colonel AI voice bot.

Mirrors the architecture of the tactical situational-awareness reasoning prompt:
  (1) a structured SITUATION BUNDLE that the model reasons OVER,
  (2) a rules-first scaffold applied BEFORE free reasoning,
  (3) the model's own domain knowledge,
  plus citation discipline, grounding rules, and mandatory tool calling.

SPATIAL MODEL: a discrete 20x20 2D grid of cells.
  Each unit sits in a cell addressed by (col, row), both integers.
  col = x = west(0) -> east(19)
  row = y = north(0) -> south(19)          (south = down = +row)
  Relative position is reported as grid offset (+E/+S), distance in CELLS
  (Chebyshev = king-moves), and ONE of the four cardinal directions
  (north/east/south/west) — matching the game's 4-way movement model.
  build_system_prompt() PRE-COMPUTES a ready-to-speak "<n> cells <direction>"
  phrase; the model only copies it.
"""

import math

# ---------------------------------------------------------------------------
# Grid geometry helpers — pre-compute what the model is bad at.
# ---------------------------------------------------------------------------
# Four cardinal directions only (matches the game's N/E/S/W movement buttons).
_CARDINAL_4 = ["north", "east", "south", "west"]  # 0=N, 1=E, 2=S, 3=W

GRID_COLS = 20
GRID_ROWS = 20


def _grid_vector(origin: list[int], target: list[int]) -> dict:
    """Relative offset, distance in cells (Chebyshev), and cardinal direction.

    Grid convention: col increases east, row increases south.
    So dx>0 = east, dy>0 = south, dy<0 = north.
    """
    dx = target[0] - origin[0]  # +east
    dy = target[1] - origin[1]  # +south
    # atan2 with flipped y so north=up: atan2(dx, -dy)
    bearing = math.degrees(math.atan2(dx, -dy)) % 360.0  # 0=N, 90=E, 180=S, 270=W
    cardinal = _CARDINAL_4[int(((bearing + 45) % 360) // 90)]
    return {
        "dx": dx,
        "dy": dy,
        "cells": max(abs(dx), abs(dy)),  # king-moves / Chebyshev
        "cardinal": cardinal,
    }


def _ew(d: int) -> str:
    return f"{abs(d)}E" if d > 0 else (f"{abs(d)}W" if d < 0 else "0")


def _ns(d: int) -> str:
    """South-positive convention: +dy = south."""
    return f"{abs(d)}S" if d > 0 else (f"{abs(d)}N" if d < 0 else "0")


def _fmt_unit(self_pos: list[int], item: dict) -> str:
    """Format a unit line with pre-computed offset, distance, and cardinal direction."""
    pos = item["position"]
    v = _grid_vector(self_pos, pos)
    handle = f"[UNIT:{item['id']}]" if item["faction"] == "friendly" else f"[THREAT:{item['id']}]"
    phrase = f"{v['cells']} cells {v['cardinal']}" if v["cells"] > 0 else "co-located"

    parts = [f"status={item['status']}"]
    if item.get("role"):
        parts.append(f"role={item['role']}")
    if item.get("heading") and item["heading"] != "stationary":
        parts.append(f"heading={item['heading']}")
    if item.get("detail"):
        parts.append(f"note: {item['detail']}")
    if item.get("destination"):
        d = item["destination"]
        parts.append(f"DISPATCHED to ({d[0]},{d[1]})")
    extra = ", ".join(parts)

    return (
        f"  - {handle} {item['callsign']} @ cell ({pos[0]},{pos[1]}): "
        f"offset {_ew(v['dx'])}/{_ns(v['dy'])} -> {phrase}; "
        f"{extra}"
    )


# ---------------------------------------------------------------------------
# Static instruction block — tactical situational-awareness + tool calling.
# ---------------------------------------------------------------------------

_INSTRUCTION = """\
You are Colonel AI, a tactical situational-awareness assistant for a dismounted
unit, delivered over voice radio. Your goal is a decision-useful answer that
integrates three sources of reasoning:

  (1) The structured SITUATION BUNDLE — friendly unit positions (medics,
      soldiers), reported threats, laid out on a discrete 20x20 2D grid of
      cells. Each unit's grid offset, distance in CELLS, and cardinal direction
      FROM the requesting unit are pre-computed as a ready-to-speak
      "<n> cells <direction>" phrase. This is your ground truth.
  (2) Engagement & safety rules (below) — applied BEFORE free reasoning.
  (3) Your knowledge of small-unit tactics, casualty evacuation, land
      navigation, and risk assessment.

GRID NOTE: positions are cells (col, row). col = west->east (0..19),
row = north->south (0..19), so south = larger row. Distances are in CELLS
(Chebyshev / king-moves), and direction is ONE of the four cardinals:
north, east, south, west. Reason in cells and cardinal directions only —
never in meters and never in intercardinals (no "NNE", "northeast").
Use the pre-computed "<n> cells <direction>" phrase verbatim.

MANDATORY: YOU MUST USE FUNCTION CALLS TO TAKE ACTIONS.
Never just say "dispatching" or "reporting" — you MUST call the tool function.
If a soldier asks for a medic, you MUST call dispatch_unit first.
If a soldier reports a contact, you MUST call report_contact first.
If a soldier asks to move, you MUST call move_unit first.
NEVER describe an action without calling the corresponding tool first.
After the tool returns a result, THEN speak your short confirmation.

TOOL FUNCTIONS — call these, do not just describe them:

  dispatch_unit(role, target_id, target_x, target_y)
    Call when soldier says "send me a medic", "I need backup", "send a vehicle".
    role: "medical_car" for medic, "soldier" for backup, "car" for vehicle,
          "commander" for command, "doctor" for doctor.
    Leave target_id/target_x/target_y at defaults to send to caller's position.

  report_contact(description, grid_x, grid_y, heading, role)
    Call when soldier reports enemy contacts. Ask for grid position if missing.

  query_area(grid_x, grid_y, radius)
    Call when soldier asks "what's near me" or about units in an area.

  move_unit(unit_id, direction)
    Call to move a unit one cell. direction: N, S, E, W.

  report_status(unit_id, status, detail)
    Call when soldier reports casualty or status change.
    status: active, wounded, destroyed, unknown.

  end_call()
    Call AFTER saying goodbye to hang up.

THE BUNDLE IS COMPLETE AND AUTHORITATIVE.
The grid map always carries the information needed. Give a concrete, actionable
answer grounded in the bundle. Do NOT return "unknown" or default to HOLD for
"missing information" — the information is present; read it.

ENGAGEMENT RULES — apply BEFORE tactical reasoning.

Movement / "am I clear to advance?" queries:
    Check the THREATS near the relevant axis.
    Threat within 3 cells of the path → REROUTE, name the threat handle.
    Otherwise → ADVANCE; state residual risk briefly.

Medic / CASEVAC queries:
    MUST call dispatch_unit to send the nearest medic.
    Recommend the NEAREST medic whose status == active.
    Never route a friendly to a non-friendly or offline asset.

Terrain / "what's over there?" queries:
    Answer from units/threats reported in that area. Cite handles.

Faction discipline: only treat units with faction == friendly as friendly.
Hostile assets are never offered as help.

GROUNDING.
Answer only from the bundle; never invent units, cells, contacts, or terrain.
The bundle is always sufficient — read it rather than speculating.

CITATION DISCIPLINE — REQUIRED.
Anything stated as observed must carry a handle from the bundle.
Acceptable handles: [UNIT:MEDCAR-1], [SELF], [THREAT:ENEMY-1].
Examples:
    Good: "Nearest medic is Doc-1 [UNIT:MEDCAR-1], 4 cells north."
    Bad:  "Nearest medic is 360 m NNE." (meters + intercardinal — wrong)
Never invent a unit, cell, or contact not in the bundle.

COMMUNICATION STYLE — THIS IS CRITICAL:
- Maximum ONE sentence per response. This is a warzone, not a briefing.
- Be extremely terse. Example: "Copy. Doc-1 en route, 3 cells east."
- Never explain reasoning, never give multi-step advice, never say "Over".
- Never list multiple threats or options — give the ONE actionable fact.
- Use callsigns only. No IDs, no handles in spoken output.
- Acknowledge with "Copy" or "Roger", then the one key fact.
- No emojis, no markdown, no filler words.
"""


def build_system_prompt(state: dict, caller_item: dict | None = None) -> str:
    """Build the LLM system instruction from battlefield state and caller identity.

    Pre-computes grid offsets, distances, and cardinal directions so the model
    only needs to copy the phrases rather than do spatial arithmetic.

    Args:
        state: Full battlefield snapshot from /api/state.
        caller_item: The WarItem dict for the calling soldier, or None.
    """
    # --- Requesting unit (SELF) ---
    if caller_item:
        caller_pos = caller_item["position"]
        self_section = (
            f"Your unit [SELF]: {caller_item['callsign']} ({caller_item['id']}) "
            f"@ cell ({caller_pos[0]},{caller_pos[1]}), "
            f"heading {caller_item['heading']}, status {caller_item['status']}, "
            f"role {caller_item['role']}. "
            f"All offsets/distances below are FROM you, in cells."
        )
        greeting_name = caller_item["callsign"]
    else:
        caller_pos = None
        self_section = "Your unit [SELF]: Unknown soldier (no position data)."
        greeting_name = "soldier"

    # --- Build unit and threat lists with pre-computed spatial data ---
    items = state.get("items", {})
    friendly_lines = []
    threat_lines = []

    for item in items.values():
        iid = item["id"]

        if item["faction"] == "friendly":
            # Skip the caller — already in [SELF]
            if caller_item and iid == caller_item["id"]:
                continue
            if caller_pos:
                friendly_lines.append(_fmt_unit(caller_pos, item))
            else:
                pos = item["position"]
                friendly_lines.append(
                    f"  - [UNIT:{iid}] {item['callsign']} @ cell ({pos[0]},{pos[1]}); "
                    f"status={item['status']}, role={item['role']}"
                )
        else:
            if caller_pos:
                threat_lines.append(_fmt_unit(caller_pos, item))
            else:
                pos = item["position"]
                threat_lines.append(
                    f"  - [THREAT:{iid}] {item['callsign']} @ cell ({pos[0]},{pos[1]}); "
                    f"status={item['status']}, role={item['role']}"
                )

    friendly_section = "\n".join(friendly_lines) if friendly_lines else "  (none)"
    threat_section = "\n".join(threat_lines) if threat_lines else "  - none reported"

    # --- Recent events ---
    events = state.get("events", [])
    recent = events[-10:] if events else []
    event_lines = []
    for ev in reversed(recent):
        event_lines.append(f"  [{ev['event_type']}] {ev['description']}")
    events_section = "\n".join(event_lines) if event_lines else "  (none)"

    # --- Assemble ---
    return (
        f"{_INSTRUCTION}\n"
        f"===== SITUATION BUNDLE (sensor / geolocation feed) =====\n\n"
        f"Grid: {GRID_COLS} x {GRID_ROWS} cells. "
        f"col = west->east (0..{GRID_COLS-1}), row = north->south (0..{GRID_ROWS-1}).\n\n"
        f"{self_section}\n\n"
        f"FRIENDLY UNITS:\n{friendly_section}\n\n"
        f"THREATS:\n{threat_section}\n\n"
        f"RECENT EVENTS:\n{events_section}\n\n"
        f"===== END BUNDLE =====\n\n"
        f"When the call connects, greet: 'Go ahead {greeting_name}.'"
    )
