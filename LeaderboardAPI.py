import hmac
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def build_leaderboard_snapshot(
    game_modes,
    started_modes,
    active_player_ids,
    players,
    match_events,
    updated_at=None,
):
    modes = []
    for definition in game_modes:
        mode = definition.mode_id
        if mode not in started_modes:
            continue
        scores = match_events[mode]["kill_scores"]
        standings = []
        for player_id in active_player_ids.get(mode, ()):
            player = players.get(player_id)
            if player is None:
                continue
            standings.append({
                "name": str(player.get("name", "플레이어")),
                "kills": max(0, int(scores.get(player_id, 0))),
            })
        standings.sort(
            key=lambda player: (-player["kills"], player["name"].casefold())
        )
        modes.append({
            "id": mode,
            "label": definition.label,
            "players": [
                {"rank": index + 1, **player}
                for index, player in enumerate(standings)
            ],
        })
    return {
        "updated_at": int(time.time() * 1000) if updated_at is None else updated_at,
        "modes": modes,
    }


class LeaderboardRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/api/leaderboard":
            self._send_json(404, {"error": "not found"})
            return

        expected = f"Bearer {self.server.api_token}"
        authorization = self.headers.get("Authorization", "")
        if not hmac.compare_digest(authorization, expected):
            self._send_json(401, {"error": "unauthorized"})
            return

        self._send_json(200, self.server.snapshot_provider())

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


class LeaderboardHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, api_token, snapshot_provider):
        self.api_token = api_token
        self.snapshot_provider = snapshot_provider
        super().__init__(address, LeaderboardRequestHandler)
