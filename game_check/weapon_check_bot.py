import abc
import argparse
import sys

from loser_bot import LoserBot
from sc2 import maps
from sc2.bot_ai import BotAI
from sc2.data import Attribute, Race, TargetType
from sc2.ids.ability_id import AbilityId
from sc2.ids.buff_id import BuffId
from sc2.ids.unit_typeid import UnitTypeId
from sc2.main import run_game
from sc2.player import Bot

SKIP_TARGET_UNITS = {
    UnitTypeId.SCV,
    UnitTypeId.PROBE,
    UnitTypeId.DRONE,
    UnitTypeId.DRONEBURROWED,
    UnitTypeId.MUTALISK,
    UnitTypeId.LOCUSTMP,
    UnitTypeId.LOCUSTMPFLYING,
    UnitTypeId.BROODLING,
}

FLYING_TYPES = {
    # Terran
    UnitTypeId.MEDIVAC,
    UnitTypeId.VIKINGFIGHTER,
    UnitTypeId.BANSHEE,
    UnitTypeId.LIBERATOR,
    UnitTypeId.LIBERATORAG,
    UnitTypeId.BATTLECRUISER,
    # Protoss
    UnitTypeId.PHOENIX,
    UnitTypeId.VOIDRAY,
    UnitTypeId.ORACLE,
    UnitTypeId.CARRIER,
    UnitTypeId.INTERCEPTOR,
    UnitTypeId.TEMPEST,
    UnitTypeId.MOTHERSHIP,
    # Zerg
    UnitTypeId.MUTALISK,
    UnitTypeId.CORRUPTOR,
    UnitTypeId.BROODLORD,
    UnitTypeId.VIPER,
    UnitTypeId.LOCUSTMPFLYING,
}

EXPECTED_WEAPONS = {
    # Terran
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
    # UnitTypeId.LIBERATORAG: 1,
    UnitTypeId.VIKINGFIGHTER: 1,
    UnitTypeId.VIKINGASSAULT: 1,
    UnitTypeId.BANSHEE: 1,
    UnitTypeId.RAVEN: 0,
    UnitTypeId.MEDIVAC: 0,
    UnitTypeId.BATTLECRUISER: 2,
    UnitTypeId.PLANETARYFORTRESS: 1,
    UnitTypeId.MISSILETURRET: 1,

    # Protoss
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
    # UnitTypeId.PHOTONCANNON: 1,

    # Zerg
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

    # Special units
    UnitTypeId.BUNKER: 0,
}


def debug_weapons(weapons):
    for i, w in enumerate(weapons, start=1):
        try:
            target_type = TargetType(w.type).name
        except ValueError:
            target_type = f"UNKNOWN({w.type})"
        print(
            f"Weapon {i}: Type={target_type}, Damage={w.damage}, Range={w.range}, Attacks={w.attacks}, Speed={w.speed}")
        if w.damage_bonus:
            for b in w.damage_bonus:
                try:
                    attr_name = Attribute(b.attribute).name
                except ValueError:
                    attr_name = f"UNKNOWN({b.attribute})"
                print(f"  Bonus vs {attr_name}: +{b.bonus}")
        else:
            print("  No damage bonus")


