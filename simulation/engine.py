"""Simulation engine: adversary advance + medical response, 2-second tick."""

import asyncio
import logging
import random
from .state import BattlefieldState, SAFE_ZONE_FRIENDLY, SAFE_ZONE_ADVERSARY, SAFE_ZONE_RADIUS

logger = logging.getLogger("colonel.engine")


DIRECTIONS = ["N", "S", "E", "W"]

# Adversary target zone — friendly HQ area (left side of grid)
TARGET_X = 4
TARGET_Y = 7

# Combat constants
DAMAGE_SOLDIER = 3     # soldiers/commanders deal 3 dmg/tick
DAMAGE_TANK = 8        # tanks deal 8 dmg/tick
COMBAT_RANGE = 3       # Chebyshev distance
COMBAT_ROLES = {"soldier", "tank", "commander", "scout"}
HEAL_PER_TICK = 15
HEAL_RANGE = 2         # must be adjacent
MEDIC_ROLES = {"medical_car", "doctor"}

# Safe zone healing (zone geometry imported from state)
SAFE_ZONE_HEAL_PER_TICK = 10  # passive heal while inside

# Friendly AI engagement thresholds
AI_ENGAGE_RANGE = 8    # soldiers notice enemies within this range
AI_LOCAL_RANGE = 5     # radius to count force balance
AI_SCOUT_KEEP = 4      # scouts stop this far from enemies
AI_CMD_DRIFT = 3       # commanders reposition if further than this from centroid


def chebyshev_distance(a: list[int], b: list[int]) -> int:
    """Chebyshev (chessboard) distance between two grid positions."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def safe_zone_center(faction: str) -> list[int]:
    """Return the safe zone center [x, y] for a faction."""
    z = SAFE_ZONE_FRIENDLY if faction == "friendly" else SAFE_ZONE_ADVERSARY
    return [z[0], z[1]]


def in_safe_zone(item) -> bool:
    """Check if a unit is inside its faction's safe zone."""
    center = safe_zone_center(item.faction)
    return chebyshev_distance(item.position, center) <= SAFE_ZONE_RADIUS


def direction_toward(pos: list[int], target_x: int, target_y: int) -> str:
    """Return the cardinal direction that moves pos closest to (target_x, target_y)."""
    dx = target_x - pos[0]
    dy = target_y - pos[1]
    # Prefer the axis with greater distance
    if abs(dx) >= abs(dy):
        return "E" if dx > 0 else "W"
    else:
        return "S" if dy > 0 else "N"


def ranked_directions_toward(pos: list[int], target_x: int, target_y: int) -> list[str]:
    """Return directions ranked by how well they approach the target."""
    dx = target_x - pos[0]
    dy = target_y - pos[1]
    dirs = []
    # Primary axis first
    if abs(dx) >= abs(dy):
        dirs.append("E" if dx > 0 else "W")
        if dy != 0:
            dirs.append("S" if dy > 0 else "N")
        # Add perpendicular alternatives
        for d in DIRECTIONS:
            if d not in dirs:
                dirs.append(d)
    else:
        dirs.append("S" if dy > 0 else "N")
        if dx != 0:
            dirs.append("E" if dx > 0 else "W")
        for d in DIRECTIONS:
            if d not in dirs:
                dirs.append(d)
    return dirs


def find_nearest_hurt(state: BattlefieldState, medic_id: str, from_pos: list[int]) -> list[int] | None:
    """Find the nearest friendly unit with health < 100 (excluding self and destroyed)."""
    best_dist = float("inf")
    best_pos = None
    for item in state.items.values():
        if item.id == medic_id:
            continue
        if item.faction != "friendly" or item.status == "destroyed":
            continue
        if item.health >= 100:
            continue
        dist = abs(item.position[0] - from_pos[0]) + abs(item.position[1] - from_pos[1])
        if dist < best_dist:
            best_dist = dist
            best_pos = item.position
    return best_pos


def _nearest_enemy(item, state: BattlefieldState):
    """Return (enemy, chebyshev_dist) of the closest living adversary, or (None, inf)."""
    best, best_d = None, float("inf")
    for other in state.items.values():
        if other.faction == item.faction or other.status == "destroyed":
            continue
        d = chebyshev_distance(item.position, other.position)
        if d < best_d:
            best, best_d = other, d
    return best, best_d


