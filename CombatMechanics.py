def apply_shield_activation(
    current_token,
    current_shield_hp,
    reported_token,
    player_hp,
    shield_hp,
):
    """Apply only newer shield activations; delayed packets cannot remove a shield."""
    if reported_token <= current_token or player_hp <= 0:
        return current_token, current_shield_hp
    return reported_token, shield_hp


def is_suicide_hit(attacker_id, target_id, skill_source):
    return attacker_id == target_id and skill_source == "자폭"
