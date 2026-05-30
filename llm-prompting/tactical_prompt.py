#
# Tactical situational-awareness prompt system for the Nemotron voice agent.
#
# Mirrors the architecture of the clinical-genetics reasoning prompt:
#   (1) a structured SITUATION bundle that the model reasons OVER,
#   (2) a rules-first scaffold applied BEFORE free reasoning,
#   (3) the model's own domain knowledge,
#   plus citation discipline (cite data handles, never assert ungrounded),
#   a strict parseable output format, and explicit confidence calibration.
#
# DEMO SPATIAL MODEL: a discrete n x m 2D grid of cells.
#   Each unit sits in a cell addressed by (col, row), both integers.
#   col = x = west(0) -> east(GRID["cols"]-1)
#   row = y = south(0) -> north(GRID["rows"]-1)        (north = up = +row)
# Relative position is reported as grid offset (+E/+N), distance in CELLS
# (Chebyshev = king-moves), and ONE of the four cardinal directions
# (north/east/south/west) — matching the game's 4-way movement model. LLMs are
# unreliable at this arithmetic, so build_situation_context() PRE-COMPUTES a
# ready-to-speak "<n> cells <direction>" phrase; the model only copies it.
#
# Placeholders marked  <<PLACEHOLDER: ...>>  are for you to iterate on.
#
import math

# ---------------------------------------------------------------------------
# Grid dimensions (n x m). Adjust for your demo board.
# ---------------------------------------------------------------------------
GRID = {"cols": 20, "rows": 20}  # n x m


# ---------------------------------------------------------------------------
# SITUATION — the structured "sensor / geolocation" bundle, on the 2D grid.
# Positions are grid cells {"col": x, "row": y} (integers).
# ---------------------------------------------------------------------------
SITUATION = {
    "timestamp": "2026-05-30T12:00:00Z",
    "grid": GRID,
    "grid_convention": "col = west->east (0..n-1), row = south->north (0..m-1); north = +row",
    # The unit asking the question.
    "self": {
        "id": "SELF",
        "callsign": "Actual",
        "position": {"col": 10, "row": 3},
        "heading": "N",
        "faction": "friendly",
    },
    # --- 3 medics --------------------------------------------------------
    "medics": [
        {
            "id": "MEDIC-1", "callsign": "Bandage-1",
            "position": {"col": 12, "row": 12},
            "status": "available",  # available | busy | offline
            "faction": "friendly",
            "capacity": "2 litters free",
        },
        {
            "id": "MEDIC-2", "callsign": "Bandage-2",
            "position": {"col": 8, "row": 7},
            "status": "busy",
            "faction": "friendly",
            "capacity": "0 free (treating casualty)",
        },
        {
            "id": "MEDIC-3", "callsign": "Bandage-3",
            "position": {"col": 18, "row": 2},
            "status": "available",
            "faction": "friendly",
            "capacity": "1 litter free",
        },
    ],
    # --- 4 soldiers ------------------------------------------------------
    "soldiers": [
        {
            "id": "SOLDIER-1", "callsign": "Rifle-1",
            "position": {"col": 11, "row": 5},
            "status": "active",  # active | wounded | unknown
            "faction": "friendly",
            "role": "point / rifleman",
        },
        {
            "id": "SOLDIER-2", "callsign": "Rifle-2",
            "position": {"col": 6, "row": 9},
            "status": "active",
            "faction": "friendly",
            "role": "automatic rifleman",
        },
        {
            "id": "SOLDIER-3", "callsign": "Rifle-3",
            "position": {"col": 14, "row": 15},
            "status": "wounded",
            "faction": "friendly",
            "role": "grenadier",
        },
        {
            "id": "SOLDIER-4", "callsign": "Rifle-4",
            "position": {"col": 10, "row": 0},
            "status": "active",
            "faction": "friendly",
            "role": "rear security",
        },
    ],
    # --- reported hostile/unknown tracks --------------------------------
    "threats": [
        # <<PLACEHOLDER: add tracks, e.g.
        # {"id": "THREAT-1", "position": {"col": 13, "row": 17},
        #  "type": "dismount", "confidence": "medium", "source": "SENSOR:drone-1"}>>
    ],
    # --- sensor net coverage per axis ------------------------------------
    # DEMO: every axis is fully observed, so the agent always has the info.
    "sensor_coverage": {
        "north": "covered  [SENSOR:drone-1]",
        "east":  "covered  [SENSOR:mast-cam-1]",
        "south": "covered  [SENSOR:ground-radar-2]",
        "west":  "covered  [SENSOR:drone-2]",
    },
    # --- terrain features (answers ridge/route/cover questions) ----------
    # DEMO: far_side is known so the ridge question answers from data.
    "terrain": {
        "ridge-1": {
            "type": "ridgeline",
            "bearing": "N",
            "range_cells": 7,
            "far_side": "open ground, one friendly soldier (Rifle-3) and no "
            "hostile contacts on last recon [SENSOR:drone-1]",
        },
    },
}