class UnitValidator(abc.ABC):

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
    def __init__(self, unit_type: UnitTypeId):
        super().__init__(unit_type)
        self.tests = []
        self.current_test = 0
        self.started = False
        self.wait_frames = 0
        self.start_hp = 0

    async def create(self, bot):
        data = bot.game_data.units[self.unit_type.value]
        weapons = data._proto.weapons

        for w in weapons:
            target_type = TargetType(w.type)

            skip_attributes = [b.attribute for b in w.damage_bonus]
            base_target = bot.pick_unit_without_attribute_no_armor(target_type, skip_attributes)
            if base_target is None:
                print(f"Fail to find a valid target type for {self.unit_type.name}")
                continue

            self.tests.append({
                "attacker_type": self.unit_type,
                "target_type": base_target,
                "target_spawned": False,
                "attacker_spawned": False,
                "expected_damage": w.damage * w.attacks,
                "attacks": w.attacks,
                "attacker_tag": None,
                "target_tag": None,
            })

            for bonus in w.damage_bonus:
                attr = Attribute(bonus.attribute)
                bonus_target = bot.pick_unit_with_attribute_no_armor(target_type, attr)
                if bonus_target is None:
                    continue
                self.tests.append({
                    "target_type": bonus_target,
                    "target_spawned": False,
                    "attacker_spawned": False,
                    "expected_damage": (w.damage + bonus.bonus) * w.attacks,
                    "attacks": w.attacks,
                    "attacker_tag": None,
                    "target_tag": None,
                })

    async def prepare(self, bot):
        return True

    async def validate(self, bot):
        data = bot.game_data.units[self.unit_type.value]
        weapons = data._proto.weapons
        expected = EXPECTED_WEAPONS.get(self.unit_type, 0)
        actual = len(weapons)
        if actual != expected:
            print(f"❌ {self.unit_type.name} weapons mismatch")
            debug_weapons(weapons)
            return True, True

        if self.current_test >= len(self.tests):
            return True, False

        test = self.tests[self.current_test]

        if not test["attacker_tag"]:
            units = bot.all_own_units.of_type(self.unit_type)
            if units:
                test["attacker_tag"] = units.first.tag
                test["attacker_spawned"] = True
                return False, False
            elif not test["attacker_spawned"]:
                test["attacker_spawned"] = True
                attacker_pos = bot.start_location.towards(bot.game_info.map_center, 2)
                await bot.client.debug_create_unit([[self.unit_type, 1, attacker_pos, bot.player_id]])
                return False, False
            else:
                return False, False

        attacker = bot.all_units.find_by_tag(test["attacker_tag"])

        if not attacker and self.unit_type != UnitTypeId.BANELING:
            print(f"❌ {self.unit_type.name} Attacker killed, target {test['target_type']}. Can't test dmg")
            data = bot.game_data.units[self.unit_type.value]
            weapons = data._proto.weapons
            debug_weapons(weapons)
            return True, True

        if test["target_tag"] is None and attacker:
            target_type = test["target_type"]
            if not test["target_spawned"]:
                if self.unit_type in [UnitTypeId.WIDOWMINEBURROWED, UnitTypeId.INTERCEPTOR]:
                    player_id = 2
                    target_pos = attacker.position.towards(bot.game_info.map_center, 7)
                else:
                    player_id = 1
                    target_pos = attacker.position.towards(bot.game_info.map_center, 2)
                await bot.client.debug_create_unit([[target_type, 1, target_pos, player_id]])
                test["target_spawned"] = True
            enemy_units = bot.all_units.of_type(target_type).filter(lambda unit: unit.tag != attacker.tag)
            if enemy_units:
                enemy_unit = enemy_units.first
                test["target_tag"] = enemy_unit.tag
            else:
                return False, False

        target = bot.all_units.find_by_tag(test["target_tag"])

        if not target:
            print(f"❌ {self.unit_type.name} Target {test['target_type']} killed, can't test dmg")
            debug_weapons(weapons)
            return True, True

        if self.unit_type == UnitTypeId.BROODLORD:
            alive_tags = [u.tag for u in bot.all_own_units if u.type_id == UnitTypeId.BROODLING]
            if alive_tags:
                await bot.client.debug_kill_unit(alive_tags)

        if not self.started:
            self.started = True
            self.start_hp = target.health_max + target.shield_max
            self.wait_frames = 0

        if attacker:
            if target.owner_id == 1:
                if target.is_flying:
                    move_range = attacker.air_range * 0.8
                else:
                    move_range = attacker.ground_range * 0.8
                target.move(attacker.position.towards(bot.game_info.map_center, move_range))
            if attacker.is_idle or attacker.order_target != target.tag:
                attacker.attack(target)

        hp_now = target.health + target.shield
        if hp_now < self.start_hp:
            self.wait_frames += 1
            # NOTE: Protoss shield does not consider armor
            # NOTE: Widow mine damage ignores armor
            if self.unit_type == UnitTypeId.WIDOWMINEBURROWED:
                armor = 0
            else:
                armor = target.armor
            dmg = self.start_hp - hp_now + (armor * test["attacks"])
            if abs(dmg - test["expected_damage"]) > 0.1 * test["attacks"]:
                if self.wait_frames <= test["attacks"] * 5:
                    return False, False
                data = bot.game_data.units[self.unit_type.value]
                weapons = data._proto.weapons
                debug_weapons(weapons)
                print(
                    f"❌ {self.unit_type.name} wrong damage vs {target.type_id.name} expected {test['expected_damage']}, got {dmg}")
                return True, True
            print(f"✅ {self.unit_type.name} damage OK: {test['expected_damage']}")
            self.current_test += 1
            self.started = False
            await bot.client.debug_kill_unit([target.tag])
            return False, False

        if self.wait_frames < test["attacks"] * 5:
            return False, False

        print(f"⚠️ {self.unit_type.name} attack timeout on {target.type_id.name}")
        self.current_test += 1
        self.started = False
        return False, True


