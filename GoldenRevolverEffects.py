AIM_DURATION_MS = 900
AIM_APPROACH_DISTANCE = 900
GOLDEN_TINT_FADE_MS = 320
GOLDEN_TINT_MAX_ALPHA = 72
GOLDEN_BULLET_INITIAL_SPEED_RATIO = 0.16
GOLDEN_BULLET_ACCELERATION_DELAY_MS = 180
GOLDEN_BULLET_ACCELERATION_DURATION_MS = 300
GOLDEN_BULLET_MAX_SPEED_MULTIPLIER = 2.5


def aim_lock_position(lock, now_ms):
    duration = max(1, lock["duration_ms"])
    progress = min(1.0, max(0.0, (now_ms - lock["started_at"]) / duration))
    eased_progress = progress * progress * (3 - 2 * progress)
    return (
        lock["start_x"] + (lock["x"] - lock["start_x"]) * eased_progress,
        lock["start_y"] + (lock["y"] - lock["start_y"]) * eased_progress,
    )


def golden_revolver_tint_alpha(started_at, aim_until, now_ms):
    if now_ms < started_at or now_ms >= aim_until + GOLDEN_TINT_FADE_MS:
        return 0
    if now_ms < aim_until:
        progress = (now_ms - started_at) / max(1, aim_until - started_at)
    else:
        progress = (aim_until + GOLDEN_TINT_FADE_MS - now_ms) / GOLDEN_TINT_FADE_MS
    eased_progress = progress * progress * (3 - 2 * progress)
    return round(GOLDEN_TINT_MAX_ALPHA * eased_progress)


def golden_bullet_speed(max_speed, elapsed_ms):
    elapsed_ms = max(0, elapsed_ms)
    if elapsed_ms <= GOLDEN_BULLET_ACCELERATION_DELAY_MS:
        return max_speed * GOLDEN_BULLET_INITIAL_SPEED_RATIO
    acceleration_progress = min(
        1.0,
        (elapsed_ms - GOLDEN_BULLET_ACCELERATION_DELAY_MS)
        / GOLDEN_BULLET_ACCELERATION_DURATION_MS,
    )
    eased_progress = acceleration_progress * acceleration_progress
    speed_multiplier = (
        GOLDEN_BULLET_INITIAL_SPEED_RATIO
        + (
            GOLDEN_BULLET_MAX_SPEED_MULTIPLIER
            - GOLDEN_BULLET_INITIAL_SPEED_RATIO
        )
        * eased_progress
    )
    return max_speed * speed_multiplier
