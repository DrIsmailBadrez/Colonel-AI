"""Data models for the battlefield simulation."""

from dataclasses import dataclass, field, asdict
import time


@dataclass
class WarItem:
    """A unit on the battlefield grid."""

    id: str  # "SOLDIER-1", "TANK-3", "MEDCAR-2"
    callsign: str  # "Rifle-1", "Armor-3", "Doc-1"
    position: list[int]  # [x, y] on the grid (0-indexed)
    status: str  # "active" | "wounded" | "destroyed" | "unknown"
    faction: str  # "friendly" | "adversary"
    role: str  # "soldier" | "tank" | "car" | "medical_car" | "doctor" | "commander" | "scout"
    heading: str = "stationary"  # "N" | "S" | "E" | "W" | "stationary"
    detail: str = ""  # free-text notes
    destination: list[int] | None = None  # [x, y] dispatch target, or None
    health: int = 100  # 0-100 hit points
    controlled: bool = False  # True = player has manual control, AI paused

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Event:
    """A timestamped battlefield event."""

    timestamp: float = field(default_factory=time.time)
    event_type: str = ""  # "MOVE" | "CONTACT" | "STATUS" | "CALL" | "REPORT"
    description: str = ""
    source_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
