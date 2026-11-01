import time
import random

from Config import (
    GAME_MODE_DEBUG,
    GAME_MODE_FLAGDOWN,
    GAME_MODE_NORMAL,
    FLAGDOWN_TEAM_SPAWN_TILES,
    LOBBY_START_DELAY_MS,
    MAX_PLAYERS,
)
from GameModes import get_game_mode, get_game_modes, is_game_mode_registered


class LobbyState:
    """접속 중인 사용자와 실제 게임 대기열을 분리해 관리합니다."""

    def __init__(self):
        self.modes = {}
        self.ready_players = set()
        mode_ids = (mode.mode_id for mode in get_game_modes())
        self.started = {mode_id: False for mode_id in mode_ids}
        self.start_at = {mode_id: None for mode_id in self.started}
        self.started_at = {mode_id: None for mode_id in self.started}
        self.match_player_ids = {mode_id: set() for mode_id in self.started}
        self.world_seeds = {mode_id: None for mode_id in self.started}
        self.world_weather = {mode_id: None for mode_id in self.started}
        self.team_assignments = {}
        self.team_members = {0: [], 1: []}

    def _player_ids(self, mode):
        return {player_id for player_id, player_mode in self.modes.items() if player_mode == mode}

    def _can_start(self, mode):
        player_ids = self._player_ids(mode)
        return (
            len(player_ids) >= get_game_mode(mode).min_players
            and bool(player_ids)
            and player_ids.issubset(self.ready_players)
        )

    def _refresh_start_countdown(self, mode):
        if self.started[mode]:
            return
        if self._can_start(mode):
            if self.start_at[mode] is None:
                self.start_at[mode] = time.monotonic() + LOBBY_START_DELAY_MS / 1000
        else:
            self.start_at[mode] = None

    def _update_start_state(self, mode):
        start_at = self.start_at[mode]
        if start_at is not None and time.monotonic() >= start_at:
            if not self._can_start(mode):
                self.start_at[mode] = None
                return
            self.started[mode] = True
            self.started_at[mode] = time.monotonic()
            self.start_at[mode] = None
            # 시작 시점의 인원만 경기 참가자로 고정해 이후 접속자가 진행 중인 경기에 끼지 못하게 합니다.
            self.match_player_ids[mode] = self._player_ids(mode)
            if mode == GAME_MODE_FLAGDOWN:
                shuffled_ids = list(self.match_player_ids[mode])
                random.SystemRandom().shuffle(shuffled_ids)
                split_at = (len(shuffled_ids) + 1) // 2
                self.team_members = {
                    0: shuffled_ids[:split_at],
                    1: shuffled_ids[split_at:],
                }
                self.team_assignments = {
                    player_id: team_id
                    for team_id, members in self.team_members.items()
                    for player_id in members
                }

    def join(self, player_id, mode, debug_enabled=False):
        if not is_game_mode_registered(mode):
            mode = GAME_MODE_NORMAL
        if debug_enabled:
            mode = GAME_MODE_DEBUG
        self._update_start_state(mode)
        current_mode = self.modes.get(player_id)
        if current_mode != mode and len(self._player_ids(mode)) >= MAX_PLAYERS:
            return False
        if self.started[mode] and (
            current_mode != mode or player_id not in self.match_player_ids[mode]
        ):
            return False
        if current_mode != mode and self.start_at[mode] is not None:
            return False
        if current_mode is not None and current_mode != mode:
            self.ready_players.discard(player_id)
            self.match_player_ids[current_mode].discard(player_id)
        self.modes[player_id] = mode
        if self.world_seeds[mode] is None:
            self.world_seeds[mode] = random.SystemRandom().getrandbits(32)
            self.world_weather[mode] = random.SystemRandom().choice(("rain", "snow"))
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

        self._refresh_start_countdown(mode)
        return True

    def leave(self, player_id):
        mode = self.modes.pop(player_id, None)
        self.ready_players.discard(player_id)
        if mode is None:
            return
        self.match_player_ids[mode].discard(player_id)
        self._refresh_start_countdown(mode)
        if not self._player_ids(mode):
            self.started[mode] = False
            self.start_at[mode] = None
            self.started_at[mode] = None
            self.match_player_ids[mode].clear()
            self.world_seeds[mode] = None
            self.world_weather[mode] = None
            if mode == GAME_MODE_FLAGDOWN:
                self.team_assignments.clear()
                self.team_members = {0: [], 1: []}

    def cancel(self, mode):
        """해당 모드의 대기열과 진행 중 매치를 전체 참가자 대상으로 취소합니다."""
        player_ids = self._player_ids(mode)
        for player_id in player_ids:
            self.modes.pop(player_id, None)
            self.ready_players.discard(player_id)
        self.started[mode] = False
        self.start_at[mode] = None
        self.started_at[mode] = None
        self.match_player_ids[mode].clear()
        self.world_seeds[mode] = None
        self.world_weather[mode] = None
        if mode == GAME_MODE_FLAGDOWN:
            self.team_assignments.clear()
            self.team_members = {0: [], 1: []}
        return player_ids

    def finish_match(self, mode=GAME_MODE_NORMAL):
        """경기 결과가 확정되면 다음 대기열을 위한 상태를 비웁니다."""
        for player_id in self._player_ids(mode):
            self.modes.pop(player_id, None)
            self.ready_players.discard(player_id)
        self.started[mode] = False
        self.start_at[mode] = None
        self.started_at[mode] = None
        self.match_player_ids[mode].clear()
        self.world_seeds[mode] = None
        self.world_weather[mode] = None
        if mode == GAME_MODE_FLAGDOWN:
            self.team_assignments.clear()
            self.team_members = {0: [], 1: []}

    def mode_for(self, player_id):
        return self.modes.get(player_id)

    def team_for(self, player_id):
        """시작 시 무작위로 정한 플래그다운 팀을 경기 종료까지 유지합니다."""
        mode = self.mode_for(player_id)
        if mode != GAME_MODE_FLAGDOWN:
            return None
        if self.started[mode]:
            return self.team_assignments.get(player_id)
        player_ids = sorted(self._player_ids(mode))
        try:
            return player_ids.index(player_id) % 2
        except ValueError:
            return None

    def team_spawn_index(self, player_id):
        """팀 내부의 고정 순번을 반환해 같은 팀 스폰 지점을 유지합니다."""
        team_id = self.team_for(player_id)
        if team_id is None:
            return None
        members = (
            self.team_members[team_id]
            if self.started[GAME_MODE_FLAGDOWN]
            else sorted(
                player_id
                for player_id in self._player_ids(GAME_MODE_FLAGDOWN)
                if self.team_for(player_id) == team_id
            )
        )
        try:
            return members.index(player_id)
        except ValueError:
            return None

    def team_spawn_tile(self, player_id):
        team_id = self.team_for(player_id)
        spawn_index = self.team_spawn_index(player_id)
        team_spawns = FLAGDOWN_TEAM_SPAWN_TILES.get(team_id)
        if team_spawns is None or spawn_index is None or spawn_index >= len(team_spawns):
            return None
        return team_spawns[spawn_index]

    def active_player_ids(self, mode=None):
        return self._player_ids(mode) if mode is not None else set(self.modes)

    def visible_player_ids(self, player_id):
        """훈련장 플레이어는 일반전 스냅샷과 서로 섞이지 않게 합니다."""
        mode = self.mode_for(player_id)
        return self._player_ids(mode) if mode is not None else set()

    def zone_enabled_for(self, player_id):
        mode_id = self.mode_for(player_id)
        return bool(mode_id and get_game_mode(mode_id).zone_enabled)

    def status(self, player_id=None, mode=None):
        if mode is None:
            mode = self.mode_for(player_id) if player_id is not None else GAME_MODE_NORMAL
        mode = mode if is_game_mode_registered(mode) else GAME_MODE_NORMAL
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
        min_required = get_game_mode(mode).min_players
        all_ready = bool(total_players) and ready_count == total_players and total_players >= min_required
        return {
            "type": "lobby_status",
            "count": total_players,
            "max_players": MAX_PLAYERS,
            "min_players": min_required,
            "mode": mode,
            "started": self.started[mode],
            "world_seed": self.world_seeds[mode],
            "weather": self.world_weather[mode],
            "accepting_players": not self.started[mode] and start_at is None,
            "countdown_ms": countdown_ms,
            "elapsed_ms": elapsed_ms,
            "ready_count": ready_count,
            "all_ready": all_ready,
            "confirmed": player_id in self.ready_players if player_id is not None else False,
            "team_id": self.team_for(player_id) if player_id is not None else None,
            "team_spawn_index": (
                self.team_spawn_index(player_id) if player_id is not None else None
            ),
            "spawn_tile": (
                self.team_spawn_tile(player_id)
                if mode == GAME_MODE_FLAGDOWN and player_id is not None
                else None
            ),
        }
