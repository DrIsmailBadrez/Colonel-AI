"""Voice bot tool functions — direct functions registered on the LLM."""

import os

import aiohttp
from loguru import logger
from pipecat.frames.frames import EndTaskFrame, FunctionCallResultProperties
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.llm_service import FunctionCallParams

from prompts import build_system_prompt

STATE_URL = os.getenv("STATE_SERVER_URL", "http://localhost:8000")

# Will be set per-session by bot.py before tools are used
_caller_item: dict | None = None
_soldier_id: str | None = None


def set_caller_context(soldier_id: str | None, caller_item: dict | None):
    """Set the per-session caller context for tool handlers."""
    global _caller_item, _soldier_id
    _soldier_id = soldier_id
    _caller_item = caller_item


async def _refresh_system_prompt(params: FunctionCallParams):
    """Fetch latest state from state server and update the LLM system instruction."""
    global _caller_item
    try:
        async with aiohttp.ClientSession() as session:
            # Refresh caller item too
            if _soldier_id:
                async with session.get(f"{STATE_URL}/api/item/{_soldier_id}") as resp:
                    if resp.status == 200:
                        item_data = await resp.json()
                        if "error" not in item_data:
                            _caller_item = item_data

            async with session.get(f"{STATE_URL}/api/state") as resp:
                state = await resp.json()

        params.llm._settings.system_instruction = build_system_prompt(state, _caller_item)
    except Exception as e:
        logger.error(f"Failed to refresh system prompt: {e}")


async def report_contact(
    params: FunctionCallParams,
    description: str,
    grid_x: int,
    grid_y: int,
    heading: str = "unknown",
    role: str = "soldier",
) -> None:
    """Report a new enemy contact spotted on the battlefield.

    Use this when a soldier reports seeing enemy units. This adds a new
    adversary marker to the battlefield map.

    Args:
        description: What was spotted (e.g., "2 tanks", "infantry squad", "sniper").
        grid_x: X coordinate on the 20x20 grid (0-19).
        grid_y: Y coordinate on the 20x20 grid (0-19).
        heading: Direction the contact is moving: N, S, E, W, or unknown.
        role: Type of unit: soldier, tank, car. Default soldier.
    """
    try:
        async with aiohttp.ClientSession() as session:
            resp = await session.post(
                f"{STATE_URL}/api/report",
                json={
                    "grid_x": grid_x,
                    "grid_y": grid_y,
                    "description": description,
                    "heading": heading,
                    "role": role,
                    "source_id": _soldier_id or "UNKNOWN",
                },
            )
            result = await resp.json()
    except Exception as e:
        logger.error(f"report_contact failed: {e}")
        await params.result_callback({"error": str(e)})
        return

    await _refresh_system_prompt(params)
    await params.result_callback(result)


async def query_area(
    params: FunctionCallParams,
    grid_x: int,
    grid_y: int,
    radius: int = 3,
) -> None:
    """Query what units are near a grid position.

    Use this when a soldier asks what's near a location, or wants a
    situational update for an area.

    Args:
        grid_x: Center X coordinate on the 20x20 grid (0-19).
        grid_y: Center Y coordinate on the 20x20 grid (0-19).
        radius: Search radius in grid cells (Manhattan distance). Default 3.
    """
    try:
        async with aiohttp.ClientSession() as session:
            resp = await session.post(
                f"{STATE_URL}/api/query",
                json={"x": grid_x, "y": grid_y, "radius": radius},
            )
            result = await resp.json()
    except Exception as e:
        logger.error(f"query_area failed: {e}")
        await params.result_callback({"error": str(e)})
        return

    await params.result_callback(result)


