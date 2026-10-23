"""게임 모드 메타데이터를 한 곳에서 등록하고 조회합니다."""

from dataclasses import dataclass

from Config import (
    GAME_MODE_DEBUG,
    GAME_MODE_DEATHMATCH,
    GAME_MODE_NORMAL,
    NORMAL_MATCH_MIN_PLAYERS,
)


@dataclass(frozen=True)
class GameModeDefinition:
    mode_id: str
    label: str
    min_players: int = NORMAL_MATCH_MIN_PLAYERS
    zone_enabled: bool = False
    debug_tools: bool = False
    elimination: bool = False


_game_modes = {}


def register_game_mode(definition):
    """새 모드를 등록합니다. mode_id는 네트워크 프로토콜에 전달되는 안정된 ID입니다."""
    if not isinstance(definition, GameModeDefinition):
        raise TypeError("definition must be a GameModeDefinition")
    if not definition.mode_id or definition.min_players < 1:
        raise ValueError("mode_id must be set and min_players must be at least 1")
    _game_modes[definition.mode_id] = definition
    return definition


def get_game_mode(mode_id):
    """등록되지 않은 모드는 안전하게 일반전 설정으로 대체합니다."""
    return _game_modes.get(mode_id, _game_modes[GAME_MODE_NORMAL])


def get_game_modes():
    """메뉴와 서버가 사용할 등록 모드 목록을 등록 순서대로 반환합니다."""
    return tuple(_game_modes.values())


def is_game_mode_registered(mode_id):
    return mode_id in _game_modes


register_game_mode(GameModeDefinition(
    mode_id=GAME_MODE_NORMAL,
    label="일반 모드",
    min_players=NORMAL_MATCH_MIN_PLAYERS,
    zone_enabled=True,
    elimination=True,
))
register_game_mode(GameModeDefinition(
    mode_id=GAME_MODE_DEBUG,
    label="연습 모드",
    min_players=1,
    debug_tools=True,
))
register_game_mode(GameModeDefinition(
    mode_id=GAME_MODE_DEATHMATCH,
    label="데스매치",
    min_players=NORMAL_MATCH_MIN_PLAYERS,
))