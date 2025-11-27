import random

from sc2.ids.unit_typeid import UnitTypeId

from sc2.bot_ai import BotAI


class LoserBot(BotAI):
    async def on_step(self, iteration):
        alive_tags = [u.tag for u in self.all_own_units if u.type_id == UnitTypeId.SCV]
        if alive_tags:
            await self.client.debug_kill_unit(alive_tags)
            return
        for unit in self.all_own_units:
            if unit.is_structure:
                continue
            if not self.enemy_units:
                continue
            closest_enemy = self.enemy_units.closest_to(unit)
            if not closest_enemy:
                continue
            if unit.is_flying:
                distance_to_keep = closest_enemy.air_range
            else:
                distance_to_keep = unit.ground_range
            unit.move(closest_enemy.position.random_on_distance(distance_to_keep * .8))
