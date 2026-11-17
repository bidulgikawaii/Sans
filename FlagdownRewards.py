"""Flagdown timed skill reward scheduling."""

import math
import random

from Config import FLAGDOWN_SKILL_REWARD_INTERVAL_MS


def trailing_flagdown_team(progress):
    """Return the lower-progress team, or None for a tie or invalid snapshot."""
    if not isinstance(progress, dict):
        return None
    try:
        blue_progress = float(progress.get(0, progress.get("0", 0)))
        red_progress = float(progress.get(1, progress.get("1", 0)))
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(blue_progress) or not math.isfinite(red_progress):
        return None
    if blue_progress == red_progress:
        return None
    return 0 if blue_progress < red_progress else 1


def flagdown_supply_x_bounds(progress, map_width, margin=2):
    """Prefer the trailing team's half of the map for unique supply drops."""
    team_id = trailing_flagdown_team(progress)
    if team_id is None:
        return None
    center_tile = map_width // 2
    if team_id == 1:
        return margin, center_tile - margin
    return center_tile + margin, map_width - margin - 1


def acknowledge_flagdown_skill_rewards(player_state, acknowledged_event_id):
    """Discard rewards the client has applied, without accepting future IDs."""
    if not isinstance(acknowledged_event_id, int) or isinstance(
        acknowledged_event_id, bool
    ):
        return
    last_issued_id = player_state.get("next_flagdown_skill_reward_id", 1) - 1
    acknowledged_event_id = min(max(0, acknowledged_event_id), last_issued_id)
    player_state["flagdown_skill_rewards"] = [
        reward
        for reward in player_state.get("flagdown_skill_rewards", [])
        if reward.get("event_id", 0) > acknowledged_event_id
    ]


def update_flagdown_skill_rewards(
    player_state,
    elapsed_ms,
    owned_skills,
    skill_names,
    rng=None,
):
    """Append due rewards, selecting unowned skills before healing items."""
    rng = rng or random
    rewards = player_state.setdefault("flagdown_skill_rewards", [])
    awarded_skills = set(player_state.setdefault("flagdown_awarded_skills", []))
    owned_skills = set(owned_skills)
    next_reward_at = player_state.setdefault(
        "next_flagdown_skill_reward_ms",
        FLAGDOWN_SKILL_REWARD_INTERVAL_MS,
    )
    next_reward_id = player_state.setdefault("next_flagdown_skill_reward_id", 1)

    while elapsed_ms >= next_reward_at:
        available_skills = [
            skill for skill in skill_names
            if skill not in owned_skills and skill not in awarded_skills
        ]
        if available_skills:
            skill = rng.choice(available_skills)
            rewards.append({
                "event_id": next_reward_id,
                "type": "skill",
                "skill": skill,
            })
            awarded_skills.add(skill)
        else:
            rewards.append({
                "event_id": next_reward_id,
                "type": "heal",
            })
        next_reward_id += 1
        next_reward_at += FLAGDOWN_SKILL_REWARD_INTERVAL_MS

    player_state["flagdown_awarded_skills"] = sorted(awarded_skills)
    player_state["next_flagdown_skill_reward_id"] = next_reward_id
    player_state["next_flagdown_skill_reward_ms"] = next_reward_at
    return rewards