def friendly_ai_directions(item, state: BattlefieldState) -> list[str] | None:
    """Return ranked move directions for an autonomous friendly unit, or None to hold."""

    if item.role in ("soldier", "commander"):
        enemy, dist = _nearest_enemy(item, state)
        if not enemy or dist > AI_ENGAGE_RANGE:
            return None  # no threat visible — hold

        if item.role == "commander":
            # Commanders stay near the centroid of friendly combat units
            fx, fy, count = 0, 0, 0
            for other in state.items.values():
                if (other.faction == "friendly" and other.role in COMBAT_ROLES
                        and other.status != "destroyed" and other.id != item.id):
                    fx += other.position[0]
                    fy += other.position[1]
                    count += 1
            if count > 0:
                cx, cy = round(fx / count), round(fy / count)
                if chebyshev_distance(item.position, [cx, cy]) > AI_CMD_DRIFT:
                    return ranked_directions_toward(item.position, cx, cy)
            return None

        # Soldier: check local force balance before engaging
        friendlies_nearby, enemies_nearby = 0, 0
        for other in state.items.values():
            if other.status == "destroyed":
                continue
            d = chebyshev_distance(item.position, other.position)
            if d <= AI_LOCAL_RANGE:
                if other.faction == "friendly" and other.role in COMBAT_ROLES:
                    friendlies_nearby += 1
                elif other.faction == "adversary":
                    enemies_nearby += 1
        if friendlies_nearby >= enemies_nearby:
            return ranked_directions_toward(item.position, enemy.position[0], enemy.position[1])
        return None  # outnumbered — hold

    if item.role == "tank":
        enemy, dist = _nearest_enemy(item, state)
        if enemy:
            return ranked_directions_toward(item.position, enemy.position[0], enemy.position[1])
        return None

    if item.role == "scout":
        enemy, dist = _nearest_enemy(item, state)
        if enemy and dist > AI_SCOUT_KEEP:
            return ranked_directions_toward(item.position, enemy.position[0], enemy.position[1])
        return None  # close enough — hold at recon distance

    return None  # car / unknown — hold


def find_escort_leader(state: BattlefieldState, item):
    """If a dispatched unit's destination is near a controlled friendly, return that unit."""
    if not item.destination:
        return None
    tx, ty = item.destination
    for other in state.items.values():
        if (other.faction == "friendly" and other.controlled
                and other.id != item.id and other.status != "destroyed"):
            if abs(tx - other.position[0]) + abs(ty - other.position[1]) <= 2:
                return other
    return None


