from Config import MINE_BLAST_RADIUS, MINE_TRIGGER_DELAY_MS


def mine_blast_contains(mine, x, y):
    dx = x - mine["x"]
    dy = y - mine["y"]
    return dx * dx + dy * dy <= MINE_BLAST_RADIUS ** 2


def trigger_mine(mine, now_ms):
    """Begin a single short detonation delay after an armed mine is stepped on."""
    if now_ms < mine["armed_at"] or "detonates_at" in mine:
        return False
    mine["triggered_at"] = now_ms
    mine["detonates_at"] = now_ms + MINE_TRIGGER_DELAY_MS
    return True


def mine_is_due_to_detonate(mine, now_ms):
    return "detonates_at" in mine and now_ms >= mine["detonates_at"]
