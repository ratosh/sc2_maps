# sc2_maps

Embedding mods files into a SC2 map, can be changed to support more mods but for this repo always having 2 is the desired behavior.

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
python game_check\weapon_check_bot.py --map Flat64 --batch 5 --timeout 30
```
