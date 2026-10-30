import math

import pygame


class MiniMap:
    """Draws a cached overview of the generated map."""

    TILE_COLORS = {
        0: (92, 125, 82),
        1: (92, 65, 58),
        2: (166, 126, 72),
        3: (224, 178, 72),
        4: (48, 116, 88),
        5: (70, 150, 106),
        6: (92, 168, 118),
        7: (128, 82, 62),
        8: (155, 105, 55),
    }

    def __init__(self, tile_generator, size=(260, 260), margin=(30, 30), font=None):
        self.tile_generator = tile_generator
        self.size = size
        self.margin = margin
        self.font = font or pygame.font.Font(None, 20)
        self._map_surface = None
        self._map_signature = None
        self._panel_surface = None
        self._panel_surface_size = None
        self._marker_surface = pygame.Surface(self.size, pygame.SRCALPHA)
        self._spectator_map_surface = None
        self._spectator_map_signature = None
        self._spectator_map_size = None
        self._spectator_sprite = None
        self._spectator_sprite_key = None

    def _get_map_signature(self):
        generator = self.tile_generator
        return (
            generator.map_width,
            generator.map_height,
            generator.tile_size,
            getattr(generator, "map_revision", 0),
        )

    def _build_map_surface(self):
        # 정적인 타일 지형은 축소 Surface로 한 번 그려 두고, 프레임마다 동적 표식만 덧그립니다.
        generator = self.tile_generator
        map_width = max(1, generator.map_width)
        map_height = max(1, generator.map_height)
        map_surface = pygame.Surface(self.size)
        map_surface.fill(self.TILE_COLORS[0])

        for (tile_x, tile_y), tile in generator.map_data.items():
            left = round(tile_x * self.size[0] / map_width)
            top = round(tile_y * self.size[1] / map_height)
            right = round((tile_x + 1) * self.size[0] / map_width)
            bottom = round((tile_y + 1) * self.size[1] / map_height)
            color = self.TILE_COLORS.get(tile.tile_type, self.TILE_COLORS[0])
            pygame.draw.rect(map_surface, color, (left, top, max(1, right - left), max(1, bottom - top)))

        self._map_surface = map_surface
        self._map_signature = self._get_map_signature()

    def _world_to_map(self, world_x, world_y):
        generator = self.tile_generator
        world_width = max(1, generator.map_width * generator.tile_size)
        world_height = max(1, generator.map_height * generator.tile_size)
        return (
            round(world_x * self.size[0] / world_width),
            round(world_y * self.size[1] / world_height),
        )

    def draw(
        self,
        surface,
        local_position,
        players=None,
        local_player_id=None,
        training_dummy=None,
        rune_alerts=None,
        magnetic_zone=None,
        zone_elapsed_ms=0,
        supply_drops=None,
        unique_supply_seconds=None,
    ):
        if self._map_surface is None or self._map_signature != self._get_map_signature():
            self._build_map_surface()

        panel_width = self.size[0] + 16
        panel_height = self.size[1] + 42
        panel_y = self.margin[1]
        alert_width = 190 if magnetic_zone is not None or unique_supply_seconds is not None else 0
        total_panel_width = panel_width + alert_width
        panel_x = surface.get_width() - total_panel_width - self.margin[0]
        panel_size = (total_panel_width, panel_height)
        if self._panel_surface_size != panel_size:
            self._panel_surface = pygame.Surface(panel_size, pygame.SRCALPHA)
            self._panel_surface_size = panel_size
        panel = self._panel_surface
        panel.fill((0, 0, 0, 0))
        pygame.draw.rect(panel, (12, 18, 22, 225), panel.get_rect(), border_radius=8)
        pygame.draw.rect(panel, (170, 205, 190, 220), panel.get_rect(), 2, border_radius=8)
        map_x = alert_width + 8
        panel.blit(self._map_surface, (map_x, 28))

        title_font = self.font
        title = title_font.render("MINIMAP", True, (235, 245, 230))
        panel.blit(title, (map_x + 4, 7))

        if magnetic_zone is not None:
            remaining_ms = magnetic_zone.next_stage_remaining_ms(zone_elapsed_ms)
            alert_font = self.font
            if remaining_ms:
                seconds = max(1, (remaining_ms + 999) // 1000)
                panel.blit(alert_font.render("자기장 접근", True, (255, 125, 135)), (12, 48))
                panel.blit(alert_font.render(f"다음 축소까지 {seconds}초", True, (255, 230, 170)), (12, 76))
            else:
                panel.blit(alert_font.render("자기장 중앙 고정", True, (255, 170, 170)), (12, 48))
        if unique_supply_seconds is not None:
            alert_font = self.font
            panel.blit(alert_font.render("유니크 보급품", True, (255, 220, 100)), (12, 118))
            panel.blit(
                alert_font.render(f"도착까지 {unique_supply_seconds}초", True, (255, 245, 180)),
                (12, 146),
            )

        marker_surface = self._marker_surface
        marker_surface.fill((0, 0, 0, 0))
        if magnetic_zone is not None:
            zone_rect = magnetic_zone.bounds_at(zone_elapsed_ms)
            zone_left, zone_top = self._world_to_map(zone_rect.left, zone_rect.top)
            zone_right, zone_bottom = self._world_to_map(zone_rect.right, zone_rect.bottom)
            pygame.draw.rect(
                marker_surface,
                (255, 90, 105),
                (zone_left, zone_top, max(1, zone_right - zone_left), max(1, zone_bottom - zone_top)),
                2,
            )
        local_marker = self._world_to_map(*local_position)
        pygame.draw.circle(marker_surface, (90, 210, 255), local_marker, 5)
        pygame.draw.circle(marker_surface, (220, 250, 255), local_marker, 7, 2)

        # 룬 경보 위치와 가까운 상대만 경보를 밟은 플레이어로 표시합니다.
        alert_positions = [(alert_x, alert_y) for alert_x, alert_y, _remaining_ms in rune_alerts or ()]
        alert_distance_squared = (self.tile_generator.tile_size * 1.5) ** 2
        for player_id, player_info in (players or {}).items():
            if local_player_id is not None and str(player_id) == str(local_player_id):
                continue
            if player_info.get("hidden", False) or player_info.get("hp", 1) <= 0:
                continue
            player_position = (
                player_info.get("posX", 0) + self.tile_generator.tile_size / 2,
                player_info.get("posY", 0) + self.tile_generator.tile_size / 2,
            )
            if any(
                (player_position[0] - alert_x) ** 2 + (player_position[1] - alert_y) ** 2
                <= alert_distance_squared
                for alert_x, alert_y in alert_positions
            ):
                player_marker = self._world_to_map(*player_position)
                pygame.draw.circle(marker_surface, (255, 225, 90), player_marker, 5)
                pygame.draw.circle(marker_surface, (255, 245, 150), player_marker, 7, 2)

        for alert_x, alert_y, _remaining_ms in rune_alerts or ():
            alert_position = self._world_to_map(alert_x, alert_y)
            pygame.draw.circle(marker_surface, (255, 225, 90), alert_position, 7, 2)
            pygame.draw.circle(marker_surface, (255, 245, 150), alert_position, 3)
        for supply in supply_drops or ():
            if supply.get("type") != "special_weapon":
                continue
            drop_position = self._world_to_map(supply["x"], supply["y"])
            pulse = 8 + round(2 * math.sin(pygame.time.get_ticks() * 0.012))
            pygame.draw.circle(marker_surface, (255, 225, 85), drop_position, pulse, 2)
            pygame.draw.circle(marker_surface, (255, 245, 160), drop_position, 3)
        if training_dummy is not None and training_dummy.Hp > 0:
            dummy_x, dummy_y = self._world_to_map(
                training_dummy.X + training_dummy.rect.width / 2,
                training_dummy.Y + training_dummy.rect.height / 2,
            )
            pygame.draw.circle(marker_surface, (255, 225, 100), (dummy_x, dummy_y), 4)

        panel.blit(marker_surface, (map_x, 28))
        surface.blit(panel, (panel_x, panel_y))

    def draw_spectator(
        self,
        surface,
        players,
        player_sprite,
        selected_player_id=None,
        bullets=None,
        skill_effects=None,
        weapon_image_getter=None,
    ):
        """전체 맵에 생존 플레이어와 관전자 전용 전투 효과를 표시합니다."""
        if self._map_surface is None or self._map_signature != self._get_map_signature():
            self._build_map_surface()

        surface.fill((8, 13, 22))
        title = self.font.render(
            "관전 모드  ·  ←/→ 대상 변경  ·  TAB 또는 Esc 종료",
            True,
            (240, 245, 255),
        )
        surface.blit(title, title.get_rect(center=(surface.get_width() // 2, 48)))

        margin = 72
        map_top = 92
        footer_height = 86
        available_width = max(1, surface.get_width() - margin * 2)
        available_height = max(1, surface.get_height() - map_top - footer_height - margin)
        scale = min(
            available_width / max(1, self._map_surface.get_width()),
            available_height / max(1, self._map_surface.get_height()),
        )
        map_size = (
            max(1, round(self._map_surface.get_width() * scale)),
            max(1, round(self._map_surface.get_height() * scale)),
        )
        if (
            self._spectator_map_surface is None
            or self._spectator_map_signature != self._map_signature
            or self._spectator_map_size != map_size
        ):
            self._spectator_map_surface = pygame.transform.smoothscale(
                self._map_surface, map_size
            )
            self._spectator_map_signature = self._map_signature
            self._spectator_map_size = map_size
        map_image = self._spectator_map_surface
        map_rect = map_image.get_rect(
            center=(surface.get_width() // 2, map_top + available_height // 2)
        )
        pygame.draw.rect(surface, (8, 12, 18), map_rect.inflate(12, 12), border_radius=8)
        surface.blit(map_image, map_rect)
        pygame.draw.rect(surface, (180, 205, 225), map_rect, 2, border_radius=4)

        world_width = max(1, self.tile_generator.map_width * self.tile_generator.tile_size)
        world_height = max(1, self.tile_generator.map_height * self.tile_generator.tile_size)

        def world_to_spectator(world_x, world_y):
            return (
                map_rect.left + round(world_x * map_rect.width / world_width),
                map_rect.top + round(world_y * map_rect.height / world_height),
            )

        skill_colors = {
            "폭탄받아라!": (255, 150, 70),
            "매의 눈": (120, 220, 255),
            "와드": (120, 240, 255),
            "부활의 차": (255, 210, 120),
            "보호막": (100, 220, 255),
            "은신": (190, 190, 255),
            "텔포": (150, 255, 170),
            "기절탄": (255, 245, 150),
        }
        for effect in skill_effects or ():
            effect_x, effect_y = world_to_spectator(effect.get("x", 0), effect.get("y", 0))
            age_ratio = min(1.0, effect.get("age_ms", 0) / 1400)
            radius = 8 + round(18 * age_ratio)
            color = skill_colors.get(effect.get("skill"), (255, 225, 150))
            pygame.draw.circle(surface, color, (effect_x, effect_y), radius, 2)
            skill_label = self.font.render(str(effect.get("skill", "스킬")), True, color)
            surface.blit(skill_label, skill_label.get_rect(midbottom=(effect_x, effect_y - radius - 3)))

        for bullet in bullets or ():
            bullet_x, bullet_y = world_to_spectator(bullet.get("x", 0), bullet.get("y", 0))
            angle = bullet.get("angle", 0.0)
            trail_length = 11
            trail_start = (
                round(bullet_x - math.cos(angle) * trail_length),
                round(bullet_y - math.sin(angle) * trail_length),
            )
            color = (120, 230, 255) if bullet.get("stun_ms", 0) else (255, 235, 155)
            pygame.draw.line(surface, color, trail_start, (bullet_x, bullet_y), 3)
            pygame.draw.circle(surface, (255, 255, 235), (bullet_x, bullet_y), 2)

        selected_info = None
        alive_players = []
        sprite_size = max(16, min(30, round(24 * scale)))
        sprite_key = (id(player_sprite), sprite_size)
        if self._spectator_sprite_key != sprite_key:
            self._spectator_sprite = pygame.transform.smoothscale(
                player_sprite, (sprite_size, sprite_size)
            )
            self._spectator_sprite_key = sprite_key
        sprite = self._spectator_sprite
        for player_id, player_info in players.items():
            if player_info.get("hidden", False) or player_info.get("hp", 0) <= 0:
                continue
            alive_players.append((player_id, player_info))
            center_x, center_y = world_to_spectator(
                player_info.get("posX", 0) + player_sprite.get_width() / 2,
                player_info.get("posY", 0) + player_sprite.get_height() / 2,
            )
            player_rect = sprite.get_rect(center=(center_x, center_y))
            if str(player_id) == str(selected_player_id):
                pygame.draw.rect(
                    surface, (255, 220, 100), player_rect.inflate(8, 8), 2, border_radius=4
                )
                selected_info = player_info
            surface.blit(sprite, player_rect)

            weapon_id = player_info.get("weapon_id")
            weapon_image = (
                weapon_image_getter(weapon_id)
                if weapon_image_getter and weapon_id
                else None
            )
            angle = math.radians(player_info.get("angle", 0.0))
            weapon_length = max(9, round(sprite_size * 1.2))
            weapon_tip = (
                round(center_x + math.cos(angle) * (sprite_size * 0.9)),
                round(center_y + math.sin(angle) * (sprite_size * 0.9)),
            )
            pygame.draw.line(surface, (255, 232, 155), (center_x, center_y), weapon_tip, 2)
            if weapon_image is not None:
                if weapon_id == "pistol":
                    weapon_image = pygame.transform.flip(weapon_image, True, False)
                image_width = weapon_length
                image_height = max(
                    3,
                    round(weapon_image.get_height() * image_width / max(1, weapon_image.get_width())),
                )
                weapon_image = pygame.transform.smoothscale(
                    weapon_image, (image_width, image_height)
                )
                weapon_image = pygame.transform.rotate(weapon_image, -math.degrees(angle))
                weapon_center = (
                    round(center_x + math.cos(angle) * sprite_size * 0.35),
                    round(center_y + math.sin(angle) * sprite_size * 0.35),
                )
                surface.blit(weapon_image, weapon_image.get_rect(center=weapon_center))
            if player_info.get("shield_active", False):
                pygame.draw.circle(
                    surface, (100, 220, 255), (center_x, center_y),
                    max(8, sprite_size), 2,
                )
            if player_info.get("stealth", False):
                pygame.draw.circle(
                    surface, (190, 190, 255), (center_x, center_y),
                    max(10, sprite_size + 4), 1,
                )
            if player_info.get("revive_armed", False):
                pygame.draw.circle(
                    surface, (255, 210, 120), (center_x, center_y),
                    max(12, sprite_size + 7), 1,
                )

        if selected_info is not None:
            label = (
                f"관전 대상: {selected_info.get('name', '플레이어')}  "
                f"HP {selected_info.get('hp', 0)}"
            )
        else:
            label = f"생존 플레이어 {len(alive_players)}명"
        footer = self.font.render(label, True, (255, 225, 150))
        surface.blit(footer, footer.get_rect(center=(surface.get_width() // 2, surface.get_height() - 34)))
