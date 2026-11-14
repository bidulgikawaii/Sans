from Config import SPIRIT_TRIAL_LINKED_DAMAGE_RATIO


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


def spirit_linked_body_damage(clone_damage, remainder=0):
    """Transfer 30% of clone damage to its linked player's body."""
    precision = 1000
    ratio_units = round(SPIRIT_TRIAL_LINKED_DAMAGE_RATIO * precision)
    accumulated_damage = max(0, int(clone_damage)) * ratio_units + int(remainder)
    return divmod(accumulated_damage, precision)
