import math
import pygame
from FontAssets import get_game_font
from Config import WARD_DISPLAY_RADIUS


_scaled_images = {}
_cooldown_overlays = {}
_damage_text_surfaces = {}
_skill_range_surfaces = {}
_HEALTH_FRAME_COLOR = pygame.Color("gray20")
_HEALTH_COLORS = (pygame.Color("green"), pygame.Color("yellow"), pygame.Color("red"))


def create_bat_launch(event, map_width, map_height, now):
    launch = event.get("bat_launch")
    if not isinstance(launch, dict):
        return None

    start_x = float(launch.get("x", 0))
    start_y = float(launch.get("y", 0))
    direction_x = float(launch.get("direction_x", 1))
    direction_y = float(launch.get("direction_y", 0))
    direction_length = math.hypot(direction_x, direction_y)
    if direction_length <= 0.001:
        direction_x, direction_y = 1.0, 0.0
    else:
        direction_x /= direction_length
        direction_y /= direction_length

    distances_to_edge = []
    if direction_x > 0:
        distances_to_edge.append((map_width - start_x) / direction_x)
    elif direction_x < 0:
        distances_to_edge.append(-start_x / direction_x)
    if direction_y > 0:
        distances_to_edge.append((map_height - start_y) / direction_y)
    elif direction_y < 0:
        distances_to_edge.append(-start_y / direction_y)
    distance_to_edge = min(value for value in distances_to_edge if value >= 0)
    distance = distance_to_edge + 240

    return {
        "x": start_x,
        "y": start_y,
        "direction_x": direction_x,
        "direction_y": direction_y,
        "distance": distance,
        "started_at": now,
        "duration": max(800, min(1800, round(distance / 3.5))),
    }


def get_bat_launch_frame(launch, now):
    elapsed = max(0, now - launch["started_at"])
    progress = min(1.0, elapsed / launch["duration"])
    eased_progress = progress * progress * (3 - 2 * progress)
    arc_height = min(320, launch["distance"] * 0.16)
    center_x = launch["x"] + launch["direction_x"] * launch["distance"] * eased_progress
    center_y = (
        launch["y"]
        + launch["direction_y"] * launch["distance"] * eased_progress
        - math.sin(progress * math.pi) * arc_height
    )
    alpha = 255 if progress < 0.72 else round(255 * (1 - progress) / 0.28)
    rotation = math.degrees(math.atan2(launch["direction_y"], launch["direction_x"]))
    rotation += 900 * eased_progress
    return center_x, center_y, rotation, max(0, alpha), progress >= 1.0


def _fit_kill_feed_text(font, text, color, max_width):
    """긴 닉네임을 카드 안에 맞추고, 잘린 이름에는 말줄임표를 붙입니다."""
    rendered = font.render(text, True, color)
    if rendered.get_width() <= max_width:
        return rendered

    shortened = text
    while shortened and font.size(shortened + "...")[0] > max_width:
        shortened = shortened[:-1]
    return font.render(shortened.rstrip() + "...", True, color)


