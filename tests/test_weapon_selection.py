import unittest

from Weapon import SPECIAL_CRATE_WEAPONS, next_special_weapon_id


class SpecialWeaponSelectionTests(unittest.TestCase):
    def test_practice_selection_cycles_in_crate_order(self):
        weapon_ids = tuple(SPECIAL_CRATE_WEAPONS)
        self.assertGreater(len(weapon_ids), 1)
        self.assertEqual(next_special_weapon_id(None), weapon_ids[0])

        for current, following in zip(weapon_ids, weapon_ids[1:] + weapon_ids[:1]):
            with self.subTest(current=current):
                self.assertEqual(next_special_weapon_id(current), following)

    def test_unknown_selection_starts_at_first_crate_weapon(self):
        self.assertEqual(
            next_special_weapon_id("unknown"),
            next(iter(SPECIAL_CRATE_WEAPONS)),
        )


if __name__ == "__main__":
    unittest.main()
