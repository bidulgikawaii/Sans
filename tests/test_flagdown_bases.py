import unittest

from Config import FLAGDOWN_MAP_WIDTH_TILES
from FlagdownBases import (
    flagdown_base_bounds,
    intersects_enemy_flagdown_base,
)


class FlagdownBaseTests(unittest.TestCase):
    def test_base_bounds_cover_four_tiles_around_team_spawn_edge(self):
        blue_base = flagdown_base_bounds(0)
        red_base = flagdown_base_bounds(1)

        self.assertEqual(blue_base[0], (FLAGDOWN_MAP_WIDTH_TILES - 4) * 32)
        self.assertEqual(blue_base[2], 4 * 32)
        self.assertEqual(red_base[0], 0)
        self.assertEqual(red_base[2], 4 * 32)
        self.assertEqual(blue_base[1:], red_base[1:])

    def test_players_cannot_overlap_the_opponent_base_but_can_enter_own(self):
        self.assertTrue(intersects_enemy_flagdown_base(0, 40, 300, 72, 72))
        self.assertFalse(intersects_enemy_flagdown_base(0, 1000, 300, 72, 72))
        self.assertTrue(intersects_enemy_flagdown_base(1, 2950, 300, 72, 72))
        self.assertFalse(intersects_enemy_flagdown_base(1, 1000, 300, 72, 72))

    def test_invalid_positions_are_rejected(self):
        self.assertTrue(
            intersects_enemy_flagdown_base(0, float("nan"), 0, 72, 72)
        )


if __name__ == "__main__":
    unittest.main()
