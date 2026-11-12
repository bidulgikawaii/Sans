"""Supply reward selection."""

import random

from Config import (
    DEATHMATCH_SUPPLY_REWARD_TYPES,
    DEATHMATCH_FLARE_SUPPLY_TYPES,
    DEATHMATCH_FLARE_UNIQUE_SUPPLY_TYPES,
    FLARE_SUPPLY_DROP_COUNT,
    FLARE_UNIQUE_SUPPLY_CHANCE,
)
from GameModes import GAME_MODE_DEATHMATCH


def select_deathmatch_supply_batch(drop_count, rng=None):
    """Choose a batch of rewards, allowing at most one skill crate per batch."""
    rng = random if rng is None else rng
    rewards = [
        rng.choice(DEATHMATCH_SUPPLY_REWARD_TYPES)
        for _ in range(max(0, drop_count))
    ]
    skill_seen = False
    for index, reward in enumerate(rewards):
        if reward != "skill":
            continue
        if skill_seen:
            rewards[index] = "heal"
        else:
            skill_seen = True
    return tuple(rewards)


def select_flare_supply_reward_types(game_mode, rng=None):
    """Choose one reward type for each flare drop."""
    rng = random if rng is None else rng
    if game_mode != GAME_MODE_DEATHMATCH:
        return ("flare_ammo",) * FLARE_SUPPLY_DROP_COUNT
    if rng.random() < FLARE_UNIQUE_SUPPLY_CHANCE:
        return DEATHMATCH_FLARE_UNIQUE_SUPPLY_TYPES
    return DEATHMATCH_FLARE_SUPPLY_TYPES


def supply_spawn_requires_leader(drop_type, source):
    """Keep global drops leader-owned, but allow player-fired flare rewards."""
    return (
        drop_type in ("heal", "skill", "special_weapon")
        and source != "flare"
    )
