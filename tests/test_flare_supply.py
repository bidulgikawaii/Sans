import unittest

from Config import (
    DEATHMATCH_FLARE_SUPPLY_TYPES,
    DEATHMATCH_FLARE_UNIQUE_SUPPLY_TYPES,
)
from FlareSupply import select_flare_supply_reward_types
from GameModes import GAME_MODE_DEATHMATCH


class FixedRandom:
    def __init__(self, value):
        self.value = value

    def random(self):
        return self.value


class FlareSupplyTests(unittest.TestCase):
    def test_deathmatch_uses_unique_rewards_below_three_percent(self):
        rewards = select_flare_supply_reward_types(
            GAME_MODE_DEATHMATCH, rng=FixedRandom(0.0299)
        )
        self.assertEqual(rewards, DEATHMATCH_FLARE_UNIQUE_SUPPLY_TYPES)
        self.assertEqual(rewards.count("special_weapon"), 1)
        self.assertEqual(rewards.count("heal"), 2)

    def test_deathmatch_uses_normal_rewards_at_three_percent_boundary(self):
        rewards = select_flare_supply_reward_types(
            GAME_MODE_DEATHMATCH, rng=FixedRandom(0.03)
        )
        self.assertEqual(rewards, DEATHMATCH_FLARE_SUPPLY_TYPES)

    def test_other_modes_keep_ammo_only_flare_rewards(self):
        rewards = select_flare_supply_reward_types(
            "other_mode", rng=FixedRandom(0.0)
        )
        self.assertEqual(rewards, ("flare_ammo",) * 3)


if __name__ == "__main__":
    unittest.main()
