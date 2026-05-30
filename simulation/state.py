"""Battlefield state management with async locking and WebSocket broadcast."""

import asyncio
import logging
import time
from .models import WarItem, Event

logger = logging.getLogger("colonel.state")

# Safe zone boundaries — units cannot enter the enemy faction's zone
SAFE_ZONE_RADIUS = 2
SAFE_ZONE_FRIENDLY = (2, 17, SAFE_ZONE_RADIUS)    # bottom-left corner
SAFE_ZONE_ADVERSARY = (17, 2, SAFE_ZONE_RADIUS)   # top-right corner


def _in_safe_zone(x: int, y: int, zone: tuple[int, int, int]) -> bool:
    cx, cy, r = zone
    return max(abs(x - cx), abs(y - cy)) <= r


def is_enemy_safe_zone(x: int, y: int, faction: str) -> bool:
    """Return True if (x,y) is inside the opposing faction's safe zone."""
    if faction == "friendly":
        return _in_safe_zone(x, y, SAFE_ZONE_ADVERSARY)
    else:
        return _in_safe_zone(x, y, SAFE_ZONE_FRIENDLY)


class BattlefieldState:
    """Thread-safe battlefield state with WebSocket broadcast on mutation."""

    def __init__(self, grid_w: int = 20, grid_h: int = 20):
        self.grid_w = grid_w
        self.grid_h = grid_h
        self.items: dict[str, WarItem] = {}
        self.events: list[Event] = []
        self.transcripts: dict[str, list[dict]] = {}  # soldier_id → list of {speaker, text, timestamp}
        self._lock = asyncio.Lock()
        self._subscribers: list[asyncio.Queue] = []

    # --- Reads (no lock needed in single-threaded asyncio) ---

    def snapshot(self) -> dict:
        """Full state as a JSON-serializable dict."""
        return {
            "grid_w": self.grid_w,
            "grid_h": self.grid_h,
            "items": {k: v.to_dict() for k, v in self.items.items()},
            "events": [e.to_dict() for e in self.events[-50:]],
            "transcripts": self.transcripts,
        }

    def get_item(self, item_id: str) -> WarItem | None:
        return self.items.get(item_id)

    def is_occupied(self, x: int, y: int, exclude_id: str | None = None) -> bool:
        """Check if a grid cell is occupied by any item (optionally excluding one)."""
        for item in self.items.values():
            if item.id == exclude_id:
                continue
            if item.position[0] == x and item.position[1] == y:
                return True
        return False

    def find_nearby_free_cell(self, x: int, y: int) -> tuple[int, int] | None:
        """Find the nearest unoccupied cell to (x, y) using BFS spiral."""
        if not self.is_occupied(x, y):
            return (x, y)
        from collections import deque
        visited = set()
        queue = deque([(x, y)])
        visited.add((x, y))
        while queue:
            cx, cy = queue.popleft()
            for dx, dy in [(0, -1), (0, 1), (1, 0), (-1, 0)]:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < self.grid_w and 0 <= ny < self.grid_h and (nx, ny) not in visited:
                    visited.add((nx, ny))
                    if not self.is_occupied(nx, ny):
                        return (nx, ny)
                    queue.append((nx, ny))
        return None

    def query_area(self, x: int, y: int, radius: int) -> dict:
        """Return items within Manhattan distance `radius` of (x, y)."""
        nearby = []
        for item in self.items.values():
            dx = abs(item.position[0] - x)
            dy = abs(item.position[1] - y)
            if dx + dy <= radius:
                nearby.append(item.to_dict())
        return {"center": [x, y], "radius": radius, "items": nearby}

    # --- Writes (acquire lock, then broadcast) ---

    async def add_item(self, item: WarItem) -> WarItem:
        async with self._lock:
            # If requested cell is occupied, find the nearest free cell
            if self.is_occupied(item.position[0], item.position[1]):
                free = self.find_nearby_free_cell(item.position[0], item.position[1])
                if free:
                    item.position = [free[0], free[1]]
            self.items[item.id] = item
            self._add_event(
                "REPORT",
                f"{item.callsign} ({item.faction} {item.role}) reported at [{item.position[0]}, {item.position[1]}]",
                item.id,
            )
            await self._broadcast()
        return item

    async def move_item(self, item_id: str, direction: str) -> WarItem | None:
        async with self._lock:
            item = self.items.get(item_id)
            if not item:
                return None
            x, y = item.position
            if direction == "N":
                y = max(0, y - 1)
            elif direction == "S":
                y = min(self.grid_h - 1, y + 1)
            elif direction == "E":
                x = min(self.grid_w - 1, x + 1)
            elif direction == "W":
                x = max(0, x - 1)
            # Block move if destination is occupied
            if self.is_occupied(x, y, exclude_id=item_id):
                logger.info(f"BLOCKED: {item.callsign} cannot move {direction} to [{x},{y}] — cell occupied")
                return item  # stay in place
            # Block entry into enemy safe zone
            if is_enemy_safe_zone(x, y, item.faction):
                logger.info(f"BLOCKED: {item.callsign} cannot enter enemy safe zone at [{x},{y}]")
                return item
            item.position = [x, y]
            item.heading = direction
            self._add_event(
                "MOVE",
                f"{item.callsign} moved {direction} to [{x}, {y}]",
                item.id,
            )
            await self._broadcast()
        return item

    async def update_status(self, item_id: str, status: str, detail: str = "") -> WarItem | None:
        async with self._lock:
            item = self.items.get(item_id)
            if not item:
                return None
            old_status = item.status
            item.status = status
            if detail:
                item.detail = detail
            self._add_event(
                "STATUS",
                f"{item.callsign} status changed from {old_status} to {status}"
                + (f" ({detail})" if detail else ""),
                item.id,
            )
            await self._broadcast()
        return item

    async def add_transcript(self, soldier_id: str, speaker: str, text: str) -> dict:
        """Append a transcript entry for a soldier's call."""
        entry = {"speaker": speaker, "text": text, "timestamp": time.time()}
        async with self._lock:
            if soldier_id not in self.transcripts:
                self.transcripts[soldier_id] = []
            self.transcripts[soldier_id].append(entry)
            await self._broadcast()
        return entry

    def get_transcripts(self, soldier_id: str) -> list[dict]:
        return self.transcripts.get(soldier_id, [])

    async def dispatch_item(self, item_id: str, target_x: int, target_y: int) -> WarItem | None:
        """Assign a destination to a friendly unit. The simulation engine will
        move it one cell per tick toward the target."""
        async with self._lock:
            item = self.items.get(item_id)
            if not item or item.faction != "friendly":
                return None
            item.destination = [target_x, target_y]
            self._add_event(
                "DISPATCH",
                f"{item.callsign} dispatched to [{target_x}, {target_y}]",
                item.id,
            )
            await self._broadcast()
        return item

    async def control_item(self, item_id: str) -> WarItem | None:
        """Take manual control of a friendly unit, pausing its AI."""
        async with self._lock:
            item = self.items.get(item_id)
            if not item or item.faction != "friendly":
                return None
            item.controlled = True
            self._add_event("STATUS", f"{item.callsign} — player took manual control", item.id)
            await self._broadcast()
        return item

    async def release_item(self, item_id: str) -> WarItem | None:
        """Release manual control, resuming AI autonomy."""
        async with self._lock:
            item = self.items.get(item_id)
            if not item or item.faction != "friendly":
                return None
            item.controlled = False
            self._add_event("STATUS", f"{item.callsign} — released to autonomous AI", item.id)
            await self._broadcast()
        return item

    async def cancel_dispatch(self, item_id: str) -> WarItem | None:
        """Cancel a unit's dispatch order."""
        async with self._lock:
            item = self.items.get(item_id)
            if not item:
                return None
            item.destination = None
            await self._broadcast()
        return item

    def find_nearest_friendly(self, role: str | None, target_pos: list[int], exclude_id: str | None = None) -> WarItem | None:
        """Find the nearest active friendly unit, optionally filtered by role."""
        best_dist = float("inf")
        best_item = None
        role_lower = role.lower() if role else None
        for item in self.items.values():
            if item.faction != "friendly" or item.status != "active":
                continue
            if item.id == exclude_id:
                continue
            if role_lower and item.role.lower() != role_lower:
                continue
            dist = abs(item.position[0] - target_pos[0]) + abs(item.position[1] - target_pos[1])
            if dist < best_dist:
                best_dist = dist
                best_item = item
        return best_item

    async def remove_item(self, item_id: str) -> bool:
        async with self._lock:
            item = self.items.pop(item_id, None)
            if not item:
                return False
            self._add_event("STATUS", f"{item.callsign} removed from battlefield", item.id)
            await self._broadcast()
        return True

    async def move_item_unlocked(self, item: WarItem, direction: str) -> bool:
        """Move an item without acquiring lock — caller must hold lock.

        Returns True if the move succeeded, False if blocked by occupancy.
        """
        x, y = item.position
        if direction == "N":
            y = max(0, y - 1)
        elif direction == "S":
            y = min(self.grid_h - 1, y + 1)
        elif direction == "E":
            x = min(self.grid_w - 1, x + 1)
        elif direction == "W":
            x = max(0, x - 1)
        if self.is_occupied(x, y, exclude_id=item.id):
            return False
        if is_enemy_safe_zone(x, y, item.faction):
            return False
        item.position = [x, y]
        item.heading = direction
        return True

    def check_no_overlaps(self) -> list[str]:
        """Debug: return list of overlap descriptions, if any."""
        positions: dict[tuple[int, int], list[str]] = {}
        for item in self.items.values():
            key = (item.position[0], item.position[1])
            positions.setdefault(key, []).append(item.id)
        return [
            f"Cell {pos}: {ids}" for pos, ids in positions.items() if len(ids) > 1
        ]

    # --- Internal helpers ---

    def _add_event(self, event_type: str, description: str, source_id: str):
        self.events.append(
            Event(
                timestamp=time.time(),
                event_type=event_type,
                description=description,
                source_id=source_id,
            )
        )
        # Keep only last 100 events
        if len(self.events) > 100:
            self.events = self.events[-100:]

    # --- Broadcast ---

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=16)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._subscribers = [s for s in self._subscribers if s is not q]

    async def _broadcast(self):
        """Push snapshot to all subscriber queues."""
        snapshot = self.snapshot()
        dead = []
        for q in self._subscribers:
            try:
                # Non-blocking put — drop if subscriber is behind
                q.put_nowait(snapshot)
            except asyncio.QueueFull:
                # Drop oldest and put new
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    q.put_nowait(snapshot)
                except asyncio.QueueFull:
                    dead.append(q)
        for q in dead:
            self._subscribers = [s for s in self._subscribers if s is not q]
