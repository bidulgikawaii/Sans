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
    }

    def __init__(self, tile_generator, size=(260, 260), margin=(30, 30)):
        self.tile_generator = tile_generator
        self.size = size
        self.margin = margin
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

    def draw(self, surface, local_position, players=None, local_player_id=None, training_dummy=None):
        if self._map_surface is None or self._map_signature != self._get_map_signature():
            self._build_map_surface()

        panel_width = self.size[0] + 16
        panel_height = self.size[1] + 42
        panel_x = surface.get_width() - panel_width - self.margin[0]
        panel_y = self.margin[1]
        panel = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
        pygame.draw.rect(panel, (12, 18, 22, 225), panel.get_rect(), border_radius=8)
        pygame.draw.rect(panel, (170, 205, 190, 220), panel.get_rect(), 2, border_radius=8)
        panel.blit(self._map_surface, (8, 28))

        title_font = pygame.font.Font(None, 20)
        title = title_font.render("MINIMAP", True, (235, 245, 230))
        panel.blit(title, (12, 7))

        marker_surface = pygame.Surface(self.size, pygame.SRCALPHA)
        if training_dummy is not None and training_dummy.Hp > 0:
            dummy_x, dummy_y = self._world_to_map(
                training_dummy.X + training_dummy.rect.width / 2,
                training_dummy.Y + training_dummy.rect.height / 2,
            )
            pygame.draw.circle(marker_surface, (255, 225, 100), (dummy_x, dummy_y), 4)

        panel.blit(marker_surface, (8, 28))
        surface.blit(panel, (panel_x, panel_y))
