import time

from Config import (
    GAME_MODE_DEBUG,
    GAME_MODE_NORMAL,
    LOBBY_START_DELAY_MS,
    MAX_PLAYERS,
    NORMAL_MATCH_MIN_PLAYERS,
)


class LobbyState:
    """접속 중인 사용자와 실제 게임 대기열을 분리해 관리합니다."""

    def __init__(self):
        self.modes = {}
        self.started = False
        self.start_at = None
        self.started_at = None
        self.practice_players = set()

    def _update_start_state(self):
        if self.start_at is not None and time.monotonic() >= self.start_at:
            self.started = True
            self.started_at = time.monotonic()
            self.start_at = None

    def join(self, player_id, mode, debug_enabled=False):
        self._update_start_state()
        if (self.started or self.start_at is not None) and player_id not in self.modes:
            return False
        if mode not in (GAME_MODE_NORMAL, GAME_MODE_DEBUG):
            mode = GAME_MODE_NORMAL
        self.modes[player_id] = mode
        if debug_enabled or mode == GAME_MODE_DEBUG:
            self.practice_players.add(player_id)
        else:
            self.practice_players.discard(player_id)
        if self.start_at is None and (
            mode == GAME_MODE_DEBUG
            or len(self.modes) >= MAX_PLAYERS
            or (mode == GAME_MODE_NORMAL and len(self.modes) >= NORMAL_MATCH_MIN_PLAYERS)
        ):
            self.start_at = time.monotonic() + LOBBY_START_DELAY_MS / 1000
        return True

    def leave(self, player_id):
        self.modes.pop(player_id, None)
        self.practice_players.discard(player_id)
        if not self.modes:
            self.started = False
            self.start_at = None
            self.started_at = None

    def active_player_ids(self):
        return set(self.modes)

    def zone_enabled_for(self, player_id):
        return player_id not in self.practice_players

    def status(self):
        self._update_start_state()
        mode = GAME_MODE_DEBUG if GAME_MODE_DEBUG in self.modes.values() else GAME_MODE_NORMAL
        countdown_ms = max(0, round((self.start_at - time.monotonic()) * 1000)) if self.start_at else 0
        elapsed_ms = (
            max(0, round((time.monotonic() - self.started_at) * 1000))
            if self.started_at else 0
        )
        return {
            "type": "lobby_status",
            "count": len(self.modes),
            "max_players": MAX_PLAYERS,
            "mode": mode,
            "started": self.started,
            "accepting_players": not self.started and self.start_at is None,
            "countdown_ms": countdown_ms,
            "elapsed_ms": elapsed_ms,
        }
