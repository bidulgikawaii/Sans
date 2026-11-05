"""Flagdown timed skill reward scheduling."""

import random

from Config import FLAGDOWN_SKILL_REWARD_INTERVAL_MS


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