class WeaponBuffValidator(UnitValidator):
    def __init__(self, unit_type: UnitTypeId):
        super().__init__(unit_type)
        self.configs = {
            UnitTypeId.VOIDRAY: {"ability": AbilityId.EFFECT_VOIDRAYPRISMATICALIGNMENT,
                                 "buff": BuffId.VOIDRAYSWARMDAMAGEBOOST},
            UnitTypeId.ORACLE: {"ability": AbilityId.BEHAVIOR_PULSARBEAMON, "buff": BuffId.ORACLEWEAPON},
        }
        self.activated = False
        self.wait_steps = 0

    async def create(self, bot):
        await bot.client.debug_create_unit([[self.unit_type, 1, bot.start_location, bot.player_id]])

    async def prepare(self, bot):
        units = bot.all_units.of_type(self.unit_type)
        return bool(units)

    async def validate(self, bot):
        units = bot.all_units.of_type(self.unit_type)
        if not units:
            return False, False
        unit = units.first
        if not self.activated:
            ability = self.configs[self.unit_type]["ability"]
            unit(ability)
            self.activated = True
            print(f"Activated {ability.name} on {self.unit_type.name}")
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
            print(f"✅ {self.unit_type.name} weapons OK, buffs {list(unit.buffs)}")
            debug_weapons(weapons)
        else:
            print(f"❌ {self.unit_type.name} weapons or buffs mismatch {list(unit.buffs)}")
            debug_weapons(weapons)
        return True, actual != expected and has_buff


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
        self.prepare_load = True
        self.found_buffs = set[BuffId]()
        self.bunker_tag = None
        self.helper_tags = []
        self.helpers_spawned = False
        self.any_missmatch = False

    async def create(self, bot):
        spawn_data = [[self.unit_type, 1, bot.start_location, bot.player_id]]
        for unit_type, count in self.configs:
            spawn_data.append([unit_type, count, bot.start_location, bot.player_id])
        await bot.client.debug_create_unit(spawn_data)
        return []

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

        if self.prepare_load:
            helpers = bot.all_units.of_type(unit_type).take(self.current_load_idx)
            if len(helpers) >= self.current_load_idx:
                self.helper_tags = [u.tag for u in helpers]
                self.prepare_load = False
            return False, False
        else:
            helpers = bot.all_units.tags_in(self.helper_tags)
            if helpers:
                unit_to_load = helpers.first
                bunker(AbilityId.LOAD_BUNKER, unit_to_load)
                return False, False
            buffs = [buff for buff in bunker.buffs if buff not in self.found_buffs]
            if len(buffs) < 1:
                return False, False

        if len(bunker.buffs) > 1:
            print(f"❌ {unit_type.name} bunker buff missmatch: {len(bunker.buffs)}/1 {list(bunker.buffs)}")
        self.found_buffs.update(bunker.buffs)
        self.prepare_load = True
        self.current_load_idx += 1
        bunker(AbilityId.UNLOADALL_BUNKER)
        return False, False


class ValidatorManager:
    def __init__(self, bot):
        self.validators = {
            UnitTypeId.VOIDRAY: WeaponBuffValidator,
            UnitTypeId.ORACLE: WeaponBuffValidator,
            UnitTypeId.BUNKER: BunkerValidator,
        }

    def get_validator(self, unit_type):
        cls = self.validators.get(unit_type, WeaponValidator)
        return cls(unit_type)


