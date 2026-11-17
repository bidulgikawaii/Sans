import unittest

from Config import (
    BULLET_MAX_TRAVEL_DISTANCE,
    BLACK_HOLE_RADIUS,
    BLACK_HOLE_DAMAGE,
    BOMB_DAMAGE,
    BOMB_DELAY_MS,
    PLASMA_CHARGE_DURATION_MS,
    PLASMA_BEAM_DURATION_MS,
    PLASMA_BEAM_WIDTH,
    PLASMA_DAMAGE,
    PLASMA_RANGE,
    FLAGDOWN_MAP_HEIGHT_TILES,
    FLAGDOWN_MAP_WIDTH_TILES,
    FPS,
    PLAYER_MAX_HP,
    SHIELD_HP,
)
from Weapon import SPECIAL_CRATE_WEAPONS, WEAPONS
from Bullet import Bullet
from GoldenRevolverEffects import GOLDEN_BULLET_MAX_SPEED_MULTIPLIER
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
        self.assertGreaterEqual(weapon.damage, PLAYER_MAX_HP + SHIELD_HP)
        self.assertLess(weapon.fire_interval, 0.45)

    def test_projectile_lifetimes_are_reduced_and_bounded(self):
        self.assertLess(WEAPONS["sniper"].bullet_lifetime, float("inf"))
        self.assertLess(
            SPECIAL_CRATE_WEAPONS["Revolver_golden"].bullet_lifetime, 0.3
        )
        self.assertGreater(WEAPONS["sniper"].bullet_speed, 40)
        map_short_edge = min(
            FLAGDOWN_MAP_WIDTH_TILES, FLAGDOWN_MAP_HEIGHT_TILES
        ) * 32
        for weapon_id, weapon in WEAPONS.items():
            if not weapon.projectile and weapon_id not in (
                "blackhole_generator",
                "Revolver_golden",
            ):
                continue
            maximum_speed = weapon.bullet_speed
            if weapon_id == "Revolver_golden":
                maximum_speed *= GOLDEN_BULLET_MAX_SPEED_MULTIPLIER
            self.assertLess(
                maximum_speed * FPS * weapon.bullet_lifetime,
                map_short_edge,
                weapon_id,
            )
        self.assertLess(BULLET_MAX_TRAVEL_DISTANCE, map_short_edge)

    def test_spirit_bullet_is_registered_as_an_equipable_skill(self):
        self.assertIn("영혼탄환", SKILL_BOOK)
        self.assertTrue(add_skill_to_inventory("영혼탄환"))
        self.assertIn("영혼탄환", owned_skills)
        self.assertTrue(remove_skill_from_inventory("영혼탄환"))

    def test_shotgun_uses_a_round_pellet_sprite(self):
        pellet = Bullet(4, weapon_id="shotgun")
        self.assertEqual(pellet.surface.get_width(), pellet.surface.get_height())

    def test_ultimate_laser_has_sustained_range_and_damage(self):
        self.assertGreaterEqual(PLASMA_CHARGE_DURATION_MS, 2000)
        self.assertGreaterEqual(PLASMA_BEAM_DURATION_MS, 2000)
        self.assertGreater(PLASMA_BEAM_WIDTH, 9)
        self.assertGreater(PLASMA_DAMAGE, 17)
        self.assertGreater(PLASMA_RANGE, 950)

    def test_black_hole_radius_is_larger_than_original_radius(self):
        self.assertEqual(BLACK_HOLE_RADIUS, 32 * 16)
        self.assertGreater(BLACK_HOLE_DAMAGE, 35)

    def test_bomb_explodes_faster_and_deals_more_damage(self):
        self.assertLessEqual(BOMB_DELAY_MS, 300)
        self.assertGreater(BOMB_DAMAGE, 30)


if __name__ == "__main__":
    unittest.main()
