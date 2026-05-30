"""FastAPI state server: REST API + WebSocket + simulation engine."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .engine import simulation_loop
from .models import WarItem, Event
from .seed import seed_items
from .state import BattlefieldState

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("colonel.app")

# Global state — initialized in lifespan
state = BattlefieldState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Colonel AI state server starting — occupancy enforcement ENABLED")
    # Seed initial units
    for item in seed_items():
        state.items[item.id] = item
    # Start simulation engine
    sim_task = asyncio.create_task(simulation_loop(state))
    yield
    sim_task.cancel()
    try:
        await sim_task
    except asyncio.CancelledError:
        pass


app = FastAPI(lifespan=lifespan)

# --- Static files ---
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(static_dir / "index.html"))


# --- REST API ---


@app.get("/api/state")
async def get_state():
    return state.snapshot()


@app.get("/api/item/{item_id}")
async def get_item(item_id: str):
    item = state.get_item(item_id)
    if not item:
        return {"error": "not found"}
    return item.to_dict()


@app.post("/api/move")
async def move_item(body: dict):
    item_id = body.get("id")
    direction = body.get("direction", "").upper()
    if not item_id or direction not in ("N", "S", "E", "W"):
        return {"error": "invalid request, need id and direction (N/S/E/W)"}
    old_item = state.get_item(item_id)
    if not old_item:
        return {"error": "item not found"}
    old_pos = list(old_item.position)
    item = await state.move_item(item_id, direction)
    if not item:
        return {"error": "item not found"}
    result = item.to_dict()
    result["moved"] = item.position != old_pos
    return result


@app.post("/api/report")
async def report_contact(body: dict):
    """Report a new contact on the battlefield (typically from voice bot)."""
    grid_x = body.get("grid_x", 0)
    grid_y = body.get("grid_y", 0)
    description = body.get("description", "Unknown contact")
    heading = body.get("heading", "stationary")
    role = body.get("role", "soldier")
    source_id = body.get("source_id", "UNKNOWN")

    # Generate a unique ID for the new contact
    existing_enemies = [k for k in state.items if k.startswith("ENEMY-")]
    next_num = len(existing_enemies) + 1
    new_id = f"ENEMY-{next_num}"
    # Avoid collisions
    while new_id in state.items:
        next_num += 1
        new_id = f"ENEMY-{next_num}"

    new_item = WarItem(
        id=new_id,
        callsign=f"Contact-{next_num}",
        position=[grid_x, grid_y],
        status="active",
        faction="adversary",
        role=role,
        heading=heading,
        detail=description,
    )
    await state.add_item(new_item)

    # Add event for the report
    state._add_event(
        "CONTACT",
        f"{source_id} reported {description} at [{grid_x}, {grid_y}]",
        source_id,
    )

    return {"ok": True, "item": new_item.to_dict()}


@app.post("/api/status")
async def update_status(body: dict):
    """Update a unit's status (e.g., wounded, destroyed)."""
    item_id = body.get("id")
    new_status = body.get("status")
    detail = body.get("detail", "")
    if not item_id or not new_status:
        return {"error": "need id and status"}
    item = await state.update_status(item_id, new_status, detail)
    if not item:
        return {"error": "item not found"}
    return item.to_dict()


# Role aliases — LLMs often use "medic" instead of "medical_car", etc.
ROLE_ALIASES: dict[str, list[str]] = {
    "medic": ["medical_car", "doctor"],
    "medical": ["medical_car", "doctor"],
    "med": ["medical_car", "doctor"],
    "doctor": ["doctor", "medical_car"],
    "medical_car": ["medical_car", "doctor"],
    "backup": ["soldier"],
    "infantry": ["soldier"],
    "reinforcement": ["soldier"],
    "vehicle": ["car"],
    "transport": ["car"],
    "armor": ["tank"],
}


