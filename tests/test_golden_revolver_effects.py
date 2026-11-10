import unittest

from GoldenRevolverEffects import (
    EFFECT_DURATION_MS,
    SHATTER_PAUSE_DURATION_MS,
    SHATTER_PAUSE_FRAME_INDEX,
    shatter_frame_index,
)


class GoldenRevolverEffectTests(unittest.TestCase):
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
