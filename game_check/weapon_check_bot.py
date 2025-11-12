import sys
import argparse
import abc
from sc2 import maps
from sc2.data import Race, Difficulty
from sc2.main import run_game
from sc2.player import Bot, Computer
from sc2.bot_ai import BotAI
from sc2.ids.ability_id import AbilityId
from sc2.ids.buff_id import BuffId
from sc2.ids.unit_typeid import UnitTypeId

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
    UnitTypeId.RAVEN: 0,
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
    UnitTypeId.ORACLE: 1,
    UnitTypeId.CARRIER: 0,
    UnitTypeId.INTERCEPTOR: 1,
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
    
    # --- Special units ---
    UnitTypeId.BUNKER: 0,
}


class UnitValidator(abc.ABC):
    """Abstract base for all validators."""

    def __init__(self, unit_type: UnitTypeId):
        self.unit_type = unit_type
        
    async def create(self, bot):
        return True

    async def prepare(self, bot):
        return True

    @abc.abstractmethod
    async def validate(self, bot):
        """Perform validation and return True when done."""
        ...


class WeaponValidator(UnitValidator):
    """Default validator for standard combat units."""
    
    async def validate(self, bot):
        data = bot.game_data.units[self.unit_type.value]
        weapons = data._proto.weapons
        expected = EXPECTED_WEAPONS.get(self.unit_type, 0)
        actual = len(weapons)

        if actual == expected:
            print(f"✅ {self.unit_type.name}: {actual}/{expected} weapon(s) OK")
        else:
            print(f"❌ {self.unit_type.name}: {actual}/{expected} weapon(s) missmatch")

        return True, actual != expected

class WeaponBuffValidator(UnitValidator):
    """VoidRay has extra bonus on Prismatic Alignment activation to expose weapon data."""
    def __init__(self, unit_type: UnitTypeId):
        super().__init__(unit_type)
        self.configs = {
            UnitTypeId.VOIDRAY: {"ability": AbilityId.EFFECT_VOIDRAYPRISMATICALIGNMENT, "buff": BuffId.VOIDRAYSWARMDAMAGEBOOST},
            UnitTypeId.ORACLE: {"ability": AbilityId.BEHAVIOR_PULSARBEAMON, "buff": BuffId.ORACLEWEAPON},
        }
        self.activated = False
        self.wait_steps = 0
        
    async def create(self, bot):
        spawn_data = [[self.unit_type, 1, bot.start_location, 1]]
        await bot.client.debug_create_unit(spawn_data)

    async def prepare(self, bot):
        units = bot.all_units.of_type(self.unit_type)
        return units

    async def validate(self, bot):
        units = bot.all_units.of_type(self.unit_type)
        if not units:
            return False, False

        unit = units.first
        if not self.activated:
            ability = self.configs[self.unit_type]["ability"]
            unit(ability)
            self.activated = True
            print(f"✨ Activated {ability.name} on {self.unit_type.name} ({unit.tag})")
            return False, False

        self.wait_steps += 1
        if self.wait_steps < 5:
            return False, False
        
        data = bot.game_data.units[self.unit_type.value]
        weapons = data._proto.weapons
        expected = EXPECTED_WEAPONS.get(self.unit_type, 0)
        actual = len(weapons)

        has_buff = self.configs[self.unit_type]["buff"] in unit.buffs
        if actual == expected and has_buff:
            print(f"✅ {self.unit_type.name}: {actual}/{expected}/{has_buff} weapon(s), buffs {list(unit.buffs)}. OK after Pulsar Beam")
        else:
            print(f"❌ {self.unit_type.name}: {actual}/{expected} weapon(s), buffs {list(unit.buffs)} missmatch ")

        return True, actual != expected and has_buff

