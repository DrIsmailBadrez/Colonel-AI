"""Initial battlefield seed: 5 friendly units + 3 adversary units."""

from .models import WarItem


def seed_items() -> list[WarItem]:
    """Return the initial set of units for the battlefield."""
    return [
        # --- Friendly forces (left/center of grid) ---
        WarItem(
            id="SOLDIER-1",
            callsign="Rifle-1",
            position=[3, 10],
            status="active",
            faction="friendly",
            role="soldier",
        ),
        WarItem(
            id="SOLDIER-2",
            callsign="Rifle-2",
            position=[5, 8],
            status="active",
            faction="friendly",
            role="soldier",
        ),
        WarItem(
            id="SOLDIER-3",
            callsign="Rifle-3",
            position=[4, 14],
            status="active",
            faction="friendly",
            role="soldier",
        ),
        WarItem(
            id="COMMANDER-1",
            callsign="Eagle-6",
            position=[2, 10],
            status="active",
            faction="friendly",
            role="commander",
        ),
        WarItem(
            id="MEDCAR-1",
            callsign="Doc-1",
            position=[1, 10],
            status="active",
            faction="friendly",
            role="medical_car",
        ),
        # --- Adversary forces (right side of grid, advancing west) ---
        WarItem(
            id="ENEMY-1",
            callsign="Contact-1",
            position=[17, 5],
            status="active",
            faction="adversary",
            role="soldier",
        ),
        WarItem(
            id="ENEMY-2",
            callsign="Contact-2",
            position=[18, 12],
            status="active",
            faction="adversary",
            role="tank",
        ),
        WarItem(
            id="ENEMY-3",
            callsign="Contact-3",
            position=[16, 17],
            status="active",
            faction="adversary",
            role="soldier",
        ),
    ]
