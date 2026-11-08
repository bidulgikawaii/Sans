"""Flare-gun supply reward selection."""

import random

from Config import (
    DEATHMATCH_FLARE_SUPPLY_TYPES,
    DEATHMATCH_FLARE_UNIQUE_SUPPLY_TYPES,
    FLARE_SUPPLY_DROP_COUNT,
    FLARE_UNIQUE_SUPPLY_CHANCE,
)
from GameModes import GAME_MODE_DEATHMATCH


def select_flare_supply_reward_types(game_mode, rng=None):
    """Choose one reward type for each flare drop."""
    rng = random if rng is None else rng
    if game_mode != GAME_MODE_DEATHMATCH:
        return ("flare_ammo",) * FLARE_SUPPLY_DROP_COUNT
    if rng.random() < FLARE_UNIQUE_SUPPLY_CHANCE:
        return DEATHMATCH_FLARE_UNIQUE_SUPPLY_TYPES
    return DEATHMATCH_FLARE_SUPPLY_TYPES