class WeaponTestBot(BotAI):
    def __init__(self, validation_timeout=300):
        super().__init__()
        self.unit_types = list(EXPECTED_WEAPONS.keys())
        self.current_index = 0
        self.validation_timeout = validation_timeout
        self.current_validator = None
        self.cleanup_pending = True
        self.done = False
        self.quit = False
        self.missmatches = 0
        self.manager = ValidatorManager(self)
        self.units_ground = []
        self.units_air = []
        self.units_by_attribute = {}

    def build_unit_attribute_index(self):
        if self.units_ground:
            return

        self.units_ground = []
        self.units_air = []
        self.units_by_attribute = {}

        ground_list = []
        air_list = []

        for ut in self.unit_types:
            proto = self.game_data.units[ut.value]._proto

            if proto.armor != 0 and proto.race == 3:
                continue
            if ut in SKIP_TARGET_UNITS:
                continue

            supply = proto.food_required

            if ut in FLYING_TYPES:
                air_list.append((ut, supply))
            else:
                ground_list.append((ut, supply))

            for attr_val in proto.attributes:
                self.units_by_attribute.setdefault(Attribute(attr_val), []).append(ut)

        ground_list.sort(key=lambda x: x[1], reverse=True)
        air_list.sort(key=lambda x: x[1], reverse=True)

        self.units_ground = [ut for ut, hp in ground_list]
        self.units_air = [ut for ut, hp in air_list]

        for attr, lst in self.units_by_attribute.items():
            lst.sort(
                key=lambda ut: (
                        self.game_data.units[ut.value]._proto.food_required
                ),
                reverse=True,
            )


    def pick_unit_without_attribute_no_armor(self, target_type, skip_attributes=None):
        if skip_attributes is None:
            skip_attributes = []

        if target_type == TargetType.Ground:
            pool = self.units_ground
        elif target_type == TargetType.Air:
            pool = self.units_air
        else:
            pool = self.units_ground + self.units_air

        for ut in pool:
            proto = self.game_data.units[ut.value]._proto
            if any(attr in proto.attributes for attr in skip_attributes):
                continue
            return ut

        return None

    def pick_unit_with_attribute_no_armor(self, target_type, attr):
        candidates = self.units_by_attribute.get(attr, [])
        for ut in candidates:
            proto = self.game_data.units[ut.value]._proto
            if proto.armor != 0:
                continue
            if target_type == TargetType.Ground and ut not in self.units_ground:
                continue
            if target_type == TargetType.Air and ut not in self.units_air:
                continue
            return ut
        return None

    async def cleanup(self) -> bool:
        alive_tags = [u.tag for u in self.all_units if u.type_id != UnitTypeId.COMMANDCENTER
                      and (u.is_mine or u.is_enemy)]
        if alive_tags:
            await self.client.debug_kill_unit(alive_tags)
            return False

        return True

    async def on_start(self):
        self.client.game_step = 1

    async def on_step(self, iteration: int):
        if self.quit:
            # Waiting game to end
            return
        if self.done:
            await self.client.leave()
            self.quit = True
            return


        self.build_unit_attribute_index()

        if self.cleanup_pending:
            if await self.cleanup():
                self.cleanup_pending = False
            else:
                return

        if not self.current_validator:
            if self.current_index >= len(self.unit_types):
                if self.missmatches > 0:
                    print(f"❌ Weapon tests failed {self.missmatches} in {self.time} seconds.")
                else:
                    print(f"✅ Weapon test completed in {self.time} seconds.")
                self.done = True
                return
            target = self.unit_types[self.current_index]
            self.current_index += 1
            validator = self.manager.get_validator(target)
            await validator.create(self)
            self.current_validator = (validator, iteration)

        validator, start_loop = self.current_validator
        if validator and start_loop + self.validation_timeout <= iteration:
            print(f"❌ Timeout: {validator.unit_type.name}")
            self.missmatches += 1
            self.cleanup_pending = True
            self.current_validator = None
            return
        ready = await validator.prepare(self)
        if not ready:
            return
        done, failed = await validator.validate(self)
        if not done:
            return
        if failed:
            print(f"❌ {validator.unit_type} Validator failed.")
            self.missmatches += 1
        self.cleanup_pending = True
        self.current_validator = None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", type=str, default="PylonAIE_5_0_14")
    parser.add_argument("--timeout", type=int, default=1120)
    args = parser.parse_args()

    bot = WeaponTestBot(validation_timeout=args.timeout)
    run_game(maps.get(args.map),
             [Bot(Race.Terran, bot), Bot(Race.Terran, LoserBot())],
             realtime=False)
    sys.exit(-1 if bot.missmatches > 0 else 0)


if __name__ == "__main__":
    main()
