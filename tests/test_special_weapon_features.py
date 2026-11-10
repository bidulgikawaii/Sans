import unittest

from Config import (
    BLACK_HOLE_RADIUS,
    PLASMA_BEAM_DURATION_MS,
    PLASMA_BEAM_WIDTH,
    PLASMA_DAMAGE,
    PLASMA_RANGE,
)
from Weapon import SPECIAL_CRATE_WEAPONS
from SkillAndSlot import (
    SKILL_BOOK,
    add_skill_to_inventory,
    owned_skills,
    remove_skill_from_inventory,
)


class SpecialWeaponFeatureTests(unittest.TestCase):
    def test_golden_revolver_is_a_single_use_projectile_weapon(self):
        weapon = SPECIAL_CRATE_WEAPONS["Revolver_golden"]

        self.assertTrue(weapon.projectile)
        self.assertEqual(weapon.magazine_size, 1)
        self.assertEqual(weapon.reserve_ammo, 0)
        self.assertEqual(weapon.damage, 99)

    def test_spirit_trial_is_registered_as_an_equipable_skill(self):
        self.assertIn("영혼의 시험", SKILL_BOOK)
        self.assertTrue(add_skill_to_inventory("영혼의 시험"))
        self.assertIn("영혼의 시험", owned_skills)
        self.assertTrue(remove_skill_from_inventory("영혼의 시험"))

    def test_ultimate_laser_has_sustained_range_and_damage(self):
        self.assertGreaterEqual(PLASMA_BEAM_DURATION_MS, 2000)
        self.assertGreater(PLASMA_BEAM_WIDTH, 9)
        self.assertGreater(PLASMA_DAMAGE, 17)
        self.assertGreater(PLASMA_RANGE, 950)

    def test_black_hole_radius_is_larger_than_original_radius(self):
        self.assertGreater(BLACK_HOLE_RADIUS, 32 * 4)


if __name__ == "__main__":
    unittest.main()
