SHATTER_ANIMATION_DURATION_MS = 1400
SHATTER_PAUSE_FRAME_INDEX = 17
SHATTER_PAUSE_DURATION_MS = 1800
EFFECT_DURATION_MS = SHATTER_ANIMATION_DURATION_MS + SHATTER_PAUSE_DURATION_MS
AIM_DURATION_MS = 900
AIM_APPROACH_DISTANCE = 900


def aim_lock_position(lock, now_ms):
    duration = max(1, lock["duration_ms"])
    progress = min(1.0, max(0.0, (now_ms - lock["started_at"]) / duration))
    eased_progress = progress * progress * (3 - 2 * progress)
    return (
        lock["start_x"] + (lock["x"] - lock["start_x"]) * eased_progress,
        lock["start_y"] + (lock["y"] - lock["start_y"]) * eased_progress,
    )


def shatter_frame_index(elapsed_ms, frame_count):
    if frame_count <= 0:
        raise ValueError("frame_count must be positive")

    elapsed_ms = max(0, elapsed_ms)
    pause_frame = min(SHATTER_PAUSE_FRAME_INDEX, frame_count - 1)
    pre_pause_duration = max(
        1,
        round(
            SHATTER_ANIMATION_DURATION_MS * (pause_frame + 1) / frame_count
        ),
    )
    if elapsed_ms < pre_pause_duration:
        return min(
            pause_frame,
            elapsed_ms * (pause_frame + 1) // pre_pause_duration,
        )
    if elapsed_ms < pre_pause_duration + SHATTER_PAUSE_DURATION_MS:
        return pause_frame

    remaining_frames = frame_count - pause_frame - 1
    post_pause_elapsed = (
        elapsed_ms - pre_pause_duration - SHATTER_PAUSE_DURATION_MS
    )
    post_pause_duration = max(
        1, SHATTER_ANIMATION_DURATION_MS - pre_pause_duration
    )
    return min(
        frame_count - 1,
        pause_frame
        + 1
        + post_pause_elapsed * remaining_frames // post_pause_duration,
    )
