import sys
import argparse
from sc2 import maps
from sc2.data import Race, Difficulty
from sc2.main import run_game
from sc2.player import Bot, Computer
from sc2.bot_ai import BotAI
from sc2.ids.unit_typeid import UnitTypeId

# === Expected weapon count per combat unit ===
EXPECTED_WEAPONS = {
    # --- Terran ---
    UnitTypeId.MARINE: 1,
    UnitTypeId.MARAUDER: 1,
    UnitTypeId.REAPER: 1,
    UnitTypeId.GHOST: 1,
    UnitTypeId.HELLION: 1,
    UnitTypeId.HELLIONTANK: 1,
    UnitTypeId.SIEGETANK: 1,
    UnitTypeId.SIEGETANKSIEGED: 1,
    UnitTypeId.THOR: 2,
    UnitTypeId.THORAP: 2,
    UnitTypeId.WIDOWMINE: 0,
    UnitTypeId.WIDOWMINEBURROWED: 1,
    UnitTypeId.CYCLONE: 1,
    UnitTypeId.LIBERATOR: 1,
    UnitTypeId.LIBERATORAG: 1,
    UnitTypeId.VIKINGFIGHTER: 1,
    UnitTypeId.VIKINGASSAULT: 1,
    UnitTypeId.BANSHEE: 1,
    UnitTypeId.RAVEN: 0,  # ability-based
    UnitTypeId.MEDIVAC: 0,
    UnitTypeId.BATTLECRUISER: 2,
    UnitTypeId.PLANETARYFORTRESS: 1,
    UnitTypeId.MISSILETURRET: 1,

    # --- Protoss ---
    UnitTypeId.ZEALOT: 1,
    UnitTypeId.STALKER: 1,
    UnitTypeId.ADEPT: 1,
    UnitTypeId.SENTRY: 1,
    UnitTypeId.IMMORTAL: 1,
    UnitTypeId.COLOSSUS: 1,
    UnitTypeId.DISRUPTOR: 0,
    UnitTypeId.ARCHON: 1,
    UnitTypeId.PHOENIX: 1,
    UnitTypeId.VOIDRAY: 1,
    UnitTypeId.ORACLE: 1, # Need to use ability to enable weapon
    UnitTypeId.CARRIER: 0,
    UnitTypeId.TEMPEST: 2,
    UnitTypeId.MOTHERSHIP: 1,
    UnitTypeId.PHOTONCANNON: 1,

    # --- Zerg ---
    UnitTypeId.ZERGLING: 1,
    UnitTypeId.BANELING: 1,
    UnitTypeId.ROACH: 1,
    UnitTypeId.RAVAGER: 1,
    UnitTypeId.HYDRALISK: 1,
    UnitTypeId.LURKERMP: 0,
    UnitTypeId.LURKERMPBURROWED: 1,
    UnitTypeId.INFESTOR: 0,
    UnitTypeId.SWARMHOSTMP: 0,
    UnitTypeId.ULTRALISK: 1,
    UnitTypeId.QUEEN: 2,
    UnitTypeId.MUTALISK: 1,
    UnitTypeId.CORRUPTOR: 1,
    UnitTypeId.BROODLORD: 1,
    UnitTypeId.VIPER: 0,
    UnitTypeId.LOCUSTMP: 1,
    UnitTypeId.BROODLING: 1,
    UnitTypeId.SPORECRAWLER: 1,
    UnitTypeId.SPINECRAWLER: 1,
}

class WeaponTestBot(BotAI):
    def __init__(self, batch_size=10, spawn_timeout=30):
        super().__init__()
        self.unit_types = list(EXPECTED_WEAPONS.keys())
        self.current_index = 0
        self.batch_size = batch_size
        self.spawn_timeout = spawn_timeout

        # Tracking state
        self.pending_units = []  # (unit_type, step_counter)
        self.any_missmatch = False
        self.done = False

    async def on_step(self, iteration: int):
        if self.done:
            await self.client.leave()
            return

        # Check pending units
        if self.pending_units:
            next_pending = []
            units_to_kill = []

            for unit_type, counter in self.pending_units:
                units = self.all_units.of_type(unit_type)
                if units:
                    data = self.game_data.units[unit_type.value]
                    weapons = data._proto.weapons
                    actual = len(weapons)
                    expected = EXPECTED_WEAPONS.get(unit_type, 0)

                    if actual == expected:
                        print(f"✅ {unit_type.name}: {actual}/{expected} weapon(s) OK")
                    else:
                        print(f"❌ {unit_type.name}: {actual}/{expected} weapon(s) MISMATCH")
                        self.any_missmatch = True

                    units_to_kill.extend(u.tag for u in units)
                elif counter >= self.spawn_timeout:
                    print(f"⚠️ {unit_type.name}: failed to spawn after {self.spawn_timeout} steps")
                else:
                    next_pending.append((unit_type, counter + 1))

            if units_to_kill:
                await self.client.debug_kill_unit(units_to_kill)

            self.pending_units = next_pending
            if self.pending_units:
                return

        # Spawn next batch
        if self.current_index >= len(self.unit_types):
            print("\nWeapon test completed.")
            self.done = True
            return

        batch = self.unit_types[self.current_index:self.current_index + self.batch_size]
        self.current_index += self.batch_size

        try:
            spawn_data = [[u, 1, self.start_location, 1] for u in batch]
            await self.client.debug_create_unit(spawn_data)
            self.pending_units = [(u, 0) for u in batch]
        except Exception as e:
            print(f"⚠️ Batch spawn error: {e}")
            self.pending_units.clear()


def main():
    parser = argparse.ArgumentParser(description="Check if SC2 units have weapons.")
    parser.add_argument("--map", type=str, required=True, help="Map name (e.g. Flat64)")
    parser.add_argument("--batch", type=int, default=10, help="Number of units to spawn per batch")
    parser.add_argument("--timeout", type=int, default=30, help="Max steps to wait for spawn")
    args = parser.parse_args()

    bot = WeaponTestBot(batch_size=args.batch, spawn_timeout=args.timeout)

    run_game(
        maps.get(args.map),
        [Bot(Race.Terran, bot), Computer(Race.Zerg, Difficulty.Easy)],
        realtime=False,
    )

    sys.exit(-1 if bot.any_missmatch else 0)


if __name__ == "__main__":
    main()
