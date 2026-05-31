"""Colonel AI tactical prompt: a ground-truth SITUATION bundle + a rules-first
scaffold (_INSTRUCTION). Positions are cells (col,row); col=west->east,
row=north->south. build_situation_context() pre-computes a ready-to-speak
"<n> cells <cardinal>" phrase per unit (LLMs are unreliable at the arithmetic)."""

# ---------------------------------------------------------------------------
# Grid dimensions. Adjust for your demo board.
# ---------------------------------------------------------------------------
GRID = {"cols": 20, "rows": 20}


# ---------------------------------------------------------------------------
# SITUATION — the structured "sensor / geolocation" bundle, on the 2D grid.
# Positions are grid cells {"col": x, "row": y} (integers).
# row = north->south, so a larger row is further SOUTH.
# ---------------------------------------------------------------------------
SITUATION = {
    "timestamp": "2026-05-30T12:00:00Z",
    "grid": GRID,
    "grid_convention": "col = west->east (0..19), row = north->south (0..19); south = +row",
    # The unit asking the question.
    "self": {
        "id": "SELF",
        "callsign": "Actual",
        "position": {"col": 10, "row": 10},
        "heading": "N",
        "faction": "friendly",
    },
    # --- 3 medical cars (role = medical_car) -----------------------------
    "medics": [
        {
            "id": "MEDCAR-1", "callsign": "Doc-1",
            "position": {"col": 10, "row": 6},
            "status": "active",  # active | wounded | destroyed | unknown
            "faction": "friendly",
            "role": "medical_car",
            "capacity": "2 litters free",
        },
        {
            "id": "MEDCAR-2", "callsign": "Doc-2",
            "position": {"col": 4, "row": 12},
            "status": "active",
            "faction": "friendly",
            "role": "medical_car",
            "capacity": "1 litter free",
        },
        {
            "id": "MEDCAR-3", "callsign": "Doc-3",
            "position": {"col": 16, "row": 2},
            "status": "unknown",
            "faction": "friendly",
            "role": "medical_car",
            "capacity": "unknown",
        },
    ],
    # --- 4 soldiers ------------------------------------------------------
    "soldiers": [
        {
            "id": "SOLDIER-1", "callsign": "Rifle-1",
            "position": {"col": 11, "row": 9},
            "status": "active",  # active | wounded | destroyed | unknown
            "faction": "friendly",
            "role": "point / rifleman",
        },
        {
            "id": "SOLDIER-2", "callsign": "Rifle-2",
            "position": {"col": 6, "row": 13},
            "status": "active",
            "faction": "friendly",
            "role": "automatic rifleman",
        },
        {
            "id": "SOLDIER-3", "callsign": "Rifle-3",
            "position": {"col": 14, "row": 4},
            "status": "wounded",
            "faction": "friendly",
            "role": "grenadier",
        },
        {
            "id": "SOLDIER-4", "callsign": "Rifle-4",
            "position": {"col": 10, "row": 17},
            "status": "active",
            "faction": "friendly",
            "role": "rear security",
        },
    ],
    # --- reported hostile/unknown tracks --------------------------------
    "threats": [
        {
            "id": "ENEMY-1", "callsign": "Hostile-1",
            "position": {"col": 13, "row": 5},
            "type": "dismount",
            "confidence": "medium",
            "faction": "hostile",
        },
    ],
}


# ---------------------------------------------------------------------------
# Grid geometry helpers — pre-compute what the model is bad at.
# Output is a single ready-to-speak "<n> cells <direction>" phrase: distance in
# cells (Chebyshev) and ONE cardinal (the dominant axis). No intercardinals.
# ---------------------------------------------------------------------------
def _bearing_phrase(origin: dict, target: dict) -> str:
    """Ready-to-speak '<n> cells <cardinal>' from origin to target.

    row increases southward, so +row delta = south, -row delta = north.
    The cardinal is the dominant axis; ties resolve to north/south.
    """
    dx = target["col"] - origin["col"]   # +east
    drow = target["row"] - origin["row"]  # +south (row grows southward)
    cells = max(abs(dx), abs(drow))
    if cells == 0:
        return "at your position"
    if abs(dx) > abs(drow):
        direction = "east" if dx > 0 else "west"
    else:
        direction = "south" if drow > 0 else "north"
    return f"{cells} cell{'s' if cells != 1 else ''} {direction}"


def _fmt_unit(self_pos: dict, unit: dict) -> str:
    p = unit["position"]
    phrase = _bearing_phrase(self_pos, p)
    extra = [
        f"{k}={unit[k]}"
        for k in ("status", "role", "capacity", "type", "confidence", "faction")
        if k in unit
    ]
    line = (
        f"  - {unit['id']} ({unit.get('callsign', '?')}) @ cell "
        f"({p['col']},{p['row']}): {phrase}"
    )
    return line + ("; " + ", ".join(extra) if extra else "")


def build_situation_context(situation: dict = SITUATION) -> str:
    """Render the situation bundle as a grid-relative, readable block."""
    me = situation["self"]
    g = situation["grid"]
    lines: list[str] = []
    lines.append("=== SITUATION BUNDLE (sensor / geolocation feed) ===")
    lines.append(f"Timestamp: {situation['timestamp']}")
    lines.append(f"Grid: {g['cols']} x {g['rows']} cells. {situation['grid_convention']}")
    lines.append(
        f"Your unit: {me['id']} ({me['callsign']}) @ cell "
        f"({me['position']['col']},{me['position']['row']}), heading {me['heading']}. "
        "All distances/directions below are FROM you, as ready-to-speak "
        '"<n> cells <cardinal>" phrases.'
    )

    lines.append("\nMEDICS:")
    for m in situation["medics"]:
        lines.append(_fmt_unit(me["position"], m))

    lines.append("\nFRIENDLY SOLDIERS:")
    for s in situation["soldiers"]:
        lines.append(_fmt_unit(me["position"], s))

    threats = situation.get("threats") or []
    lines.append("\nTHREATS:")
    if threats:
        for t in threats:
            lines.append(_fmt_unit(me["position"], t))
    else:
        lines.append("  - none reported (NOTE: absence of report != area is clear)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# _INSTRUCTION — Colonel AI tactical scaffold (tool-calling, voice radio).
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

COMMUNICATION STYLE:
- Voice delivery: 1-2 sentences max. Calm, direct, military radio style.
- Use callsigns, not full IDs.
- Acknowledge reports with "Copy" or "Roger".
- No emojis, no markdown. Spoken responses only.
"""


def build_messages(
    prompt: str, situation: dict = SITUATION, instruction: str | None = None
) -> list[dict]:
    """Build an OpenAI-style messages list: system + situation context + user query.

    `instruction` overrides the default _INSTRUCTION scaffold — used by the
    auto-improve loop (improve.py) to test candidate prompt versions.
    """
    return [
        {"role": "system", "content": instruction or _INSTRUCTION},
        {"role": "system", "content": build_situation_context(situation)},
        {"role": "user", "content": prompt},
    ]


if __name__ == "__main__":
    print(build_situation_context())