@app.post("/api/dispatch")
async def dispatch_unit(body: dict):
    """Dispatch a friendly unit to a target position.

    Body options:
      - unit_id + target_x + target_y: dispatch a specific unit
      - role + target_x + target_y: find nearest unit of that role and dispatch it
      - role + target_id: dispatch nearest unit of role to another unit's position
    """
    target_x = body.get("target_x")
    target_y = body.get("target_y")
    unit_id = body.get("unit_id")
    role = body.get("role")
    target_id = body.get("target_id")
    exclude_id = body.get("exclude_id")

    logger.info(f"DISPATCH request: {body}")

    # Resolve target position from target_id if needed
    if target_id and (target_x is None or target_y is None):
        target_item = state.get_item(target_id)
        if not target_item:
            logger.warning(f"DISPATCH failed: target unit {target_id} not found")
            return {"error": f"target unit {target_id} not found"}
        target_x = target_item.position[0]
        target_y = target_item.position[1]

    if target_x is None or target_y is None:
        logger.warning("DISPATCH failed: no target coordinates")
        return {"error": "need target_x/target_y or target_id"}

    # If no specific unit_id, find nearest matching role
    if not unit_id:
        if not role:
            logger.warning("DISPATCH failed: no unit_id or role")
            return {"error": "need unit_id or role"}

        # Try the role directly first, then try aliases
        roles_to_try = [role.lower()]
        aliases = ROLE_ALIASES.get(role.lower(), [])
        for alias in aliases:
            if alias not in roles_to_try:
                roles_to_try.append(alias)

        found = None
        for try_role in roles_to_try:
            found = state.find_nearest_friendly(try_role, [target_x, target_y], exclude_id=exclude_id)
            if found:
                logger.info(f"DISPATCH: matched role '{try_role}' (requested '{role}') → {found.callsign} ({found.id})")
                break

        if not found:
            # Last resort: try without role filter — find ANY available friendly
            logger.warning(f"DISPATCH: no unit with role '{role}' (tried {roles_to_try}), trying any friendly")
            found = state.find_nearest_friendly(None, [target_x, target_y], exclude_id=exclude_id)
            if found:
                logger.info(f"DISPATCH fallback: sending {found.callsign} ({found.id}, role={found.role})")

        if not found:
            logger.warning(f"DISPATCH failed: no available unit found for role '{role}'")
            return {"error": f"no available {role} found"}
        unit_id = found.id

    item = await state.dispatch_item(unit_id, target_x, target_y)
    if not item:
        logger.warning(f"DISPATCH failed: dispatch_item returned None for {unit_id}")
        return {"error": "unit not found or not friendly"}
    logger.info(f"DISPATCH success: {item.callsign} → [{target_x}, {target_y}]")
    return {"ok": True, "item": item.to_dict(), "destination": [target_x, target_y]}


@app.post("/api/control")
async def control_unit(body: dict):
    """Take manual control of a friendly unit, pausing its AI."""
    unit_id = body.get("unit_id")
    if not unit_id:
        return {"error": "need unit_id"}
    item = await state.control_item(unit_id)
    if not item:
        return {"error": "unit not found or not friendly"}
    return {"ok": True, "item": item.to_dict()}


@app.post("/api/release")
async def release_unit(body: dict):
    """Release manual control, resuming AI autonomy."""
    unit_id = body.get("unit_id")
    if not unit_id:
        return {"error": "need unit_id"}
    item = await state.release_item(unit_id)
    if not item:
        return {"error": "unit not found or not friendly"}
    return {"ok": True, "item": item.to_dict()}


@app.post("/api/cancel_dispatch")
async def cancel_dispatch(body: dict):
    """Cancel a unit's dispatch order."""
    unit_id = body.get("unit_id")
    if not unit_id:
        return {"error": "need unit_id"}
    item = await state.cancel_dispatch(unit_id)
    if not item:
        return {"error": "unit not found"}
    return {"ok": True, "item": item.to_dict()}


@app.get("/api/debug/overlaps")
async def check_overlaps():
    """Debug: check if any items share the same cell."""
    return {"overlaps": state.check_no_overlaps()}


@app.post("/api/query")
async def query_area(body: dict):
    """Query items near a grid position."""
    x = body.get("x", 0)
    y = body.get("y", 0)
    radius = body.get("radius", 3)
    return state.query_area(x, y, radius)


@app.post("/api/transcript")
async def add_transcript(body: dict):
    """Add a transcript entry for a soldier's call."""
    soldier_id = body.get("soldier_id")
    speaker = body.get("speaker", "unknown")
    text = body.get("text", "")
    if not soldier_id or not text:
        return {"error": "need soldier_id and text"}
    entry = await state.add_transcript(soldier_id, speaker, text)
    return {"ok": True, "entry": entry}


@app.get("/api/transcript/{soldier_id}")
async def get_transcripts(soldier_id: str):
    """Get all transcript entries for a soldier."""
    return {"soldier_id": soldier_id, "entries": state.get_transcripts(soldier_id)}


# --- WebSocket ---


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    q = state.subscribe()
    # Send initial state immediately
    try:
        await ws.send_json(state.snapshot())
    except Exception:
        state.unsubscribe(q)
        return

    # Heartbeat + update loop
    try:
        while True:
            try:
                snapshot = await asyncio.wait_for(q.get(), timeout=1.0)
                await ws.send_json(snapshot)
            except asyncio.TimeoutError:
                # Heartbeat: send current state every 1s even if no mutations
                await ws.send_json(state.snapshot())
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        state.unsubscribe(q)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("simulation.app:app", host="0.0.0.0", port=8000, reload=True)