# Possible problem when spawning units to put inside the bunker and other validator tests
class BunkerValidator(UnitValidator):
    """Validates bunker weapon scaling with various loaded units."""

    required_units = [
        UnitTypeId.MARINE,
        UnitTypeId.MARAUDER,
        UnitTypeId.REAPER,
        UnitTypeId.GHOST,
    ]

    def __init__(self, unit_type: UnitTypeId):
        super().__init__(unit_type)
        self.configs = [
            (UnitTypeId.MARINE, 4),
            (UnitTypeId.MARAUDER, 2),
            (UnitTypeId.REAPER, 4),
            (UnitTypeId.GHOST, 2),
        ]
        self.current_config = 0
        self.current_load_idx = 1
        self.wait_loading = False
        self.found_buffs = set[BuffId]()
        self.bunker_tag = None
        self.helper_tags = []
        self.helpers_spawned = False
        self.any_missmatch = False
        
    async def create(self, bot):
        spawn_data = [[self.unit_type, 1, bot.start_location, 1]]
        for unit_type, count in self.configs:
            spawn_data.append([unit_type, count, bot.start_location, 1])
        await bot.client.debug_create_unit(spawn_data)

    async def prepare(self, bot):
        units = bot.all_units.of_type(self.unit_type)
        return units

    async def prepare(self, bot):
        bunkers = bot.all_units.of_type(self.unit_type)
        if not bunkers:
            return False

        self.bunker_tag = bunkers.first.tag

        if not self.helpers_spawned:
            for unit_type, count in self.configs:
                units = bot.all_units.of_type(unit_type)
                if len(units) < count:
                    return False
            self.helpers_spawned = True
        return True

    async def validate(self, bot):
        bunker = bot.all_units.find_by_tag(self.bunker_tag)
        if not bunker:
            return False, False

        if self.current_config >= len(self.configs):
            print(f"🏁 Finished bunker validation. Failed: {self.any_missmatch}")
            await self.cleanup(bot)
            return True, self.any_missmatch

        unit_type, load_counts = self.configs[self.current_config]
        if self.current_load_idx > load_counts:
            buffs = self.found_buffs

            if load_counts == len(buffs):
                print(f"✅ {unit_type.name} bunker buffs OK: ({list(buffs)})")
            else:
                print(f"❌ {unit_type.name} bunker buff missmatch: {len(buffs)}/{load_counts} {list(buffs)}")
                self.any_missmatch = True

            self.found_buffs.clear()
            self.current_config += 1
            self.current_load_idx = 1
            bunker(AbilityId.UNLOADALL_BUNKER)
            return False, False

        if not self.wait_loading:
            self.wait_loading = True
            helpers = bot.all_units.of_type(unit_type).take(self.current_load_idx)
            self.helper_tags.clear()
            for u in helpers:
                self.helper_tags.append(u.tag)
                bunker(AbilityId.LOAD_BUNKER, u)
            return False, False
        else:
            helper = bot.all_units.tags_in(self.helper_tags)
            # The unit vanishes from the list when loaded into the bunker, so we wait
            if helper:
                return False, False
                
        if len(bunker.buffs) > 1:
            print(f"❌ {unit_type.name} bunker buff missmatch: {len(bunker.buffs)}/1 {list(bunker.buffs)}")
        self.found_buffs.update(bunker.buffs)

        self.wait_loading = False
        self.current_load_idx += 1
        bunker(AbilityId.UNLOADALL_BUNKER)
        return False, False

    async def cleanup(self, bot):
        if self.helpers_spawned:
            tags = [u.tag for u in bot.all_units.of_type(self.required_units)]
            await bot.client.debug_kill_unit(tags)
            self.helpers_spawned = False


class ValidatorManager:
    def __init__(self, bot):
        self.validators = {
            UnitTypeId.VOIDRAY: WeaponBuffValidator,
            UnitTypeId.ORACLE: WeaponBuffValidator,
            UnitTypeId.BUNKER: BunkerValidator,
        }

    def get_validator(self, unit_type):
        validator_cls = self.validators.get(unit_type, WeaponValidator)
        return validator_cls(unit_type)

class WeaponTestBot(BotAI):
    def __init__(self, batch_size: int=10, validation_timeout: int=30):
        super().__init__()
        self.unit_types = list(EXPECTED_WEAPONS.keys())
        self.current_index = 0
        self.batch_size = batch_size
        self.validation_timeout = validation_timeout
        self.pending_units = []
        self.any_missmatch = False
        self.done = False
        self.manager = ValidatorManager(self)

    async def on_step(self, iteration: int):
        if self.done:
            await self.client.leave()
            return

        if not self.pending_units:
            if self.current_index >= len(self.unit_types):
                print(f"✅ Weapon test completed in {iteration} iterations.")
                self.done = True
                return

            batch = self.unit_types[self.current_index:self.current_index + self.batch_size]
            self.current_index += self.batch_size
            for u in batch:
                validator = self.manager.get_validator(u)
                await validator.create(self)
                self.pending_units.append((validator, iteration))
            return

        next_pending = []
        for validator, start_loop in self.pending_units:
            if start_loop + self.validation_timeout <= iteration:
                print(f"⚠️ {validator.unit_type.name} failed, timed out in {self.validation_timeout} steps")
                self.any_missmatch = True
                continue

            ready = await validator.prepare(self)
            if not ready:
                next_pending.append((validator, start_loop))
                continue

            done, failed = await validator.validate(self)
            if failed:
                self.any_missmatch = True
            elif not done:
                next_pending.append((validator, start_loop))

        self.pending_units = next_pending


def main():
    parser = argparse.ArgumentParser(description="Check if SC2 units have weapons.")
    parser.add_argument("--map", type=str, required=True, help="Map name (e.g. Flat64)")
    parser.add_argument("--batch", type=int, default=10, help="Units per batch")
    parser.add_argument("--timeout", type=int, default=300, help="Steps before giving up on spawn")
    args = parser.parse_args()

    bot = WeaponTestBot(batch_size=args.batch, validation_timeout=args.timeout)

    run_game(
        maps.get(args.map),
        [Bot(Race.Terran, bot), Computer(Race.Zerg, Difficulty.Easy)],
        realtime=False,
    )

    sys.exit(-1 if bot.any_missmatch else 0)


if __name__ == "__main__":
    main()
