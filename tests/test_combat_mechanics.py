import unittest

from CombatMechanics import (
    apply_shield_activation,
    is_suicide_hit,
    resolve_hit_weapon_id,
    spirit_linked_body_damage,
)


class ShieldActivationTests(unittest.TestCase):
    def test_delayed_token_does_not_remove_active_shield(self):
        self.assertEqual(
            apply_shield_activation(3, 65, 2, 100, 100),
            (3, 65),
        )

    def test_new_token_activates_full_shield_for_living_player(self):
        self.assertEqual(
            apply_shield_activation(3, 0, 4, 100, 100),
            (4, 100),
        )

    def test_dead_player_cannot_activate_shield(self):
        self.assertEqual(
            apply_shield_activation(3, 0, 4, 0, 100),
            (3, 0),
        )

    def test_only_explicit_self_destruct_is_labeled_as_suicide(self):
        self.assertTrue(is_suicide_hit("player", "player", "자폭"))
        self.assertFalse(is_suicide_hit("player", "player", None))
        self.assertFalse(is_suicide_hit("attacker", "victim", "자폭"))

    def test_spirit_clone_transfers_only_thirty_percent_to_linked_body(self):
        damage, remainder = spirit_linked_body_damage(25)
        self.assertEqual(damage, 7)
        damage, remainder = spirit_linked_body_damage(25, remainder)
        self.assertEqual(damage, 8)
        self.assertEqual(remainder, 0)

    def test_verified_bullet_controls_kill_weapon_attribution(self):
        weapon_configs = {"rifle": object(), "knife": object()}

        self.assertEqual(
            resolve_hit_weapon_id(
                "rifle", "knife", "pistol", weapon_configs, "pistol"
            ),
            "knife",
        )

    def test_unverified_hit_uses_reported_weapon_before_equipped_weapon(self):
        weapon_configs = {"rifle": object(), "knife": object()}

        self.assertEqual(
            resolve_hit_weapon_id(
                "knife", None, "rifle", weapon_configs, "pistol"
            ),
            "knife",
        )


if __name__ == "__main__":
    unittest.main()
