#!/usr/bin/env python3
"""Derived Dune Exchange category masks.

The Exchange UI tree is separate from generic item category tags. These values
come from local game GUI category assets plus category rewrites observed from
the client/server exchange category refresh path.

Keep game assets out of the repo. This module stores only derived mask metadata
and keeps all importers on one shared Exchange-specific map.
"""

EXCHANGE_CATEGORY_MASKS = {
    "augments/armor": (0x04000000, 2),
    "augments/melee": (0x04010000, 2),
    "augments/misc": (0x04020000, 2),
    "augments/ranged": (0x04030000, 2),
    "armor/combat": (0x00010400, 3),
    "armor/heavy": (0x00010400, 3),
    "armor/light": (0x00000300, 3),
    "armor/social": (0x00030000, 2),
    "armor/stillsuit": (0x00020300, 3),
    "building/patents": (0x03070000, 2),
    "consumables/medical": (0x03060200, 3),
    "consumables/spice": (0x03060200, 3),
    "contracts": (0x05050000, 2),
    "customization": (0x05060000, 2),
    "resources/fuel": (0x05030000, 2),
    "resources/components": (0x05020000, 2),
    "resources/raw": (0x05000000, 2),
    "resources/refined": (0x05010000, 2),
    "schematics/augments": (0x07000000, 2),
    "schematics/armor": (0x07000000, 2),
    "schematics/armor/heavy": (0x07000000, 2),
    "schematics/armor/light": (0x07000000, 2),
    "schematics/armor/social": (0x07000000, 2),
    "schematics/armor/stillsuit": (0x07000000, 2),
    "schematics/utility": (0x07000000, 2),
    "schematics/utility/cartography": (0x07000000, 2),
    "schematics/utility/deployables": (0x07000000, 2),
    "schematics/utility/gathering": (0x07000000, 2),
    "schematics/utility/hydration": (0x07000000, 2),
    "schematics/vehicles": (0x07000000, 2),
    "schematics/vehicles/buggy": (0x07000000, 2),
    "schematics/vehicles/light_ornithopter": (0x07000000, 2),
    "schematics/vehicles/medium_ornithopter": (0x07000000, 2),
    "schematics/vehicles/sandbike": (0x07000000, 2),
    "schematics/vehicles/sandcrawler": (0x07000000, 2),
    "schematics/vehicles/transport_ornithopter": (0x07000000, 2),
    "schematics/weapons": (0x07000000, 2),
    "schematics/weapons/melee": (0x07000000, 2),
    "schematics/weapons/ranged": (0x07000000, 2),
    "tools/cartography": (0x03030000, 2),
    "tools/deployables": (0x03020000, 2),
    "tools/gathering": (0x03000000, 2),
    "tools/hydration": (0x03010000, 2),
    "tools/mining": (0x03000000, 2),
    "tools/utility": (0x03050100, 3),
    "vehicles/ammunition": (0x01020000, 2),
    "vehicles/buggy": (0x02010000, 2),
    "vehicles/light_ornithopter": (0x02020000, 2),
    "vehicles/medium_ornithopter": (0x02040000, 2),
    "vehicles/ornithopter": (0x02020000, 2),
    "vehicles/parts": (0x02010000, 2),
    "vehicles/sandbike": (0x02000500, 3),
    "vehicles/sandcrawler": (0x02030000, 2),
    "vehicles/transport_ornithopter": (0x02050000, 2),
    "weapons/ammunition": (0x01020000, 2),
    "weapons/melee": (0x01000100, 3),
    "weapons/ranged": (0x01010700, 3),
    "unknown": (0x00000000, 0),
}


if __name__ == "__main__":
    for category, (mask, depth) in sorted(EXCHANGE_CATEGORY_MASKS.items()):
        print(f"{category},{mask},{depth}")
