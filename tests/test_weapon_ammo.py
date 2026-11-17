import unittest

from Weapon import WeaponState, WEAPONS


class WeaponAmmoTests(unittest.TestCase):
    def test_unlimited_ammo_keeps_magazine_full_and_allows_firing(self):
        weapon = WeaponState("rifle")
        weapon.reloading = True
        weapon.set_unlimited_ammo(True)
        weapon.magazine_ammo = 0

        self.assertTrue(weapon.can_fire())
        self.assertFalse(weapon.is_reloading_now())
        weapon.consume_round()
        self.assertEqual(weapon.magazine_ammo, 0)
        self.assertFalse(weapon.start_reload())

    def test_rifle_range_is_shorter_without_changing_bullet_speed(self):
        rifle = WEAPONS["rifle"]

        self.assertEqual(rifle.bullet_speed, 23.0)
        self.assertLess(rifle.bullet_lifetime, 1.5)


if __name__ == "__main__":
    unittest.main()
