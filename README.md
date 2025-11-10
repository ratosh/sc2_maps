# sc2_maps

Embedding mods files into a SC2 map, can be changed to support more mods but for this repo always having 2 is the desired behavior.

## Fixes
Intended to solve issues when making new sc2 maps to be compatible with 4.10 version.

### Weapons
The protobuff API is designed for weapons to be shared inside unit type data, so we can't change weapons based on current state of a unit.

To overcome this issue we add buffs to units giving more information. Here is a list of special weapons:
* Void ray: Has the basic weapon defined and a buff telling if void ray prismatic alignment is active, but we can't tell what is different on that weapon.
* Oracle: Has the basic weapon and a buff telling that weapon is active. Bots should integrate that the weapon is only active when the buff is active.
* Bunker: No weapons but has buffs to specify the amount of units inside. Bots should integrate the weapon from the units.

We can discuss better solutions.

## How to use

Using build_sc2map.py the script to merge folders and pack the map

Usage:
    python build_sc2map.py  /path/to/MapFolder /path/to/GamePatch /path/to/ExtraFixes [--force]

```sh
python build_sc2map.py maps/PylonAIE mods/Patch_5_0_14 mods/AiArenaExtraFixes PylonAIE_5_0_14 --force
```

## How to check

### Checking weapons

Usage:
    python game_check\weapon_check_bot.py --map [map_name] --batch [paralel_units] --timeout [spawn_timeout]

```sh
python game_check\weapon_check_bot.py --map PylonAIE_5_0_14 --batch 5 --timeout 30
```
