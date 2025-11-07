# sc2_maps
Supporting new sc2 maps

## How to use

Using build_sc2map.py the script to merge folders and pack the map

Usage:
    python build_sc2map.py /path/to/GamePatch /path/to/ExtraFixes /path/to/MapFolder [--force]

```sh
python build_sc2map.py maps/PylonAIE mods/Patch_5_0_14 mods/AiArenaExtraFixes PylonAIE_5_0_14 --force
```

## TODO

Patching all files (right now we only patch xml files):
* Patch folder has all patch files (extracted with casc)
* Put map name inside GameStrings.txt on the map folder
* Merge txt files as key value lines
