import unittest

from GoldenRevolverEffects import (
    AIM_DURATION_MS,
    EFFECT_DURATION_MS,
    SHATTER_PAUSE_DURATION_MS,
    SHATTER_PAUSE_FRAME_INDEX,
    aim_lock_position,
    shatter_frame_index,
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

    def test_eighteenth_frame_holds_for_configured_duration(self):
        frame_count = 60
        pause_start = round(1400 * (SHATTER_PAUSE_FRAME_INDEX + 1) / frame_count)

        self.assertEqual(shatter_frame_index(pause_start, frame_count), 17)
        self.assertEqual(
            shatter_frame_index(
                pause_start + SHATTER_PAUSE_DURATION_MS - 1, frame_count
            ),
            17,
        )
        self.assertGreater(
            shatter_frame_index(
                pause_start + SHATTER_PAUSE_DURATION_MS, frame_count
            ),
            17,
        )
        self.assertEqual(EFFECT_DURATION_MS, 3200)


if __name__ == "__main__":
    unittest.main()
