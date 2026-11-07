import json
import unittest

from LeaderboardClient import parse_leaderboard_snapshot


class LeaderboardClientTests(unittest.TestCase):
    def test_snapshot_is_flattened_by_mode_and_player(self):
        rows = parse_leaderboard_snapshot(
            json.dumps({
                "modes": [{
                    "id": "deathmatch",
                    "label": "데스매치",
                    "players": [{"rank": 1, "name": "플레이어", "kills": 4}],
                }],
            }).encode("utf-8")
        )
        self.assertEqual(
            rows,
            [("데스매치", "1", "플레이어", "4")],
        )

    def test_invalid_snapshot_shape_raises_clear_error(self):
        with self.assertRaisesRegex(ValueError, "형식"):
            parse_leaderboard_snapshot(b'{"modes":{}}')


if __name__ == "__main__":
    unittest.main()
