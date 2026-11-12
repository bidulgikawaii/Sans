import unittest

from GameRendering import linked_clone_opacity


class SpiritTrialLifetimeTests(unittest.TestCase):
    def test_clone_is_visible_before_fade_period(self):
        self.assertGreater(linked_clone_opacity(4999, 0), 0)

    def test_clone_blinks_after_five_seconds(self):
        self.assertGreater(linked_clone_opacity(5200, 240), 0)
        self.assertEqual(linked_clone_opacity(5200, 360), 0)

    def test_clone_disappears_after_six_seconds(self):
        self.assertEqual(linked_clone_opacity(6000, 120), 0)


if __name__ == "__main__":
    unittest.main()
