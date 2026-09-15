import math

import pygame


def draw_visibility_geometry(surface, geometry, camera_x, camera_y, zoom):
    if geometry.is_empty:
        return
    polygons = geometry.geoms if geometry.geom_type == "MultiPolygon" else (geometry,)
    for polygon in polygons:
        points = [
            ((world_x - camera_x) * zoom, (world_y - camera_y) * zoom)
            for world_x, world_y in polygon.exterior.coords
        ]
        if len(points) >= 3:
            pygame.draw.polygon(surface, (0, 0, 0, 0), points)


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
        (255, 0, 0),
        (round(start_x), round(start_y)),
        (round(end_screen[0]), round(end_screen[1])),
        max(1, round(2 * zoom)),
    )


def draw_teleport_anchor(surface, anchor_x, anchor_y, camera_x, camera_y, zoom, image=None):
    screen_x = (anchor_x - camera_x) * zoom
    screen_y = (anchor_y - camera_y) * zoom
    center = (round(screen_x), round(screen_y))
    if image is not None:
        scaled_image = pygame.transform.smoothscale(
            image,
            (
                max(1, round(image.get_width() * zoom)),
                max(1, round(image.get_height() * zoom)),
            ),
        )
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
    pygame.draw.rect(surface, pygame.Color("gray20"), inner_rect)

    health_ratio = current_value / max(1, max_value)
    if health_ratio >= thresholds[0]:
        health_color = pygame.Color("green")
    elif health_ratio >= thresholds[1]:
        health_color = pygame.Color("yellow")
    else:
        health_color = pygame.Color("red")
    fill_rect = inner_rect.copy()
    fill_rect.width = int(inner_rect.width * health_ratio)
    if fill_rect.width > 0:
        pygame.draw.rect(surface, health_color, fill_rect)
    surface.blit(frame, (x, y))


def draw_ammo_status(
    surface,
    weapon_state,
    font,
    screen_width,
    screen_height,
    panel_image,
    panel_size,
    panel_margin,
):
    config = weapon_state.config
    name_text = font.render(config.name, True, (255, 220, 120))
    ammo_text = font.render(
        "재장전 중..." if weapon_state.is_reloading_now() else f"{weapon_state.magazine_ammo}   {config.magazine_size}",
        True,
        (255, 180, 120) if weapon_state.is_reloading_now() else (255, 255, 255),
    )
    panel = pygame.transform.smoothscale(panel_image, panel_size)
    panel_x = screen_width - panel_size[0] - panel_margin[0]
    panel_y = screen_height - panel_size[1] - panel_margin[1]
    surface.blit(panel, (panel_x, panel_y))
    name_rect = name_text.get_rect(center=(panel_x + panel_size[0] // 2, panel_y + 3))
    ammo_rect = ammo_text.get_rect(center=(panel_x + panel_size[0] // 2, panel_y + 43))
    surface.blit(name_text, name_rect)
    surface.blit(ammo_text, ammo_rect)


def draw_ward(surface, ward_x, ward_y, camera_x, camera_y, zoom):
    screen_x = round((ward_x - camera_x) * zoom)
    screen_y = round((ward_y - camera_y) * zoom)
    radius = max(6, round(12 * zoom))
    pygame.draw.circle(surface, (120, 240, 255), (screen_x, screen_y), radius, 2)
    pygame.draw.line(surface, (120, 240, 255), (screen_x - radius, screen_y), (screen_x + radius, screen_y), 1)
    pygame.draw.line(surface, (120, 240, 255), (screen_x, screen_y - radius), (screen_x, screen_y + radius), 1)


def draw_quick_slot_cooldowns(surface, slots, cooldowns, font):
    now = pygame.time.get_ticks()
    for slot in slots:
        if not slot.assigned_skill:
            continue
        end_time = cooldowns.get(slot.assigned_skill, 0)
        if end_time <= now:
            continue
        remain = max(0.0, (end_time - now) / 1000.0)
        overlay = pygame.Surface((slot.rect.width, slot.rect.height), pygame.SRCALPHA)
        pygame.draw.rect(overlay, (0, 0, 0, 170), overlay.get_rect(), border_radius=8)
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
        text = font.render(str(number["damage"]), True, number["color"])
        text.set_alpha(round(255 * (1.0 - progress)))
        surface.blit(text, text.get_rect(center=(round(screen_x), round(screen_y))))


def draw_supply_drop(surface, supply, camera_x, camera_y, zoom, colors, now):
    x = round((supply["x"] - camera_x) * zoom)
    y = round((supply["y"] - camera_y) * zoom)
    color = colors[supply["type"]]
    warning_until = supply.get("warning_until", 0)
    if now < warning_until:
        pulse = 22 + round(8 * math.sin(now * 0.012))
        pygame.draw.circle(surface, (255, 230, 120), (x, y), max(18, round(pulse * zoom)), 3)
        pygame.draw.line(surface, (255, 240, 150), (x, max(0, y - round(150 * zoom))), (x, y), 2)
        label = pygame.font.Font(None, 26).render("보급품 낙하", True, (255, 240, 150))
        surface.blit(label, label.get_rect(center=(x, max(18, y - round(165 * zoom)))))
    box = pygame.Rect(0, 0, max(22, round(36 * zoom)), max(18, round(28 * zoom)))
    box.center = (x, y)
    pygame.draw.rect(surface, (35, 35, 45), box, border_radius=4)
    pygame.draw.rect(surface, color, box, 3, border_radius=4)
    pygame.draw.line(surface, color, (box.left, box.centery), (box.right, box.centery), 2)
