import unittest

from MineAuthority import (
    advance_mines,
    register_mine_placements,
    serialize_mines,
)


class MineAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.events = {
            "mines": [],
            "next_mine_id": 1,
            "mine_hit_authorizations": {},
            "mine_blast_events": [],
        }
        self.owner = {"last_mine_request_id": 0}
        self.players = {
            "owner": {"posX": 0, "posY": 0, "hp": 100},
            "enemy": {"posX": 64, "posY": 64, "hp": 100},
            "ally": {"posX": 64, "posY": 64, "hp": 100},
        }
        self.teams = {"owner": 0, "enemy": 1, "ally": 0}

    def place_mine(self, now=0):
        return register_mine_placements(
            self.events,
            self.owner,
            "owner",
            [{"request_id": 1, "x": 100, "y": 100}],
            now,
            1000,
            1000,
            0,
            100,
            2,
        )

    def test_placement_is_deduplicated_and_acknowledged(self):
        self.assertEqual(self.place_mine(), 1)
        self.assertEqual(self.place_mine(), 1)
        self.assertEqual(len(self.events["mines"]), 1)
        serialized = serialize_mines(self.events, 0)[0]
        self.assertEqual(serialized["armed_in_ms"], 100)
        self.assertEqual(serialized["owner_id"], "owner")

    def test_trigger_waits_then_authorizes_enemy_damage_once(self):
        self.place_mine()
        kwargs = dict(
            events=self.events,
            players=self.players,
            active_player_ids={"owner", "enemy", "ally"},
            team_for=self.teams.get,
            mode="flagdown",
            trigger_radius=100,
            blast_radius=120,
            trigger_delay_ms=900,
            damage=10,
        )
        self.assertEqual(advance_mines(now=0.05, **kwargs), [])
        self.assertEqual(advance_mines(now=0.1, **kwargs), [])
        self.assertEqual(len(serialize_mines(self.events, 0.1)), 1)
        self.assertEqual(advance_mines(now=0.999, **kwargs), [])
        hits = advance_mines(now=1.0, **kwargs)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["target_id"], "enemy")
        self.assertEqual(hits[0]["damage"], 10)
        self.assertEqual(
            self.events["mine_hit_authorizations"][(1, "enemy")],
            "owner",
        )
        self.assertEqual(self.events["mines"], [])
        self.assertEqual(len(self.events["mine_blast_events"]), 1)
        self.assertEqual(advance_mines(now=2.0, **kwargs), [])

    def test_invalid_placement_is_acknowledged_but_not_created(self):
        acknowledgement = register_mine_placements(
            self.events,
            self.owner,
            "owner",
            [{"request_id": 1, "x": float("inf"), "y": 100}],
            0,
            1000,
            1000,
            0,
            100,
            2,
        )
        self.assertEqual(acknowledgement, 1)
        self.assertEqual(self.events["mines"], [])

    def test_invalid_player_position_does_not_crash_mine_processing(self):
        self.place_mine()
        self.players["enemy"]["posX"] = None
        self.assertEqual(
            advance_mines(
                self.events,
                self.players,
                {"owner", "enemy", "ally"},
                self.teams.get,
                "flagdown",
                0.2,
                100,
                120,
                900,
                10,
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