def draw_kill_feed(
    surface,
    events,
    font,
    panel_image,
    get_weapon_image,
    local_player_id,
    local_player_name,
):
    """최근 처치 이벤트를 장식 패널과 무기 아이콘이 포함된 카드로 그립니다."""
    card_width = panel_image.get_width() if panel_image is not None else 520
    card_height = panel_image.get_height() if panel_image is not None else 58
    right_margin = 24
    top = 250
    row_gap = 8
    left = surface.get_width() - card_width - right_margin

    # 최신 이벤트가 위쪽에 오도록 최대 다섯 건을 역순으로 표시합니다.
    visible_events = list(reversed(events[-5:]))
    now = pygame.time.get_ticks()
    for index, event in enumerate(visible_events):
        age = max(0, now - event.get("started_at", now))
        appear = min(1.0, age / 220)
        appear = appear * appear * (3 - 2 * appear)
        fade = min(1.0, max(0.0, (5000 - age) / 450))
        opacity = round(255 * min(appear, fade))
        if opacity <= 0:
            continue
        card_rect = pygame.Rect(
            left + round((1.0 - appear) * 48),
            top + index * (card_height + row_gap),
            card_width,
            card_height,
        )
        card = pygame.Surface((card_width, card_height), pygame.SRCALPHA)
        if panel_image is not None:
            card.blit(panel_image, (0, 0))
        else:
            pygame.draw.rect(card, (24, 34, 46), card.get_rect(), border_radius=10)
            pygame.draw.rect(card, (100, 190, 220), card.get_rect(), 2, border_radius=10)

        killer_id = event.get("killer_id")
        target_id = event.get("target_id")
        has_local_id = local_player_id is not None and str(local_player_id) != ""
        is_local_killer = has_local_id and killer_id is not None and str(killer_id) == str(local_player_id)
        is_local_target = has_local_id and target_id is not None and str(target_id) == str(local_player_id)
        cause = event.get("cause")
        if cause == "magnetic_zone":
            killer = "자기장"
        elif cause == "self_inflicted":
            killer = "자폭"
        else:
            killer = str(
                event.get("killer_name")
                or (local_player_name if is_local_killer else f"플레이어 {killer_id or ''}")
            )
        target = str(
            event.get("target_name")
            or (local_player_name if is_local_target else target_id or "플레이어")
        )
        killer_color = (105, 225, 255) if is_local_killer else (245, 240, 225)
        target_color = (255, 110, 120) if is_local_target else (245, 240, 225)
        center_y = card_rect.centery

        killer_surface = _fit_kill_feed_text(font, killer, killer_color, 160)
        card.blit(killer_surface, (34, center_y - card_rect.top - killer_surface.get_height() // 2))

        separator = font.render(">", True, (210, 220, 230))
        card.blit(separator, separator.get_rect(center=(210, card_height // 2)))

        weapon_id = event.get("weapon_id")
        weapon_image = get_weapon_image(weapon_id) if weapon_id else None
        if weapon_image is not None:
            icon = pygame.transform.smoothscale(weapon_image, (34, 34))
            card.blit(icon, icon.get_rect(center=(260, card_height // 2)))

        target_surface = _fit_kill_feed_text(font, target, target_color, 160)
        card.blit(
            target_surface,
            (card_width - 34 - target_surface.get_width(), card_height // 2 - target_surface.get_height() // 2),
        )
        card.set_alpha(opacity)
        surface.blit(card, card_rect)


def draw_visibility_geometry(surface, geometry, camera_x, camera_y, zoom):
    if geometry.is_empty:
        return
    polygons = geometry.geoms if geometry.geom_type == "MultiPolygon" else (geometry,)
    for polygon in polygons:
        points = [
            (round((world_x - camera_x) * zoom), round((world_y - camera_y) * zoom))
            for world_x, world_y in polygon.exterior.coords
        ]
        if len(points) >= 3:
            pygame.draw.polygon(surface, (0, 0, 0, 0), points)


def draw_bush_vision_angle(
    surface, center_x, center_y, direction_angle, fov_angle, bonus_angle, radius,
    zoom=1.0,
):
    """Mark the extra cone edges used to spot players hiding in nearby bushes."""
    direction = math.radians(direction_angle)
    base_half = math.radians(fov_angle / 2)
    bonus_half = math.radians(bonus_angle / 2)
    center = (round(center_x), round(center_y))
    line_width = max(1, round(3 * zoom))
    for sign in (-1, 1):
        inner_angle = direction + sign * base_half
        outer_angle = direction + sign * (base_half + bonus_half)
        outer = (
            round(center_x + math.cos(outer_angle) * radius),
            round(center_y + math.sin(outer_angle) * radius),
        )
        pygame.draw.line(surface, (70, 235, 150), center, outer, line_width)
        pygame.draw.line(surface, (205, 255, 220), center, outer, max(1, round(zoom)))
        arc_points = []
        for step in range(7):
            angle = inner_angle + (outer_angle - inner_angle) * step / 6
            arc_points.append((
                round(center_x + math.cos(angle) * radius),
                round(center_y + math.sin(angle) * radius),
            ))
        if len(arc_points) > 1:
            pygame.draw.lines(
                surface, (90, 245, 165), False, arc_points,
                max(1, round(2 * zoom)),
            )


def draw_player_hitboxes(surface, head_rect, body_rect, camera_x, camera_y, zoom):
    for world_rect, color in (
        (head_rect, (255, 80, 80)),
        (body_rect, (80, 220, 255)),
    ):
        screen_rect = pygame.Rect(
            round((world_rect.x - camera_x) * zoom),
            round((world_rect.y - camera_y) * zoom),
            max(1, round(world_rect.width * zoom)),
            max(1, round(world_rect.height * zoom)),
        )
        pygame.draw.rect(surface, color, screen_rect, max(1, round(2 * zoom)))


def get_aim_ray_endpoint(origin_x, origin_y, angle_degrees, tile_generator, target_distance):
    angle = math.radians(angle_degrees)
    step = max(4, tile_generator.tile_size // 4)
    last_x, last_y = origin_x, origin_y
    for distance in range(step, target_distance + step, step):
        ray_x = origin_x + math.cos(angle) * distance
        ray_y = origin_y + math.sin(angle) * distance
        ray_rect = pygame.Rect(round(ray_x) - 2, round(ray_y) - 2, 4, 4)
        if tile_generator.check_wall_collision(ray_rect):
            return last_x, last_y
        last_x, last_y = ray_x, ray_y
    return last_x, last_y


def draw_local_aim_ray(
    surface,
    start_x,
    start_y,
    angle_degrees,
    camera_x,
    camera_y,
    zoom,
    tile_generator,
    target_distance,
):
    end_x, end_y = get_aim_ray_endpoint(
        (start_x + camera_x) / zoom,
        (start_y + camera_y) / zoom,
        angle_degrees,
        tile_generator,
        target_distance,
    )
    end_screen = (
        (end_x - camera_x) * zoom,
        (end_y - camera_y) * zoom,
    )
    pygame.draw.line(
        surface,
        (255, 235, 80),
        (round(start_x), round(start_y)),
        (round(end_screen[0]), round(end_screen[1])),
        max(1, round(2 * zoom)),
    )


def draw_teleport_anchor(surface, anchor_x, anchor_y, camera_x, camera_y, zoom, image=None):
    screen_x = (anchor_x - camera_x) * zoom
    screen_y = (anchor_y - camera_y) * zoom
    center = (round(screen_x), round(screen_y))
    if image is not None:
        size = (
            max(1, round(image.get_width() * zoom)),
            max(1, round(image.get_height() * zoom)),
        )
        cache_key = (id(image), size)
        scaled_image = _scaled_images.get(cache_key)
        if scaled_image is None:
            scaled_image = pygame.transform.smoothscale(image, size)
            if len(_scaled_images) >= 64:
                _scaled_images.clear()
            _scaled_images[cache_key] = scaled_image
        surface.blit(scaled_image, scaled_image.get_rect(center=center))
        return
    width = max(8, round(18 * zoom))
    height = max(16, round(48 * zoom))
    pygame.draw.ellipse(
        surface,
        (100, 255, 150),
        (center[0] - width, center[1] + height // 3, width * 2, max(4, height // 3)),
        2,
    )
    pygame.draw.polygon(
        surface,
        (150, 255, 180),
        [
            (center[0], center[1] - height),
            (center[0] - width, center[1] + height // 3),
            (center[0] + width, center[1] + height // 3),
        ],
        2,
    )
    pygame.draw.circle(surface, (220, 255, 220), center, max(3, round(6 * zoom)), 2)


def draw_health_bar(surface, x, y, current_value, max_value, frame, frame_size, thresholds):
    frame_width, frame_height = frame_size
    inner_x = int(frame_width * 0.11)
    inner_y = int(frame_height * 0.34)
    inner_width = int(frame_width * 0.78)
    inner_height = int(frame_height * 0.27)
    inner_rect = pygame.Rect(x + inner_x, y + inner_y, inner_width, inner_height)
    pygame.draw.rect(surface, _HEALTH_FRAME_COLOR, inner_rect)

    health_ratio = current_value / max(1, max_value)
    if health_ratio >= thresholds[0]:
        health_color = _HEALTH_COLORS[0]
    elif health_ratio >= thresholds[1]:
        health_color = _HEALTH_COLORS[1]
    else:
        health_color = _HEALTH_COLORS[2]
    fill_width = int(inner_rect.width * health_ratio)
    if fill_width > 0:
        pygame.draw.rect(
            surface,
            health_color,
            (inner_rect.x, inner_rect.y, fill_width, inner_rect.height),
        )
    surface.blit(frame, (x, y))


def draw_ammo_status(
    surface,
    weapon_state,
    font,
    screen_width,
    screen_height,
    panel_size,
    panel_margin,
):
    config = weapon_state.config
    name_text = font.render(config.name, True, (255, 220, 120))
    ammo_text = font.render(
        "재장전 중..." if weapon_state.is_reloading_now() else f"탄창 {weapon_state.magazine_ammo}/{config.magazine_size}",
        True,
        (255, 180, 120) if weapon_state.is_reloading_now() else (255, 255, 255),
    )
    reserve_text = font.render(f"예비 탄약 {weapon_state.reserve_ammo}", True, (190, 220, 255))
    panel_x = screen_width - panel_size[0] - panel_margin[0]
    panel_y = screen_height - panel_size[1] - panel_margin[1]
    panel_center_x = panel_x + panel_size[0] // 2
    name_rect = name_text.get_rect(center=(panel_center_x, panel_y + 20))
    reserve_rect = reserve_text.get_rect(center=(panel_center_x, panel_y + 60))
    ammo_rect = ammo_text.get_rect(center=(panel_center_x, panel_y + 100))
    surface.blit(name_text, name_rect)
    surface.blit(ammo_text, ammo_rect)
    surface.blit(reserve_text, reserve_rect)


def draw_ward(surface, ward_x, ward_y, camera_x, camera_y, zoom, image=None):
    screen_x = round((ward_x - camera_x) * zoom)
    screen_y = round((ward_y - camera_y) * zoom)
    radius = max(8, round(WARD_DISPLAY_RADIUS * zoom))
    pygame.draw.circle(surface, (120, 240, 255), (screen_x, screen_y), radius, 2)
    if image is not None:
        size = max(1, round(radius * 2))
        image_size = (size, size)
        cache_key = (id(image), image_size)
        scaled_image = _scaled_images.get(cache_key)
        if scaled_image is None:
            scaled_image = pygame.transform.smoothscale(image, image_size)
            if len(_scaled_images) >= 64:
                _scaled_images.clear()
            _scaled_images[cache_key] = scaled_image
        surface.blit(scaled_image, scaled_image.get_rect(center=(screen_x, screen_y)))
    else:
        pygame.draw.line(surface, (120, 240, 255), (screen_x - radius, screen_y), (screen_x + radius, screen_y), 1)
        pygame.draw.line(surface, (120, 240, 255), (screen_x, screen_y - radius), (screen_x, screen_y + radius), 1)


def draw_stun_effect(surface, center_x, center_y, zoom, now):
    """기절 중인 플레이어 주변에 맥동하는 전기 효과를 표시합니다."""
    pulse = 1.0 + 0.16 * math.sin(now * 0.035)
    radius = max(12, round(30 * zoom * pulse))
    center = (round(center_x), round(center_y))
    pygame.draw.circle(surface, (100, 225, 255), center, radius, max(1, round(2 * zoom)))
    pygame.draw.circle(surface, (210, 250, 255), center, max(2, round(radius * 0.18)), 1)
    for index in range(6):
        angle = math.tau * index / 6 + now * 0.003
        start = (center_x + math.cos(angle) * radius, center_y + math.sin(angle) * radius)
        end = (
            center_x + math.cos(angle + 0.22) * (radius + 15 * zoom),
            center_y + math.sin(angle + 0.22) * (radius + 15 * zoom),
        )
        middle = (
            (start[0] + end[0]) / 2 + math.sin(now * 0.04 + index * 2) * 7 * zoom,
            (start[1] + end[1]) / 2 + math.cos(now * 0.035 + index) * 7 * zoom,
        )
        points = [tuple(map(round, point)) for point in (start, middle, end)]
        pygame.draw.lines(surface, (55, 180, 255), False, points, max(2, round(4 * zoom)))
        pygame.draw.lines(surface, (225, 255, 255), False, points, max(1, round(1.5 * zoom)))


def draw_stun_bolt(surface, center_x, center_y, angle, zoom, now, frames):
    """코멧 프레임 애니메이션을 기절탄의 발광 효과로 표시합니다."""
    if not frames:
        return
    frame = frames[(now // 40) % len(frames)]
    size = max(1, round(72 * zoom))
    cache_key = (id(frame), (size, size))
    sprite = _scaled_images.get(cache_key)
    if sprite is None:
        sprite = pygame.transform.smoothscale(frame, (size, size))
        if len(_scaled_images) >= 96:
            _scaled_images.clear()
        _scaled_images[cache_key] = sprite
    sprite = pygame.transform.rotate(sprite, -angle)
    surface.blit(sprite, sprite.get_rect(center=(round(center_x), round(center_y))))


def draw_linked_clone(
    surface, clone, player_image, camera_x, camera_y, zoom, now,
    linked_player=None,
):
    """연결된 플레이어 위치로 이어지는 분신과 체력 막대를 그립니다."""
    clone_x = float(clone["x"])
    clone_y = float(clone["y"])
    screen_x = round((clone_x - camera_x) * zoom)
    screen_y = round((clone_y - camera_y) * zoom)
    sprite_size = (
        max(1, round(player_image.get_width() * zoom)),
        max(1, round(player_image.get_height() * zoom)),
    )
    sprite = pygame.transform.scale(player_image, sprite_size)
    sprite.set_alpha(145 + round(25 * math.sin(now * 0.012)))
    sprite.fill((55, 150, 255, 0), special_flags=pygame.BLEND_RGBA_ADD)
    sprite_rect = sprite.get_rect(center=(screen_x, screen_y))

    if linked_player is not None and linked_player.get("hp", 0) > 0:
        target_x = round((linked_player["posX"] + 36 - camera_x) * zoom)
        target_y = round((linked_player["posY"] + 36 - camera_y) * zoom)
        pygame.draw.line(surface, (90, 205, 255), (screen_x, screen_y), (target_x, target_y), max(1, round(2 * zoom)))

    if sprite_rect.colliderect(surface.get_rect()):
        surface.blit(sprite, sprite_rect)
        pygame.draw.rect(surface, (130, 225, 255), sprite_rect, max(1, round(2 * zoom)))
        bar_width = max(24, round(54 * zoom))
        bar_height = max(3, round(5 * zoom))
        bar_rect = pygame.Rect(
            screen_x - bar_width // 2,
            sprite_rect.top - bar_height - max(2, round(4 * zoom)),
            bar_width,
            bar_height,
        )
        health_ratio = max(0.0, min(1.0, clone["hp"] / max(1, clone["max_hp"])))
        pygame.draw.rect(surface, (20, 35, 50), bar_rect)
        fill_rect = bar_rect.copy()
        fill_rect.width = round(bar_width * health_ratio)
        pygame.draw.rect(surface, (90, 230, 255), fill_rect)


def draw_skill_range(surface, world_x, world_y, world_radius, camera_x, camera_y, zoom, color, pulse=1.0):
    """스킬의 월드 범위를 반투명 면, 외곽선, 눈금으로 표시합니다."""
    center_x = round((world_x - camera_x) * zoom)
    center_y = round((world_y - camera_y) * zoom)
    radius = max(2, round(world_radius * zoom * pulse))
    line_width = max(1, round(2 * zoom))
    cache_key = (radius, tuple(color[:3]), line_width)
    overlay = _skill_range_surfaces.get(cache_key)
    if overlay is None:
        diameter = radius * 2 + 2
        overlay = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
        center = (radius + 1, radius + 1)
        pygame.draw.circle(overlay, (*color[:3], 24), center, radius)
        pygame.draw.circle(overlay, (*color[:3], 210), center, radius, line_width)
        tick_inner = max(1, round(radius * 0.9))
        for index in range(16):
            angle = math.tau * index / 16
            start = (
                round(center[0] + math.cos(angle) * tick_inner),
                round(center[1] + math.sin(angle) * tick_inner),
            )
            end = (
                round(center[0] + math.cos(angle) * radius),
                round(center[1] + math.sin(angle) * radius),
            )
            pygame.draw.line(overlay, (*color[:3], 150), start, end, line_width)
        if len(_skill_range_surfaces) >= 6:
            _skill_range_surfaces.clear()
        _skill_range_surfaces[cache_key] = overlay
    surface.blit(overlay, (center_x - radius - 1, center_y - radius - 1))


def draw_quick_slot_cooldowns(surface, slots, cooldowns, font):
    now = pygame.time.get_ticks()
    for slot in slots:
        if not slot.assigned_skill:
            continue
        end_time = cooldowns.get(slot.assigned_skill, 0)
        if end_time <= now:
            continue
        remain = max(0.0, (end_time - now) / 1000.0)
        overlay_size = (slot.rect.width, slot.rect.height)
        overlay = _cooldown_overlays.get(overlay_size)
        if overlay is None:
            overlay = pygame.Surface(overlay_size, pygame.SRCALPHA)
            pygame.draw.rect(overlay, (0, 0, 0, 170), overlay.get_rect(), border_radius=8)
            _cooldown_overlays[overlay_size] = overlay
        surface.blit(overlay, slot.rect.topleft)
        text = font.render(f"{remain:.1f}s", True, (255, 255, 255))
        surface.blit(text, (slot.rect.centerx - text.get_width() / 2, slot.rect.centery - 8))


def draw_damage_numbers(surface, damage_numbers, camera_x, camera_y, zoom, font, now):
    for number in damage_numbers:
        age = now - number["started_at"]
        if age < 0 or age >= number["lifetime"]:
            continue
        progress = age / number["lifetime"]
        screen_x = (number["x"] - camera_x) * zoom
        screen_y = (number["y"] - camera_y - progress * 42) * zoom
        text_key = (str(number["damage"]), tuple(number["color"]))
        text = _damage_text_surfaces.get(text_key)
        if text is None:
            text = font.render(text_key[0], True, text_key[1])
            if len(_damage_text_surfaces) >= 256:
                _damage_text_surfaces.clear()
            _damage_text_surfaces[text_key] = text
        text.set_alpha(round(255 * (1.0 - progress)))
        surface.blit(text, text.get_rect(center=(round(screen_x), round(screen_y))))


def draw_supply_drop(surface, supply, camera_x, camera_y, zoom, colors, now):
    x = round((supply["x"] - camera_x) * zoom)
    y = round((supply["y"] - camera_y) * zoom)
    color = colors[supply["type"]]
    warning_until = supply.get("warning_until", 0)
    if now < warning_until:
        pulse = 22 + round(8 * math.sin(now * 0.012))
        top = max(0, y - round(180 * zoom))
        elapsed = max(0, now - supply.get("fall_started_at", now))
        fall_progress = min(1.0, elapsed / max(1, warning_until - supply.get("fall_started_at", now)))
        beam_y = top + round((y - top) * fall_progress)
        pygame.draw.circle(
            surface,
            (255, 230, 120),
            (x, y),
            max(18, round(pulse * zoom)),
            3,
        )
        pygame.draw.line(surface, (255, 240, 150), (x, top), (x, beam_y), 2)
        pygame.draw.circle(
            surface,
            (255, 250, 190),
            (x, beam_y),
            max(3, round(6 * zoom)),
        )
        warning_label = (
            "유니크 보급품 낙하"
            if supply["type"] == "special_weapon"
            else "보급품 낙하"
        )
        label = get_game_font(26).render(warning_label, True, (255, 240, 150))
        surface.blit(label, label.get_rect(center=(x, max(18, y - round(165 * zoom)))))
    box = pygame.Rect(0, 0, max(22, round(36 * zoom)), max(18, round(28 * zoom)))
    box.center = (x, y)
    pygame.draw.rect(surface, (35, 35, 45), box, border_radius=4)
    pygame.draw.rect(surface, color, box, 3, border_radius=4)
    pygame.draw.line(surface, color, (box.left, box.centery), (box.right, box.centery), 2)
    labels = {
        "special_weapon": "3",
        "flare_ammo": "+10",
        "flare_skill": "S",
    }
    label_text = labels.get(supply["type"])
    if label_text:
        label = get_game_font(max(12, round(18 * zoom))).render(
            label_text,
            True,
            (255, 255, 255),
        )
        surface.blit(label, label.get_rect(center=box.center))
