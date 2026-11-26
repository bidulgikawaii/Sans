import math

import pygame


AIM_DURATION_MS = 500
AIM_APPROACH_DISTANCE = 900
GOLDEN_BULLET_FIRE_INTERVAL_MS = 55
GOLDEN_TINT_FADE_MS = 320
GOLDEN_TINT_MAX_ALPHA = 52
GOLDEN_SEQUENCE_DURATION_MS = 1400
GOLDEN_SUNSET_DURATION_MS = GOLDEN_SEQUENCE_DURATION_MS
GOLDEN_SUNSET_FADE_MS = 450
GOLDEN_SUNSET_MAX_ALPHA = 120
GOLDEN_BULLET_INITIAL_SPEED_RATIO = 0.2
GOLDEN_BULLET_ACCELERATION_DELAY_MS = 0
GOLDEN_BULLET_ACCELERATION_DURATION_MS = 180
GOLDEN_BULLET_MAX_SPEED_MULTIPLIER = 4.0


def aim_lock_position(lock, now_ms):
    duration = max(1, lock["duration_ms"])
    progress = min(1.0, max(0.0, (now_ms - lock["started_at"]) / duration))
    eased_progress = progress * progress * (3 - 2 * progress)
    return (
        lock["start_x"] + (lock["x"] - lock["start_x"]) * eased_progress,
        lock["start_y"] + (lock["y"] - lock["start_y"]) * eased_progress,
    )


