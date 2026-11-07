import json
import unittest

from LeaderboardClient import parse_leaderboard_snapshot


class LeaderboardClientTests(unittest.TestCase):
    def test_snapshot_keeps_standings_separate_by_mode(self):
        modes = parse_leaderboard_snapshot(
            json.dumps({
                "modes": [
                    {
                        "id": "deathmatch",
                        "label": "데스매치",
                        "players": [{"rank": 1, "name": "플레이어", "kills": 4}],
                    },
                    {
                        "id": "flagdown",
                        "label": "플래그다운",
                        "players": [{"rank": 1, "name": "다른 플레이어", "kills": 2}],
                    },
                ],
            }).encode("utf-8")
        )
        self.assertEqual(
            modes,
            [
                ("deathmatch", "데스매치", [("1", "플레이어", "4")]),
                ("flagdown", "플래그다운", [("1", "다른 플레이어", "2")]),
            ],
        )

    def test_invalid_snapshot_shape_raises_clear_error(self):
        with self.assertRaisesRegex(ValueError, "형식"):
            parse_leaderboard_snapshot(b'{"modes":{}}')


if __name__ == "__main__":
    unittest.main()
