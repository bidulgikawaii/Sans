"""클라이언트 설정값과 로컬 저장을 관리합니다."""

import json
from pathlib import Path

import pygame


KEY_ACTION_LABELS = {
    "move_up": "위로 이동",
    "move_down": "아래로 이동",
    "move_left": "왼쪽 이동",
    "move_right": "오른쪽 이동",
    "sprint": "달리기",
    "dash": "대시",
    "skill_inventory": "스킬 인벤토리",
    "healing_inventory": "회복 아이템 창",
    "use_healing": "회복 아이템 사용",
    "reload": "재장전",
    "slot_q": "스킬 슬롯 1",
    "slot_e": "스킬 슬롯 2",
    "slot_t": "스킬 슬롯 3",
}

DEFAULT_KEY_BINDINGS = {
    "move_up": pygame.K_w,
    "move_down": pygame.K_s,
    "move_left": pygame.K_a,
    "move_right": pygame.K_d,
    "sprint": pygame.K_LSHIFT,
    "dash": pygame.K_g,
    "skill_inventory": pygame.K_i,
    "healing_inventory": pygame.K_b,
    "use_healing": pygame.K_h,
    "reload": pygame.K_r,
    "slot_q": pygame.K_q,
    "slot_e": pygame.K_e,
    "slot_t": pygame.K_t,
}
RESERVED_KEYS = {
    pygame.K_ESCAPE,
    pygame.K_SPACE,
    pygame.K_RETURN,
    pygame.K_BACKSPACE,
    pygame.K_1,
    pygame.K_2,
    pygame.K_3,
    pygame.K_4,
    pygame.K_5,
    pygame.K_6,
    pygame.K_F9,
    pygame.K_F10,
    pygame.K_f,
    pygame.K_v,
    pygame.K_x,
    pygame.K_z,
}

SETTINGS_PATH = Path(__file__).resolve().with_name("settings.json")
settings = {
    "mouse_sensitivity": 1.0,
    "owned_skills_only": False,
}
key_bindings = DEFAULT_KEY_BINDINGS.copy()


def load_settings():
    """읽을 수 있는 설정값만 가져오고 나머지는 기본값으로 둡니다."""
    try:
        saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    sensitivity = saved.get("mouse_sensitivity", settings["mouse_sensitivity"])
    if isinstance(sensitivity, (int, float)):
        settings["mouse_sensitivity"] = min(2.0, max(0.25, float(sensitivity)))
    if isinstance(saved.get("owned_skills_only"), bool):
        settings["owned_skills_only"] = saved["owned_skills_only"]

    saved_bindings = saved.get("key_bindings", {})
    if isinstance(saved_bindings, dict):
        for action in DEFAULT_KEY_BINDINGS:
            key = saved_bindings.get(action)
            if isinstance(key, int) and key >= 0:
                key_bindings[action] = key


def save_settings():
    data = {
        **settings,
        "key_bindings": key_bindings,
    }
    SETTINGS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_key(action):
    return key_bindings[action]


def key_label(action):
    return pygame.key.name(get_key(action)).upper()


load_settings()