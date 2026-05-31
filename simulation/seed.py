"""Initial battlefield seed: 10 friendly units + 10 adversary units (mirrored composition)."""

from .models import WarItem


def seed_items() -> list[WarItem]:
    """Return the initial set of units for the battlefield.

    Each faction has: 6 soldiers, 2 commanders, 2 medical cars.
    """
    return [
        # --- Friendly forces (left/center of grid) ---
        WarItem(
            id="SOLDIER-1",
            callsign="Rifle-1",
            position=[4, 7],
            status="active",
            faction="friendly",
            role="soldier",
        ),
        WarItem(
            id="SOLDIER-2",
            callsign="Rifle-2",
            position=[7, 5],
            status="active",
            faction="friendly",
            role="soldier",
        ),
        WarItem(
            id="SOLDIER-3",
            callsign="Rifle-3",
            position=[6, 10],
            status="active",
            faction="friendly",
            role="soldier",
        ),
        WarItem(
            id="SOLDIER-4",
            callsign="Rifle-4",
            position=[5, 3],
            status="active",
            faction="friendly",
            role="soldier",
        ),
        WarItem(
            id="SOLDIER-5",
            callsign="Rifle-5",
            position=[3, 9],
            status="active",
            faction="friendly",
            role="soldier",
        ),
        WarItem(
            id="SOLDIER-6",
            callsign="Rifle-6",
            position=[8, 7],
            status="active",
            faction="friendly",
            role="soldier",
        ),
        WarItem(
            id="COMMANDER-1",
            callsign="Eagle-6",
            position=[3, 7],
            status="active",
            faction="friendly",
            role="commander",
        ),
        WarItem(
            id="COMMANDER-2",
            callsign="Eagle-7",
            position=[2, 10],
            status="active",
            faction="friendly",
            role="commander",
        ),
        WarItem(
            id="MEDCAR-1",
            callsign="Doc-1",
            position=[1, 7],
            status="active",
            faction="friendly",
            role="medical_car",
        ),
        WarItem(
            id="MEDCAR-2",
            callsign="Doc-2",
            position=[1, 10],
            status="active",
            faction="friendly",
            role="medical_car",
        ),
        # --- Adversary forces (right side of grid, advancing west) ---
        # Mirrored composition: 6 soldiers, 2 commanders, 2 medical cars
        WarItem(
            id="ENEMY-1",
            callsign="Contact-1",
            position=[25, 3],
            status="active",
            faction="adversary",
            role="soldier",
        ),
        WarItem(
            id="ENEMY-2",
            callsign="Contact-2",
            position=[27, 9],
            status="active",
            faction="adversary",
            role="soldier",
        ),
        WarItem(
            id="ENEMY-3",
            callsign="Contact-3",
            position=[24, 12],
            status="active",
            faction="adversary",
            role="soldier",
        ),
        WarItem(
            id="ENEMY-4",
            callsign="Contact-4",
            position=[26, 6],
            status="active",
            faction="adversary",
            role="soldier",
        ),
        WarItem(
            id="ENEMY-5",
            callsign="Contact-5",
            position=[25, 10],
            status="active",
            faction="adversary",
            role="soldier",
        ),
        WarItem(
            id="ENEMY-6",
            callsign="Contact-6",
            position=[28, 7],
            status="active",
            faction="adversary",
            role="soldier",
        ),
        WarItem(
            id="ENEMY-CMD-1",
            callsign="Warlord-1",
            position=[27, 4],
            status="active",
            faction="adversary",
            role="commander",
        ),
        WarItem(
            id="ENEMY-CMD-2",
            callsign="Warlord-2",
            position=[26, 11],
            status="active",
            faction="adversary",
            role="commander",
        ),
        WarItem(
            id="ENEMY-MED-1",
            callsign="Medik-1",
            position=[28, 5],
            status="active",
            faction="adversary",
            role="medical_car",
        ),
        WarItem(
            id="ENEMY-MED-2",
            callsign="Medik-2",
            position=[28, 10],
            status="active",
            faction="adversary",
            role="medical_car",
        ),
    ]
