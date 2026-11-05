import json
import threading
import unittest
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from LeaderboardAPI import (
    LeaderboardHTTPServer,
    build_leaderboard_snapshot,
)


class LeaderboardAPITests(unittest.TestCase):
    def setUp(self):
        self.server = LeaderboardHTTPServer(
            ("127.0.0.1", 0),
            "test-token-that-is-long-enough-123456",
            lambda: {"modes": [{"id": "deathmatch", "players": []}]},
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
            kwargs={"poll_interval": 0.01},
        )
        self.thread.start()
        self.addCleanup(self.thread.join, 2)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def _request(self, path, token=None):
        url = f"http://127.0.0.1:{self.server.server_port}{path}"
        headers = {}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        return urlopen(Request(url, headers=headers), timeout=2)

    def test_leaderboard_requires_bearer_token(self):
        with self.assertRaises(HTTPError) as error:
            self._request("/api/leaderboard")
        self.assertEqual(error.exception.code, 401)
        error.exception.close()

    def test_authenticated_request_returns_current_snapshot(self):
        with self._request(
            "/api/leaderboard",
            "test-token-that-is-long-enough-123456",
        ) as response:
            self.assertEqual(response.status, 200)
            snapshot = json.loads(response.read().decode("utf-8"))
        self.assertEqual(snapshot["modes"][0]["id"], "deathmatch")

    def test_unknown_path_is_not_exposed(self):
        with self.assertRaises(HTTPError) as error:
            self._request("/other")
        self.assertEqual(error.exception.code, 404)
        error.exception.close()

    def test_snapshot_sorts_verified_kills_for_each_active_mode(self):
        modes = (
            SimpleNamespace(mode_id="flagdown", label="플래그다운"),
            SimpleNamespace(mode_id="debug", label="연습 모드"),
        )
        snapshot = build_leaderboard_snapshot(
            modes,
            {"flagdown"},
            {"flagdown": ("p1", "p2")},
            {
                "p1": {"name": "플레이어 A"},
                "p2": {"name": "플레이어 B"},
            },
            {"flagdown": {"kill_scores": {"p1": 2, "p2": 5}}},
            updated_at=123,
        )
        self.assertEqual(snapshot["updated_at"], 123)
        self.assertEqual(
            snapshot["modes"][0]["players"],
            [
                {"rank": 1, "name": "플레이어 B", "kills": 5},
                {"rank": 2, "name": "플레이어 A", "kills": 2},
            ],
        )


if __name__ == "__main__":
    unittest.main()
