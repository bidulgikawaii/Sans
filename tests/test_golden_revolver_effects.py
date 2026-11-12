import unittest

import pygame

from GoldenRevolverEffects import (
    AIM_DURATION_MS,
    GOLDEN_BULLET_ACCELERATION_DURATION_MS,
    GOLDEN_BULLET_ACCELERATION_DELAY_MS,
    GOLDEN_BULLET_MAX_SPEED_MULTIPLIER,
    GOLDEN_SEQUENCE_DURATION_MS,
    GOLDEN_SUNSET_DURATION_MS,
    GOLDEN_SUNSET_FADE_MS,
    GOLDEN_TINT_FADE_MS,
    aim_lock_position,
    golden_bullet_speed,
    golden_camera_focus,
    golden_revolver_sunset_alpha,
    golden_revolver_tint_alpha,
    golden_target_timing,
    draw_golden_revolver_sunset,
)


class GoldenRevolverEffectTests(unittest.TestCase):
    def test_aim_lock_moves_to_target_over_aim_duration(self):
        lock = {
            "start_x": 10,
            "start_y": 20,
            "x": 110,
            "y": 220,
            "started_at": 1000,
            "duration_ms": AIM_DURATION_MS,
        }

        self.assertEqual(aim_lock_position(lock, 1000), (10, 20))
        self.assertEqual(aim_lock_position(lock, 1000 + AIM_DURATION_MS // 2), (60, 120))
        self.assertEqual(aim_lock_position(lock, 1000 + AIM_DURATION_MS), (110, 220))

    def test_targets_are_aimed_sequentially_within_the_aim_window(self):
        timings = [
            golden_target_timing(index, 4)
            for index in range(4)
        ]

        self.assertEqual(timings[0], (0, AIM_DURATION_MS // 4))
        self.assertEqual(timings[-1][0] + timings[-1][1], AIM_DURATION_MS)

    def test_camera_focus_tracks_the_currently_aimed_target(self):
        locks = [
            {"x": 100, "y": 120, "started_at": 1000, "until": 1125},
            {"x": 300, "y": 320, "started_at": 1125, "until": 1250},
        ]

        self.assertEqual(golden_camera_focus(locks, 1100), (100, 120))
        self.assertEqual(golden_camera_focus(locks, 1200), (300, 320))
        self.assertIsNone(golden_camera_focus(locks, 1250))

    def test_sunset_tint_fades_in_during_aim_and_out_after_shot(self):
        started_at = 1000
        aim_until = started_at + AIM_DURATION_MS

        self.assertEqual(golden_revolver_tint_alpha(started_at, aim_until, 999), 0)
        self.assertEqual(golden_revolver_tint_alpha(started_at, aim_until, started_at), 0)
        self.assertGreater(
            golden_revolver_tint_alpha(
                started_at, aim_until, started_at + AIM_DURATION_MS // 2
            ),
            0,
        )
        self.assertGreater(
            golden_revolver_tint_alpha(started_at, aim_until, aim_until),
            0,
        )
        self.assertEqual(
            golden_revolver_tint_alpha(
                started_at, aim_until, aim_until + GOLDEN_TINT_FADE_MS
            ),
            0,
        )

    def test_golden_bullet_starts_slow_then_accelerates(self):
        max_speed = 32

        slow_speed = golden_bullet_speed(max_speed, 0)
        after_delay_speed = golden_bullet_speed(
            max_speed, GOLDEN_BULLET_ACCELERATION_DELAY_MS
        )
        fast_speed = golden_bullet_speed(max_speed, 10_000)

        self.assertEqual(slow_speed, after_delay_speed)
        self.assertGreater(fast_speed, slow_speed)
        self.assertEqual(fast_speed, max_speed * GOLDEN_BULLET_MAX_SPEED_MULTIPLIER)
        self.assertEqual(GOLDEN_BULLET_ACCELERATION_DELAY_MS, 0)
        self.assertLess(AIM_DURATION_MS, 600)
        self.assertLess(
            AIM_DURATION_MS + GOLDEN_BULLET_ACCELERATION_DURATION_MS,
            GOLDEN_SEQUENCE_DURATION_MS,
        )

    def test_sunset_effect_fades_in_and_expires_after_firing(self):
        started_at = 1000

        self.assertEqual(GOLDEN_SUNSET_DURATION_MS, 1400)
        self.assertLessEqual(AIM_DURATION_MS, GOLDEN_SEQUENCE_DURATION_MS)
        self.assertEqual(golden_revolver_sunset_alpha(started_at, started_at), 0)
        self.assertGreater(
            golden_revolver_sunset_alpha(started_at, started_at + 180), 0
        )
        self.assertGreater(
            golden_revolver_sunset_alpha(
                started_at,
                started_at + GOLDEN_SUNSET_DURATION_MS - GOLDEN_SUNSET_FADE_MS // 2,
            ),
            0,
        )
        self.assertEqual(
            golden_revolver_sunset_alpha(
                started_at, started_at + GOLDEN_SUNSET_DURATION_MS
            ),
            0,
        )

    def test_sunset_renderer_draws_a_sun_on_the_local_surface(self):
        surface = pygame.Surface((320, 240))
        surface.fill((20, 30, 40))
        overlay = pygame.Surface((320, 240), pygame.SRCALPHA)
        started_at = 1000

        draw_golden_revolver_sunset(surface, overlay, started_at, started_at + 500)

        self.assertNotEqual(surface.get_at((160, 175))[:3], (20, 30, 40))


if __name__ == "__main__":
    unittest.main()