def golden_target_timing(target_index, target_count):
    target_count = max(1, target_count)
    target_index = min(target_count - 1, max(0, target_index))
    interval_ms = max(1, AIM_DURATION_MS // target_count)
    sequence_step_ms = interval_ms + GOLDEN_BULLET_FIRE_INTERVAL_MS
    return target_index * sequence_step_ms, interval_ms


def golden_bullet_release_delay(target_index):
    return (
        AIM_DURATION_MS
        + max(0, target_index) * GOLDEN_BULLET_FIRE_INTERVAL_MS
    )


def golden_bullet_path_intersects_rect(
    start_x,
    start_y,
    end_x,
    end_y,
    projectile_width,
    projectile_height,
    target_rect,
):
    expanded_rect = target_rect.inflate(projectile_width, projectile_height)
    start = (round(start_x), round(start_y))
    end = (round(end_x), round(end_y))
    return expanded_rect.collidepoint(start) or bool(
        expanded_rect.clipline(start, end)
    )


def golden_camera_focus(aim_locks, now_ms, owner_id=None):
    active_locks = [
        lock
        for lock in aim_locks
        if lock["started_at"] <= now_ms < lock["until"]
        and (owner_id is None or lock.get("owner_id", owner_id) == owner_id)
    ]
    if not active_locks:
        return None
    lock = min(active_locks, key=lambda item: item["started_at"])
    return lock["x"], lock["y"]


def golden_revolver_tint_alpha(started_at, aim_until, now_ms):
    if now_ms < started_at or now_ms >= aim_until + GOLDEN_TINT_FADE_MS:
        return 0
    if now_ms < aim_until:
        progress = (now_ms - started_at) / max(1, aim_until - started_at)
    else:
        progress = (aim_until + GOLDEN_TINT_FADE_MS - now_ms) / GOLDEN_TINT_FADE_MS
    eased_progress = progress * progress * (3 - 2 * progress)
    return round(GOLDEN_TINT_MAX_ALPHA * eased_progress)


def golden_revolver_sunset_alpha(started_at, now_ms):
    elapsed_ms = now_ms - started_at
    if started_at <= 0 or elapsed_ms < 0 or elapsed_ms >= GOLDEN_SUNSET_DURATION_MS:
        return 0
    fade_in = min(1.0, elapsed_ms / 180)
    fade_out = min(
        1.0,
        (GOLDEN_SUNSET_DURATION_MS - elapsed_ms) / GOLDEN_SUNSET_FADE_MS,
    )
    return round(GOLDEN_SUNSET_MAX_ALPHA * min(fade_in, fade_out))


def draw_golden_revolver_sunset(surface, overlay, started_at, now_ms):
    alpha = golden_revolver_sunset_alpha(started_at, now_ms)
    if not alpha:
        return

    width, height = surface.get_size()
    overlay.fill((0, 0, 0, 0))
    palette = (
        (82, 36, 112),
        (177, 52, 94),
        (244, 91, 52),
        (255, 166, 57),
        (255, 222, 132),
    )
    band_count = 24
    first_band = round(height * 0.36)
    band_height = max(1, math.ceil((height - first_band) / band_count))
    for band in range(band_count):
        blend = band / max(1, band_count - 1) * (len(palette) - 1)
        color_index = min(len(palette) - 2, int(blend))
        color_mix = blend - color_index
        color = tuple(
            round(
                palette[color_index][channel] * (1 - color_mix)
                + palette[color_index + 1][channel] * color_mix
            )
            for channel in range(3)
        )
        band_alpha = round(alpha * (0.12 + 0.2 * band / band_count))
        pygame.draw.rect(
            overlay,
            (*color, band_alpha),
            (0, first_band + band * band_height, width, band_height + 1),
        )

    sun_x = width // 2
    elapsed_ms = max(0, now_ms - started_at)
    sunset_progress = min(1.0, elapsed_ms / AIM_DURATION_MS)
    sun_y = round(height * (0.50 + 0.23 * sunset_progress))
    sun_radius = max(24, round(min(width * 0.24, height * 0.31)))
    rotation = elapsed_ms * 0.00018

    pygame.draw.circle(
        overlay,
        (255, 92, 40, round(alpha * 0.12)),
        (sun_x, sun_y),
        round(sun_radius * 1.65),
    )
    ray_count = 48
    for ray in range(ray_count):
        angle = math.tau * ray / ray_count + rotation
        ray_width = 0.035 if ray % 3 else 0.055
        inner_radius = sun_radius * 0.94
        outer_radius = sun_radius * (1.55 if ray % 2 else 1.85)
        points = (
            (
                round(sun_x + math.cos(angle - ray_width) * inner_radius),
                round(sun_y + math.sin(angle - ray_width) * inner_radius),
            ),
            (
                round(sun_x + math.cos(angle) * outer_radius),
                round(sun_y + math.sin(angle) * outer_radius),
            ),
            (
                round(sun_x + math.cos(angle + ray_width) * inner_radius),
                round(sun_y + math.sin(angle + ray_width) * inner_radius),
            ),
        )
        pygame.draw.polygon(
            overlay,
            (255, 204, 104, round(alpha * (0.18 if ray % 2 else 0.28))),
            points,
        )

    for ring_index in range(3):
        ring_radius = round(sun_radius * (1.45 + ring_index * 0.2))
        ring_rect = pygame.Rect(
            sun_x - ring_radius,
            sun_y - ring_radius,
            ring_radius * 2,
            ring_radius * 2,
        )
        ring_start = rotation * (1 + ring_index * 0.35) + ring_index * 1.8
        pygame.draw.arc(
            overlay,
            (255, 224, 145, round(alpha * (0.62 - ring_index * 0.12))),
            ring_rect,
            ring_start,
            ring_start + math.pi * (1.35 + ring_index * 0.2),
            max(1, sun_radius // 24),
        )

    for sparkle in range(12):
        angle = math.tau * sparkle / 12 - rotation * 1.8
        sparkle_radius = sun_radius * (
            1.62 + 0.12 * math.sin(elapsed_ms * 0.012 + sparkle)
        )
        sparkle_x = round(sun_x + math.cos(angle) * sparkle_radius)
        sparkle_y = round(sun_y + math.sin(angle) * sparkle_radius)
        sparkle_size = max(3, round(sun_radius * 0.09))
        pygame.draw.line(
            overlay,
            (255, 244, 205, round(alpha * 0.85)),
            (sparkle_x - sparkle_size, sparkle_y),
            (sparkle_x + sparkle_size, sparkle_y),
            max(1, sparkle_size // 3),
        )
        pygame.draw.line(
            overlay,
            (255, 244, 205, round(alpha * 0.85)),
            (sparkle_x, sparkle_y - sparkle_size),
            (sparkle_x, sparkle_y + sparkle_size),
            max(1, sparkle_size // 3),
        )

    pygame.draw.circle(
        overlay,
        (255, 119, 43, round(alpha * 0.78)),
        (sun_x, sun_y),
        sun_radius,
    )
    pygame.draw.circle(
        overlay,
        (255, 188, 74, round(alpha * 0.88)),
        (sun_x, sun_y),
        round(sun_radius * 0.82),
    )
    pygame.draw.circle(
        overlay,
        (255, 238, 164, alpha),
        (sun_x, sun_y),
        round(sun_radius * 0.58),
    )

    horizon_y = round(sun_y + sun_radius * 0.53)
    for stripe in range(5):
        stripe_y = horizon_y + stripe * max(3, sun_radius // 12)
        if stripe_y >= height:
            break
        half_width = round(
            sun_radius
            * math.sqrt(max(0, 1 - ((stripe_y - sun_y) / sun_radius) ** 2))
        )
        pygame.draw.line(
            overlay,
            (196, 72, 59, round(alpha * 0.76)),
            (sun_x - half_width, stripe_y),
            (sun_x + half_width, stripe_y),
            max(2, sun_radius // 20),
        )

    horizon_glow = round(height * 0.83)
    pygame.draw.rect(
        overlay,
        (255, 195, 91, round(alpha * 0.28)),
        (0, horizon_glow, width, max(1, round(height * 0.025))),
    )
    surface.blit(overlay, (0, 0))


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
