import unittest

from Config import MINE_BLAST_RADIUS, MINE_TRIGGER_DELAY_MS
from MineMechanics import (
    mine_blast_contains,
    mine_is_due_to_detonate,
    trigger_mine,
)


class MineMechanicsTests(unittest.TestCase):
    def test_mine_detonation_delay_is_shortened(self):
        self.assertEqual(MINE_TRIGGER_DELAY_MS, 600)

    def test_mine_flashes_for_delay_before_detonating(self):
        mine = {"armed_at": 100}
        self.assertFalse(trigger_mine(mine, 99))
        self.assertTrue(trigger_mine(mine, 100))
        self.assertEqual(mine["detonates_at"], 100 + MINE_TRIGGER_DELAY_MS)
        self.assertFalse(mine_is_due_to_detonate(mine, 100))
        self.assertFalse(
            mine_is_due_to_detonate(mine, 100 + MINE_TRIGGER_DELAY_MS - 1)
        )
        self.assertTrue(
            mine_is_due_to_detonate(mine, 100 + MINE_TRIGGER_DELAY_MS)
        )

    def test_triggered_mine_cannot_be_triggered_twice(self):
        mine = {"armed_at": 0}
        self.assertTrue(trigger_mine(mine, 50))
        detonates_at = mine["detonates_at"]
        self.assertFalse(trigger_mine(mine, 60))
        self.assertEqual(mine["detonates_at"], detonates_at)

    def test_blast_hits_targets_inside_radius_only(self):
        mine = {"x": 20, "y": 30}
        self.assertTrue(mine_blast_contains(mine, 20, 30))
        self.assertTrue(mine_blast_contains(mine, 20 + MINE_BLAST_RADIUS, 30))
        self.assertFalse(
            mine_blast_contains(mine, 21 + MINE_BLAST_RADIUS, 30)
        )


if __name__ == "__main__":
    unittest.main()
