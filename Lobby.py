from Config import GAME_MODE_DEBUG, GAME_MODE_NORMAL, MAX_PLAYERS


class LobbyState:
    """접속 중인 사용자와 실제 게임 대기열을 분리해 관리합니다."""

    def __init__(self):
        self.modes = {}
        self.started = False

    def join(self, player_id, mode):
        if mode not in (GAME_MODE_NORMAL, GAME_MODE_DEBUG):
            mode = GAME_MODE_NORMAL
        self.modes[player_id] = mode
        if len(self.modes) >= MAX_PLAYERS or mode == GAME_MODE_DEBUG:
            self.started = True

    def leave(self, player_id):
        self.modes.pop(player_id, None)
        if not self.modes:
            self.started = False

    def active_player_ids(self):
        return set(self.modes)

    def status(self):
        mode = GAME_MODE_DEBUG if GAME_MODE_DEBUG in self.modes.values() else GAME_MODE_NORMAL
        return {
            "type": "lobby_status",
            "count": len(self.modes),
            "max_players": MAX_PLAYERS,
            "mode": mode,
            "started": self.started,
        }