async def simulation_loop(state: BattlefieldState, tick_interval: float = 1.0):
    """Run the simulation loop forever.

    - Adversary units advance toward the target zone with 20% random perturbation
    - Medical units move toward nearest wounded friendly
    - Friendly combat units hold position (controlled by UI or voice)
    """
    while True:
        await asyncio.sleep(tick_interval)
        async with state._lock:
            for item in list(state.items.values()):
                if item.status in ("destroyed", "unknown"):
                    continue

                # --- Player-controlled friendly: skip all AI movement ---
                if item.faction == "friendly" and item.controlled:
                    continue

                # --- Wounded retreat: uncontrolled combat units & medics fall back to safe zone ---
                if item.status == "wounded" and (item.role in COMBAT_ROLES or item.role in MEDIC_ROLES):
                    zone = safe_zone_center(item.faction)
                    if chebyshev_distance(item.position, zone) > 0:
                        dirs = ranked_directions_toward(item.position, zone[0], zone[1])
                        for d in dirs:
                            if await state.move_item_unlocked(item, d):
                                break
                    continue

                # --- Adversary AI: advance toward target ---
                if item.faction == "adversary" and item.status == "active":
                    if random.random() < 0.2:
                        dirs = [random.choice(DIRECTIONS)]
                        dirs += [d for d in DIRECTIONS if d not in dirs]
                    else:
                        dirs = ranked_directions_toward(item.position, TARGET_X, TARGET_Y)
                    for d in dirs:
                        if await state.move_item_unlocked(item, d):
                            break

                # --- Dispatched friendly units: move toward destination ---
                elif item.faction == "friendly" and item.destination:
                    # Escort mode: if destination is near a controlled unit, follow them
                    leader = find_escort_leader(state, item)
                    if leader:
                        item.destination = list(leader.position)

                    tx, ty = item.destination
                    dist = abs(item.position[0] - tx) + abs(item.position[1] - ty)

                    if dist <= 1:
                        if leader:
                            pass  # keep following — don't clear destination
                        else:
                            item.destination = None
                            logger.info(f"DISPATCH ARRIVED: {item.callsign} at [{item.position[0]},{item.position[1]}] (target [{tx},{ty}])")
                            state._add_event(
                                "DISPATCH",
                                f"{item.callsign} arrived at destination [{tx}, {ty}]",
                                item.id,
                            )
                    else:
                        old_pos = list(item.position)
                        dirs = ranked_directions_toward(item.position, tx, ty)
                        moved = False
                        for d in dirs:
                            if await state.move_item_unlocked(item, d):
                                moved = True
                                break
                        if moved:
                            logger.info(f"DISPATCH MOVE: {item.callsign} {old_pos} → [{item.position[0]},{item.position[1]}] toward [{tx},{ty}]")
                        else:
                            logger.warning(f"DISPATCH BLOCKED: {item.callsign} at {old_pos} — all directions blocked toward [{tx},{ty}]")
                        dist = abs(item.position[0] - tx) + abs(item.position[1] - ty)
                        if dist <= 1 and not leader:
                            item.destination = None
                            logger.info(f"DISPATCH ARRIVED: {item.callsign} at [{item.position[0]},{item.position[1]}] (target [{tx},{ty}])")
                            state._add_event(
                                "DISPATCH",
                                f"{item.callsign} arrived at destination [{tx}, {ty}]",
                                item.id,
                            )

                # --- Medical AI (no dispatch): move toward nearest hurt friendly ---
                elif item.role in ("medical_car", "doctor") and item.faction == "friendly" and not item.destination:
                    wounded_pos = find_nearest_hurt(state, item.id, item.position)
                    if wounded_pos:
                        dirs = ranked_directions_toward(item.position, wounded_pos[0], wounded_pos[1])
                        for d in dirs:
                            if await state.move_item_unlocked(item, d):
                                break

                # --- Friendly autonomous AI: role-based decisions ---
                elif item.faction == "friendly" and item.status == "active" and item.role in COMBAT_ROLES:
                    ai_dirs = friendly_ai_directions(item, state)
                    if ai_dirs:
                        for d in ai_dirs:
                            if await state.move_item_unlocked(item, d):
                                break

            # --- Phase 2: Combat damage ---
            all_items = list(state.items.values())
            for attacker in all_items:
                if attacker.status in ("destroyed", "unknown"):
                    continue
                if attacker.role not in COMBAT_ROLES:
                    continue
                damage = DAMAGE_TANK if attacker.role == "tank" else DAMAGE_SOLDIER
                nearest_target = None
                nearest_dist = float("inf")
                for target in all_items:
                    if target.faction == attacker.faction:
                        continue
                    if target.status == "destroyed":
                        continue
                    dist_to = chebyshev_distance(attacker.position, target.position)
                    if dist_to > COMBAT_RANGE:
                        continue
                    if dist_to < nearest_dist:
                        nearest_dist = dist_to
                        nearest_target = target
                    old_health = target.health
                    target.health = max(0, target.health - damage)
                    if target.health <= 0 and old_health > 0:
                        target.status = "destroyed"
                        state._add_event(
                            "STATUS",
                            f"{target.callsign} destroyed by {attacker.callsign}",
                            target.id,
                        )
                    elif target.health < 50 and old_health >= 50:
                        target.status = "wounded"
                        state._add_event(
                            "STATUS",
                            f"{target.callsign} wounded ({target.health}% HP)",
                            target.id,
                        )
                # Orient attacker toward nearest enemy in range
                if nearest_target:
                    attacker.heading = direction_toward(
                        attacker.position, nearest_target.position[0], nearest_target.position[1]
                    )

            # --- Phase 3: Healing ---
            for medic in all_items:
                if medic.status in ("destroyed", "unknown"):
                    continue
                if medic.role not in MEDIC_ROLES:
                    continue
                for patient in all_items:
                    if patient.faction != medic.faction:
                        continue
                    if patient is medic:
                        continue
                    if patient.status == "destroyed":
                        continue
                    if patient.health >= 100:
                        continue
                    if chebyshev_distance(medic.position, patient.position) > HEAL_RANGE:
                        continue
                    old_health = patient.health
                    patient.health = min(100, patient.health + HEAL_PER_TICK)
                    if patient.health >= 50 and old_health < 50:
                        patient.status = "active"
                        state._add_event(
                            "STATUS",
                            f"{patient.callsign} healed by {medic.callsign} — back to active ({patient.health}% HP)",
                            patient.id,
                        )

            # --- Phase 4: Safe zone passive healing ---
            for item in all_items:
                if item.status == "destroyed":
                    continue
                if item.health >= 100:
                    continue
                if not in_safe_zone(item):
                    continue
                old_health = item.health
                item.health = min(100, item.health + SAFE_ZONE_HEAL_PER_TICK)
                if item.health >= 50 and old_health < 50:
                    item.status = "active"
                    state._add_event(
                        "STATUS",
                        f"{item.callsign} recovered in safe zone — back to active ({item.health}% HP)",
                        item.id,
                    )

            # Invariant check: no two items on the same cell
            overlaps = state.check_no_overlaps()
            if overlaps:
                logger.warning(f"OVERLAP DETECTED: {overlaps}")

            await state._broadcast()
