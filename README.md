# sc2_maps

Intended to solve problems when making new sc2 maps to be compatible with 4.10 version.

This repo contains:

* Script to embed files SC2 maps (can be changed to support more mods but for this repo always having 2 is the desired behavior)
* Fixes to known problems when converting maps
* Validation bot to confirm problems are solved

## Fixes

Covered problems:
* Missing weapons details
 
### Weapons

Due to changes on 5.x.x patches, some weapons are not available on the API. We add them as visual effects or buffs that should not affect the gameplay.
There is also an issue with units that change weapon behavior without changing unit type (VoidRay, Oracle and Bunkers). We can't just add the weapon as the Protobuff protocol is designed with weapon info shared on unit type data, so we can't change weapon information based on current state of a specific unit. 

Current solution to this issue is to add visual buffs to units giving more information. Here is how we add this information:
* Void ray: Has the basic weapon defined and a buff telling if void ray prismatic alignment is active. Bots should integrate the weapon and add a bonus damage when the buff is active.
* Oracle: Has the basic weapon and a buff telling that weapon is active. Bots should integrate that the weapon is only active when the buff is active.
* Bunker: No weapons but has buffs to specify the amount of units inside. Bots should copy the weapon from units and changing the attack amount based on the amount of units.

## How to build a map

Using build_sc2map.py the script to merge folders and pack the map

Usage:
    python build_sc2map.py  /path/to/MapFolder /path/to/GamePatch /path/to/ExtraFixes MapName [--force]

```sh
python build_sc2map.py maps/PylonAIE mods/Patch_5_0_14 mods/AiArenaExtraFixes PylonAIE_5_0_14 --force
```

## How to check

### Checking weapons
Batch is an optional param to specify how many paralel checks we do, important for validations that require game actions.
Timeout is an optional param to specify how many game steps a validation has to complete it's check.

Usage:
    python game_check\weapon_check_bot.py --map [map_name] [--batch [paralel_units]] [--timeout [spawn_timeout]]

```sh
python game_check\weapon_check_bot.py --map PylonAIE_5_0_14 --batch 5 --timeout 30
```

## Extracting patch

You can extract the current patch changes using Ladik's Casc Viewer.
Different patch versions can also be found on github: https://github.com/Ahli/sc2xml

Content inside mods\voidmulti.sc2mod is current game version patch

## Extracting stableid

This can be done by making a bot play a map on a windows machine. The stable.json file should be refreshed under %USERPROFILE%\Documents\StarCraft II folder.
This file then needs to be placed under the game patch folder.

NOTE: Our custom buffs need to be included on that stable.json file too.

## TODO

* Check terrain version (t3Terrain.xmml files), it needs to be 114;
* Check if we can replace our custom build script with sc2modkit
