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
        self.started = False
        self.start_at = None
        self.started_at = None
        self.practice_players = set()
        self.match_normal_player_ids = set()

    def _update_start_state(self):
        if self.start_at is not None and time.monotonic() >= self.start_at:
            self.started = True
            self.started_at = time.monotonic()
            self.start_at = None
            # 경기 도중 관전 전환이나 화면별 표시 필터가 바뀌어도
            # 승리 판정 대상은 시작 당시 일반전 참가자로 유지합니다.
            self.match_normal_player_ids = {
                player_id
                for player_id, mode in self.modes.items()
                if mode == GAME_MODE_NORMAL and player_id not in self.practice_players
            }

    def join(self, player_id, mode, debug_enabled=False):
        self._update_start_state()
        if player_id not in self.modes and len(self.modes) >= MAX_PLAYERS:
            return False
        if (self.started or self.start_at is not None) and player_id not in self.modes:
            return False
        if mode not in (GAME_MODE_NORMAL, GAME_MODE_DEBUG):
            mode = GAME_MODE_NORMAL
        same_mode = self.modes.get(player_id) == mode
        self.modes[player_id] = mode
        if not same_mode:
            self.ready_players.discard(player_id)
        if debug_enabled or mode == GAME_MODE_DEBUG:
            self.practice_players.add(player_id)
        else:
            self.practice_players.discard(player_id)
        return True

    def set_ready(self, player_id, ready):
        self._update_start_state()
        if player_id not in self.modes:
            return False
        if ready:
            self.ready_players.add(player_id)
        else:
            self.ready_players.discard(player_id)

        mode = self.modes.get(player_id, GAME_MODE_NORMAL)
        min_required = 1 if mode == GAME_MODE_DEBUG else NORMAL_MATCH_MIN_PLAYERS
        all_ready = bool(self.modes) and len(self.ready_players) == len(self.modes)
        enough_players = len(self.modes) >= min_required

        if self.start_at is None and all_ready and enough_players:
            self.start_at = time.monotonic() + LOBBY_START_DELAY_MS / 1000
        elif not all_ready or not enough_players:
            self.start_at = None
        return True

    def leave(self, player_id):
        self.modes.pop(player_id, None)
        self.ready_players.discard(player_id)
        self.practice_players.discard(player_id)
        if not self.modes:
            self.started = False
            self.start_at = None
            self.started_at = None

    def finish_match(self):
        """경기 결과가 확정되면 다음 대기열을 위한 상태를 비웁니다."""
        self.modes.clear()
        self.ready_players.clear()
        self.practice_players.clear()
        self.match_normal_player_ids.clear()
        self.started = False
        self.start_at = None
        self.started_at = None

    def active_player_ids(self):
        return set(self.modes)

    def visible_player_ids(self, player_id):
        """훈련장 플레이어는 일반전 스냅샷과 서로 섞이지 않게 합니다."""
        active_ids = self.active_player_ids()
        if player_id in self.practice_players:
            return active_ids & self.practice_players
        return active_ids - self.practice_players

    def zone_enabled_for(self, player_id):
        return player_id not in self.practice_players

    def status(self, player_id=None):
        self._update_start_state()
        mode = GAME_MODE_DEBUG if GAME_MODE_DEBUG in self.modes.values() else GAME_MODE_NORMAL
        countdown_ms = max(0, round((self.start_at - time.monotonic()) * 1000)) if self.start_at else 0
        elapsed_ms = (
            max(0, round((time.monotonic() - self.started_at) * 1000))
            if self.started_at else 0
        )
        ready_count = len(self.ready_players)
        total_players = len(self.modes)
        min_required = 1 if mode == GAME_MODE_DEBUG else NORMAL_MATCH_MIN_PLAYERS
        all_ready = bool(total_players) and ready_count == total_players and total_players >= min_required
        return {
            "type": "lobby_status",
            "count": total_players,
            "max_players": MAX_PLAYERS,
            "mode": mode,
            "started": self.started,
            "accepting_players": not self.started and self.start_at is None,
            "countdown_ms": countdown_ms,
            "elapsed_ms": elapsed_ms,
            "ready_count": ready_count,
            "all_ready": all_ready,
            "confirmed": player_id in self.ready_players if player_id is not None else False,
        }
