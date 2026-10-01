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
        self.ready_players = set()
        self.started = {GAME_MODE_NORMAL: False, GAME_MODE_DEBUG: False}
        self.start_at = {GAME_MODE_NORMAL: None, GAME_MODE_DEBUG: None}
        self.started_at = {GAME_MODE_NORMAL: None, GAME_MODE_DEBUG: None}
        self.match_player_ids = {GAME_MODE_NORMAL: set(), GAME_MODE_DEBUG: set()}

    def _player_ids(self, mode):
        return {player_id for player_id, player_mode in self.modes.items() if player_mode == mode}

    def _update_start_state(self, mode):
        start_at = self.start_at[mode]
        if start_at is not None and time.monotonic() >= start_at:
            self.started[mode] = True
            self.started_at[mode] = time.monotonic()
            self.start_at[mode] = None
            self.match_player_ids[mode] = self._player_ids(mode)

    def join(self, player_id, mode, debug_enabled=False):
        if mode not in (GAME_MODE_NORMAL, GAME_MODE_DEBUG):
            mode = GAME_MODE_NORMAL
        if debug_enabled:
            mode = GAME_MODE_DEBUG
        self._update_start_state(mode)
        current_mode = self.modes.get(player_id)
        if current_mode != mode and len(self._player_ids(mode)) >= MAX_PLAYERS:
            return False
        if current_mode != mode and (
            self.started[mode] or self.start_at[mode] is not None
        ):
            return False
        if current_mode is not None and current_mode != mode:
            self.ready_players.discard(player_id)
            self.match_player_ids[current_mode].discard(player_id)
        self.modes[player_id] = mode
        return True

    def set_ready(self, player_id, ready):
        mode = self.mode_for(player_id)
        if mode is None:
            return False
        self._update_start_state(mode)
        if ready:
            self.ready_players.add(player_id)
        else:
            self.ready_players.discard(player_id)

        min_required = 1 if mode == GAME_MODE_DEBUG else NORMAL_MATCH_MIN_PLAYERS
        player_ids = self._player_ids(mode)
        ready_count = len(player_ids & self.ready_players)
        all_ready = bool(player_ids) and ready_count == len(player_ids)
        enough_players = len(player_ids) >= min_required

        if self.start_at[mode] is None and all_ready and enough_players:
            self.start_at[mode] = time.monotonic() + LOBBY_START_DELAY_MS / 1000
        elif not all_ready or not enough_players:
            self.start_at[mode] = None
        return True

    def leave(self, player_id):
        mode = self.modes.pop(player_id, None)
        self.ready_players.discard(player_id)
        if mode is not None and not self._player_ids(mode):
            self.started[mode] = False
            self.start_at[mode] = None
            self.started_at[mode] = None
            self.match_player_ids[mode].clear()

    def finish_match(self, mode=GAME_MODE_NORMAL):
        """경기 결과가 확정되면 다음 대기열을 위한 상태를 비웁니다."""
        for player_id in self._player_ids(mode):
            self.modes.pop(player_id, None)
            self.ready_players.discard(player_id)
        self.started[mode] = False
        self.start_at[mode] = None
        self.started_at[mode] = None
        self.match_player_ids[mode].clear()

    def mode_for(self, player_id):
        return self.modes.get(player_id)

    def active_player_ids(self, mode=None):
        return self._player_ids(mode) if mode is not None else set(self.modes)

    def visible_player_ids(self, player_id):
        """훈련장 플레이어는 일반전 스냅샷과 서로 섞이지 않게 합니다."""
        mode = self.mode_for(player_id)
        return self._player_ids(mode) if mode is not None else set()

    def zone_enabled_for(self, player_id):
        return self.mode_for(player_id) == GAME_MODE_NORMAL

    def status(self, player_id=None, mode=None):
        if mode is None:
            mode = self.mode_for(player_id) if player_id is not None else GAME_MODE_NORMAL
        mode = mode or GAME_MODE_NORMAL
        self._update_start_state(mode)
        start_at = self.start_at[mode]
        started_at = self.started_at[mode]
        countdown_ms = max(0, round((start_at - time.monotonic()) * 1000)) if start_at else 0
        elapsed_ms = (
            max(0, round((time.monotonic() - started_at) * 1000))
            if started_at else 0
        )
        player_ids = self._player_ids(mode)
        ready_count = len(player_ids & self.ready_players)
        total_players = len(player_ids)
        min_required = 1 if mode == GAME_MODE_DEBUG else NORMAL_MATCH_MIN_PLAYERS
        all_ready = bool(total_players) and ready_count == total_players and total_players >= min_required
        return {
            "type": "lobby_status",
            "count": total_players,
            "max_players": MAX_PLAYERS,
            "mode": mode,
            "started": self.started[mode],
            "accepting_players": not self.started[mode] and start_at is None,
            "countdown_ms": countdown_ms,
            "elapsed_ms": elapsed_ms,
            "ready_count": ready_count,
            "all_ready": all_ready,
            "confirmed": player_id in self.ready_players if player_id is not None else False,
        }
