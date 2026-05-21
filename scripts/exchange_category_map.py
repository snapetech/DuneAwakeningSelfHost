#!/usr/bin/env python3
"""Derived Dune Exchange category masks.

The Exchange UI tree is separate from the generic item category tags. These
top-level buckets were derived from local client GUI.pak strings for
/Game/Dune/GUI/Data/ItemCategories/DA_ExchangeyTree:

1 Augments, 2 Garment, 3 Misc, 4 Utility, 5 Vehicles, 6 Weapons.

Keep game assets out of the repo. This module stores only derived mask metadata
and keeps all importers on one shared Exchange-specific map.
"""

EXCHANGE_CATEGORY_MASKS = {
    "resources/raw": (0x01010000, 2),
    "resources/refined": (0x01020000, 2),
    "resources/components": (0x01030000, 2),
    "augments/armor": (0x01010000, 2),
    "augments/melee": (0x01020000, 2),
    "augments/misc": (0x01030000, 2),
    "augments/ranged": (0x01040000, 2),
    "consumables/medical": (0x02010000, 2),
    "consumables/spice": (0x02010000, 2),
    "tools/mining": (0x03010000, 2),
    "tools/utility": (0x03020000, 2),
    "weapons/melee": (0x04010000, 2),
    "weapons/ranged": (0x04020000, 2),
    "armor/combat": (0x05010000, 2),
    "armor/heavy": (0x05010000, 2),
    "armor/light": (0x05010000, 2),
    "armor/social": (0x05030000, 2),
    "armor/stillsuit": (0x05020000, 2),
    "vehicles/parts": (0x06030000, 2),
    "vehicles/sandbike": (0x06010000, 2),
    "vehicles/ornithopter": (0x06020000, 2),
    "vehicles/buggy": (0x06030000, 2),
    "vehicles/sandcrawler": (0x06030000, 2),
    "schematics/weapons": (0x07010000, 2),
    "schematics/armor": (0x07020000, 2),
    "schematics/vehicles": (0x07030000, 2),
    "building/patents": (0x08010000, 2),
    "customization": (0x09010000, 2),
    "contracts": (0x09010000, 2),
    "unknown": (0x00000000, 0),
}


if __name__ == "__main__":
    for category, (mask, depth) in sorted(EXCHANGE_CATEGORY_MASKS.items()):
        print(f"{category},{mask},{depth}")
