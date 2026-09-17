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
        9: (115, 120, 135),
    }

    def __init__(self, tile_generator, size=(260, 260), margin=(30, 30), font=None):
        self.tile_generator = tile_generator
        self.size = size
        self.margin = margin
        self.font = font or pygame.font.Font(None, 20)
        self._map_surface = None
        self._map_signature = None

    def _get_map_signature(self):
        generator = self.tile_generator
        return generator.map_width, generator.map_height, generator.tile_size, len(generator.map_data)

    def _build_map_surface(self):
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
    ):
        if self._map_surface is None or self._map_signature != self._get_map_signature():
            self._build_map_surface()

        panel_width = self.size[0] + 16
        panel_height = self.size[1] + 42
        panel_y = self.margin[1]
        alert_width = 190 if magnetic_zone is not None else 0
        total_panel_width = panel_width + alert_width
        panel_x = surface.get_width() - total_panel_width - self.margin[0]
        panel = pygame.Surface((total_panel_width, panel_height), pygame.SRCALPHA)
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

        marker_surface = pygame.Surface(self.size, pygame.SRCALPHA)
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
        for player_id, player_info in (players or {}).items():
            if local_player_id is not None and int(player_id) == int(local_player_id):
                continue
            player_position = (
                player_info.get("posX", 0) + self.tile_generator.tile_size / 2,
                player_info.get("posY", 0) + self.tile_generator.tile_size / 2,
            )
            if any(
                (player_position[0] - alert_x) ** 2 + (player_position[1] - alert_y) ** 2
                <= (self.tile_generator.tile_size * 1.5) ** 2
                for alert_x, alert_y in alert_positions
            ):
                player_marker = self._world_to_map(*player_position)
                pygame.draw.circle(marker_surface, (255, 225, 90), player_marker, 5)
                pygame.draw.circle(marker_surface, (255, 245, 150), player_marker, 7, 2)

        for alert_x, alert_y, _remaining_ms in rune_alerts or ():
            alert_position = self._world_to_map(alert_x, alert_y)
            pygame.draw.circle(marker_surface, (255, 225, 90), alert_position, 7, 2)
            pygame.draw.circle(marker_surface, (255, 245, 150), alert_position, 3)
        if training_dummy is not None and training_dummy.Hp > 0:
            dummy_x, dummy_y = self._world_to_map(
                training_dummy.X + training_dummy.rect.width / 2,
                training_dummy.Y + training_dummy.rect.height / 2,
            )
            pygame.draw.circle(marker_surface, (255, 225, 100), (dummy_x, dummy_y), 4)

        panel.blit(marker_surface, (map_x, 28))
        surface.blit(panel, (panel_x, panel_y))