async def move_unit(
    params: FunctionCallParams,
    unit_id: str,
    direction: str,
) -> None:
    """Move a friendly unit one cell in a cardinal direction.

    Use this when the Colonel needs to order a unit to move, or when
    a soldier requests to reposition.

    Args:
        unit_id: The ID of the unit to move (e.g., "SOLDIER-1").
        direction: Direction to move: N (north/up), S (south/down), E (east/right), W (west/left).
    """
    try:
        async with aiohttp.ClientSession() as session:
            resp = await session.post(
                f"{STATE_URL}/api/move",
                json={"id": unit_id, "direction": direction.upper()},
            )
            result = await resp.json()
    except Exception as e:
        logger.error(f"move_unit failed: {e}")
        await params.result_callback({"error": str(e)})
        return

    await _refresh_system_prompt(params)
    await params.result_callback(result)


async def report_status(
    params: FunctionCallParams,
    unit_id: str,
    status: str,
    detail: str = "",
) -> None:
    """Update a unit's status on the battlefield.

    Use this when a soldier reports being wounded, or reports that a
    unit has been destroyed, or any status change.

    Args:
        unit_id: The ID of the unit (e.g., "SOLDIER-1").
        status: New status: active, wounded, destroyed, or unknown.
        detail: Optional additional detail (e.g., "low ammo", "leg injury").
    """
    try:
        async with aiohttp.ClientSession() as session:
            resp = await session.post(
                f"{STATE_URL}/api/status",
                json={"id": unit_id, "status": status, "detail": detail},
            )
            result = await resp.json()
    except Exception as e:
        logger.error(f"report_status failed: {e}")
        await params.result_callback({"error": str(e)})
        return

    await _refresh_system_prompt(params)
    await params.result_callback(result)


async def dispatch_unit(
    params: FunctionCallParams,
    role: str,
    target_id: str = "",
    target_x: int = -1,
    target_y: int = -1,
) -> None:
    """Dispatch a friendly unit to a location. The unit will automatically
    navigate there on the battlefield map.

    Use this when a soldier requests support: "send me a medic",
    "I need backup", "send a vehicle", "move Rifle-2 to my position", etc.

    Args:
        role: Type of unit to send: soldier, medical_car, doctor, car, tank, commander.
              Use "medical_car" or "doctor" for medic requests.
              Use "soldier" for backup/reinforcement requests.
              Use "car" for vehicle requests.
        target_id: ID of the unit to send help TO (e.g., the caller's ID).
                   If provided, target_x/target_y are ignored.
                   Default: empty string (use target_x/target_y instead).
        target_x: X coordinate to dispatch to (0-19). Only used if target_id is empty.
        target_y: Y coordinate to dispatch to (0-19). Only used if target_id is empty.
    """
    body: dict = {"role": role}

    # Determine target: use caller's ID by default if no explicit target
    if target_id:
        body["target_id"] = target_id
    elif target_x >= 0 and target_y >= 0:
        body["target_x"] = target_x
        body["target_y"] = target_y
    elif _soldier_id:
        # Default to caller's position
        body["target_id"] = _soldier_id
    else:
        await params.result_callback({"error": "no target specified"})
        return

    # Don't dispatch the caller to themselves
    if _soldier_id:
        body["exclude_id"] = _soldier_id

    logger.info(f"dispatch_unit tool called: {body}")
    try:
        async with aiohttp.ClientSession() as session:
            resp = await session.post(
                f"{STATE_URL}/api/dispatch",
                json=body,
            )
            result = await resp.json()
    except Exception as e:
        logger.error(f"dispatch_unit failed: {e}")
        await params.result_callback({"error": str(e)})
        return

    if "error" in result:
        logger.warning(f"dispatch_unit returned error: {result}")
    else:
        logger.info(f"dispatch_unit success: {result.get('item', {}).get('callsign')} → {result.get('destination')}")

    await _refresh_system_prompt(params)
    await params.result_callback(result)


async def end_call(params: FunctionCallParams) -> None:
    """End the radio call. Only call this AFTER you have said goodbye in the
    same turn. The pipeline will flush any queued speech and then hang up."""
    logger.info("end_call invoked — pushing EndTaskFrame upstream")
    await params.llm.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)
    await params.result_callback(
        {"ok": True}, properties=FunctionCallResultProperties(run_llm=False)
    )