# ---------------------------------------------------------------------------
# Grid geometry helpers — pre-compute what the model is bad at.
# ---------------------------------------------------------------------------
# Four cardinal directions only (matches the game's N/E/S/W movement buttons).
_CARDINAL_4 = ["north", "east", "south", "west"]  # 0=N, 1=E, 2=S, 3=W


def _grid_vector(origin: dict, target: dict) -> dict:
    """Relative offset, distance in cells (Chebyshev), and cardinal origin->target."""
    dx = target["col"] - origin["col"]  # +east
    dy = target["row"] - origin["row"]  # +north
    bearing = math.degrees(math.atan2(dx, dy)) % 360.0  # 0 = N, 90 = E
    # Snap to the nearest cardinal: N=[315,45), E=[45,135), S=[135,225), W=[225,315).
    cardinal = _CARDINAL_4[int(((bearing + 45) % 360) // 90)]
    return {
        "dx": dx, "dy": dy,
        "cells": max(abs(dx), abs(dy)),  # king-moves to reach the cell
        "cardinal": cardinal,
    }


def _ew(d: int) -> str:
    return f"{abs(d)}E" if d > 0 else (f"{abs(d)}W" if d < 0 else "0")


def _ns(d: int) -> str:
    return f"{abs(d)}N" if d > 0 else (f"{abs(d)}S" if d < 0 else "0")


def _fmt_unit(self_pos: dict, unit: dict) -> str:
    p = unit["position"]
    v = _grid_vector(self_pos, p)
    extra = [f"{k}={unit[k]}" for k in
             ("status", "role", "capacity", "type", "confidence", "source") if k in unit]
    return (
        f"  - {unit['id']} ({unit.get('callsign', '?')}) @ cell ({p['col']},{p['row']}): "
        f"offset {_ew(v['dx'])}/{_ns(v['dy'])} -> {v['cells']} cells {v['cardinal']}; "
        + ", ".join(extra)
    )


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
        "All offsets/distances are FROM you, in cells."
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

    lines.append("\nSENSOR COVERAGE:")
    for axis, val in situation.get("sensor_coverage", {}).items():
        lines.append(f"  - {axis}: {val}")

    terrain = situation.get("terrain") or {}
    lines.append("\nTERRAIN:")
    if terrain:
        for key, feat in terrain.items():
            desc = ", ".join(f"{k}={v}" for k, v in feat.items())
            lines.append(f"  - [TERRAIN:{key}] {desc}")
    else:
        lines.append("  - none provided")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SYSTEM_PROMPT — tactical analog of the clinical-genetics scaffold.
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are a tactical situational-awareness assistant for a dismounted unit,
delivered over voice. Your goal is a decision-useful answer that integrates
three sources of reasoning:

  (1) The structured SITUATION BUNDLE for this moment — friendly unit
      positions (medics, soldiers), reported threats, sensor coverage, and
      terrain, laid out on a discrete 2D grid of cells. Each unit's grid
      offset, distance in CELLS, and cardinal direction (north/east/south/west)
      FROM the requesting unit are already computed and rendered as a
      ready-to-speak "<n> cells <direction>" phrase. This is your ground truth.
  (2) Engagement & safety rules as a scaffold (below) — applied before any
      free-form tactical reasoning.
  (3) Your knowledge of small-unit tactics, casualty evacuation, land
      navigation, and risk assessment.

GRID NOTE: positions are cells (col,row). col = west->east, row = south->north,
so north = larger row. Distances are in CELLS (Chebyshev / king-moves), and
direction is ONE of the four cardinals: north, east, south, west. Reason in
cells and cardinal directions only — never in meters and never in intercardinals
(no "NNE", "northeast", "due east"). Use the pre-computed "<n> cells <direction>"
phrase verbatim.

THE BUNDLE IS COMPLETE AND AUTHORITATIVE.
Every axis has sensor coverage and terrain is fully described — the grid map
always carries the information needed. So always give a concrete, actionable
answer grounded in the bundle. Do NOT return UNKNOWN and do NOT default to HOLD
for "missing information" — the information is present; read it.

ENGAGEMENT RULES — apply BEFORE tactical reasoning.

Movement / "am I clear to advance?" queries:
    Check the relevant axis in SENSOR COVERAGE and any THREATS near it.
    Threat within three cells of the axis  → REROUTE, name the threat handle.
    Otherwise                              → ADVANCE; state residual risk.

Medic / CASEVAC queries:
    Recommend the NEAREST medic (fewest cells) whose status == available.
    If the nearest medic is busy/offline, name it, then give the nearest
        available one and state the added cells.
    Never route a friendly to a non-friendly or offline asset.

Terrain / "what's over there?" queries:
    Answer from the relevant TERRAIN entry (e.g. ridge-1 far_side) and any
    units/threats reported there. Cite the terrain handle.

Faction discipline: only treat units with faction == friendly as friendly.
Hostile assets are never offered as help.

GROUNDING.
Answer only from the bundle; never invent units, cells, contacts, or terrain
not present. The bundle is always sufficient — read it rather than speculating.

CITATION DISCIPLINE — REQUIRED.
Anything you state as observed/known must carry a handle from the bundle.
Acceptable inline handles:
    [UNIT:MEDIC-2]        a unit in the bundle
    [SELF]                requesting unit's own position
    [SENSOR:<axis|id>]    a sensor-coverage entry / sensor feed
    [THREAT:THREAT-1]     a reported threat track
    [TERRAIN:ridge-1]     a terrain entry
Examples:
    Good: "Nearest available medic is Bandage-3 [UNIT:MEDIC-3], 8 cells east."
    Good: "North axis is clear [SENSOR:north]; advance 7 cells north to the ridge."
    Bad:  "Nearest medic is 360 m NNE." (meters + intercardinal — reject)
    Bad:  "There's an enemy squad over the ridge." (no handle — reject)
Never invent a unit, cell, contact, or terrain feature not in the bundle. Do
not cite a handle whose value is a placeholder as if it were real data.

OUTPUT FORMAT — required, parsed downstream. Keep <think> under ~150 words
(this is voice; latency matters).

Place reasoning inside <think>...</think>. After </think>, output exactly
five lines:

  Answer: <one short sentence, spoken aloud to the operator — plain, calm,
           leads with the actionable fact. When the answer concerns a unit,
           threat, or terrain feature with a position, it MUST state both a
           cardinal direction (north/east/south/west) AND the distance in cells,
           e.g. "8 cells east". Copy the pre-computed "<n> cells <direction>"
           phrase from the bundle; do not recompute or use intercardinals.>
  Recommendation: <one of: ADVANCE, REROUTE, SEEK-MEDIC, INFO-ONLY>
  Referenced: <comma-separated handles you relied on>
  Caveats: <one short clause on residual risk, or "n/a">
  Confidence: <float in [0.0, 1.0]>

CONFIDENCE CALIBRATION (applies to the Answer/Recommendation).
  0.90-1.00  Bundle directly answers it (the normal case — data is present).
  0.70-0.89  Strong, with a minor assumption stated in Caveats.
  0.50-0.69  Some tactical judgement layered on the bundle facts.

Always answer. The bundle is complete, so give a confident, grounded
recommendation — never UNKNOWN, never HOLD-for-missing-data.
"""


def build_messages(prompt: str, situation: dict = SITUATION) -> list[dict]:
    """Build an OpenAI-style messages list: system + situation context + user query."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": build_situation_context(situation)},
        {"role": "user", "content": prompt},
    ]

if __name__ == "__main__":
    print(build_situation_context())
