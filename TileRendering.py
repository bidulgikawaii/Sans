"""타일 이미지와 정적 월드 Surface를 생성하고 화면에 렌더링합니다."""

import random

import pygame


class TileRenderingMixin:
    def _load_placeholder_images(self):
        """맵의 각 타일 종류에 사용할 Surface를 준비합니다."""
        floor = self.IML.GetGrassTile()
        self.tile_images[0] = floor

        wall = pygame.Surface((self.tile_size, self.tile_size))
        wall_texture = pygame.transform.scale(
            self.IML.GetTileTest(),
            (self.tile_size, self.tile_size),
        )
        wall.fill((140, 180, 130))
        wall.blit(wall_texture, (0, 0))
        self.tile_images[1] = wall

        door = pygame.Surface((self.tile_size, self.tile_size))
        door.fill((140, 180, 130))
        door_width = max(8, round(self.tile_size * 0.95))
        door_height = self.tile_size
        door_x = (self.tile_size - door_width) // 2
        door_y = max(0, (self.tile_size - door_height) // 2)
        pygame.draw.rect(door, (101, 67, 33), (door_x, door_y, door_width, door_height))
        pygame.draw.rect(door, (255, 200, 100), (door_x, door_y, door_width, door_height), 2)
        pygame.draw.circle(door, (200, 150, 50), (door_x + door_width - 5, self.tile_size // 2), 3)
        self.tile_images[2] = door

        treasure = pygame.Surface((self.tile_size, self.tile_size))
        treasure.fill((140, 180, 130))
        chest_x = self.tile_size // 6
        chest_y = self.tile_size // 3
        chest_width = self.tile_size - chest_x * 2
        chest_height = max(8, self.tile_size // 3)
        pygame.draw.rect(treasure, (200, 150, 50), (chest_x, chest_y, chest_width, chest_height))
        pygame.draw.rect(treasure, (255, 200, 0), (chest_x, chest_y, chest_width, chest_height), 1)
        pygame.draw.line(
            treasure,
            (150, 100, 0),
            (self.tile_size // 2, chest_y),
            (self.tile_size // 2, chest_y + chest_height),
            1,
        )
        self.tile_images[3] = treasure

        bush = pygame.Surface((self.tile_size, self.tile_size), pygame.SRCALPHA)
        center = self.tile_size // 2
        pygame.draw.circle(bush, (45, 105, 45), (center, center), max(5, self.tile_size // 3))
        for angle in range(0, 360, 45):
            direction = pygame.Vector2(1, 0).rotate(angle)
            tip = pygame.Vector2(center, center) + direction * (self.tile_size * 0.45)
            pygame.draw.line(bush, (120, 190, 90), (center, center), tip, 2)
        self.tile_images[4] = bush

        rune = pygame.Surface((self.tile_size, self.tile_size), pygame.SRCALPHA)
        rune_center = self.tile_size // 2
        rune_points = [
            (rune_center, 4),
            (self.tile_size - 5, rune_center),
            (rune_center, self.tile_size - 4),
            (5, rune_center),
        ]
        pygame.draw.polygon(rune, (40, 180, 210, 120), rune_points)
        pygame.draw.polygon(rune, (170, 245, 255, 230), rune_points, 2)
        pygame.draw.circle(rune, (230, 255, 180, 220), (rune_center, rune_center), 3)
        self.tile_images[5] = rune

        bed = pygame.Surface((self.tile_size, self.tile_size), pygame.SRCALPHA)
        pygame.draw.rect(bed, (135, 75, 55), (3, 7, self.tile_size - 6, self.tile_size - 10), border_radius=3)
        pygame.draw.rect(bed, (235, 220, 190), (6, 10, self.tile_size - 12, self.tile_size // 2), border_radius=2)
        pygame.draw.line(bed, (90, 45, 35), (4, self.tile_size - 5), (self.tile_size - 4, self.tile_size - 5), 2)
        self.tile_images[7] = bed

        chair = pygame.Surface((self.tile_size, self.tile_size), pygame.SRCALPHA)
        pygame.draw.rect(chair, (150, 90, 45), (8, 8, self.tile_size - 16, 10), border_radius=2)
        pygame.draw.rect(chair, (120, 70, 35), (10, 17, self.tile_size - 20, 10), border_radius=2)
        pygame.draw.line(chair, (100, 55, 30), (11, 27), (8, self.tile_size - 3), 3)
        pygame.draw.line(chair, (100, 55, 30), (self.tile_size - 11, 27), (self.tile_size - 8, self.tile_size - 3), 3)
        self.tile_images[8] = chair

        stone = pygame.Surface((self.tile_size, self.tile_size), pygame.SRCALPHA)
        stone_points = [(5, 22), (9, 9), (20, 4), (29, 12), (26, 27), (14, 30)]
        pygame.draw.polygon(stone, (105, 110, 120), stone_points)
        pygame.draw.polygon(stone, (190, 195, 205), stone_points, 2)
        pygame.draw.line(stone, (145, 150, 160), (10, 12), (22, 24), 2)
        self.tile_images[9] = stone

        water = pygame.Surface((self.tile_size, self.tile_size), pygame.SRCALPHA)
        water.fill((45, 145, 205, 210))
        pygame.draw.line(water, (150, 225, 255), (4, self.tile_size // 3), (self.tile_size - 4, self.tile_size // 3), 2)
        pygame.draw.line(water, (100, 205, 245), (8, self.tile_size * 2 // 3), (self.tile_size - 6, self.tile_size * 2 // 3), 2)
        self.tile_images[6] = water

    def _build_world_surface(self):
        """정적인 맵을 하나의 Surface로 합쳐 반복 그리기 비용을 줄입니다."""
        world_size = (
            self.map_width * self.tile_size,
            self.map_height * self.tile_size,
        )
        self.world_surface = pygame.Surface(world_size).convert()
        for (tile_x, tile_y), tile in self.map_data.items():
            self._draw_world_tile(tile_x, tile_y, tile)
        self._scaled_world_surface = None
        self._scaled_world_zoom = None

    def _draw_world_tile(self, tile_x, tile_y, tile):
        self.world_surface.blit(
            self.tile_images[tile.tile_type],
            (tile_x * self.tile_size, tile_y * self.tile_size),
        )
        if tile.tile_type != 0:
            return

        tile_rng = random.Random(tile_x * 73856093 ^ tile_y * 19349663)
        tile_left = tile_x * self.tile_size
        tile_top = tile_y * self.tile_size
        for _ in range(3):
            detail_x = tile_left + tile_rng.randrange(4, self.tile_size - 4)
            detail_y = tile_top + tile_rng.randrange(4, self.tile_size - 4)
            detail_color = tile_rng.choice(((116, 161, 105), (157, 192, 138), (126, 171, 112)))
            pygame.draw.line(
                self.world_surface,
                detail_color,
                (detail_x, detail_y),
                (detail_x + tile_rng.choice((-2, -1, 1, 2)), detail_y - 3),
                1,
            )

    def draw(self, surface, camera_x, camera_y, zoom=1.0):
        """미리 합성한 월드 Surface를 카메라 위치에 맞춰 그립니다."""
        if self.world_surface is not None:
            if zoom == 1.0:
                surface.blit(self.world_surface, (-int(camera_x), -int(camera_y)))
            else:
                if self._scaled_world_zoom != zoom:
                    self._scaled_world_surface = pygame.transform.smoothscale(
                        self.world_surface,
                        (round(self.world_surface.get_width() * zoom), round(self.world_surface.get_height() * zoom)),
                    )
                    self._scaled_world_zoom = zoom
                surface.blit(self._scaled_world_surface, (-round(camera_x * zoom), -round(camera_y * zoom)))
        self.draw_stones(surface, camera_x, camera_y, zoom)

    def draw_stones(self, surface, camera_x, camera_y, zoom=1.0):
        """타일과 분리된 큰 돌 오브젝트를 그립니다."""
        for stone in self.stone_objects:
            rect = stone["rect"]
            screen_rect = pygame.Rect(
                round((rect.x - camera_x) * zoom),
                round((rect.y - camera_y) * zoom),
                max(1, round(rect.width * zoom)),
                max(1, round(rect.height * zoom)),
            )
            points = [
                (screen_rect.left + screen_rect.width // 4, screen_rect.top),
                (screen_rect.right - screen_rect.width // 5, screen_rect.top + screen_rect.height // 8),
                (screen_rect.right, screen_rect.centery),
                (screen_rect.right - screen_rect.width // 5, screen_rect.bottom),
                (screen_rect.left + screen_rect.width // 5, screen_rect.bottom - screen_rect.height // 8),
                (screen_rect.left, screen_rect.centery),
            ]
            pygame.draw.polygon(surface, (80, 85, 95), points)
            pygame.draw.polygon(surface, (185, 190, 200), points, max(1, round(2 * zoom)))
            pygame.draw.line(
                surface,
                (135, 140, 150),
                (screen_rect.left + screen_rect.width // 4, screen_rect.top + screen_rect.height // 4),
                (screen_rect.centerx, screen_rect.centery),
                max(1, round(2 * zoom)),
            )

    def clamp_camera(self, camera_x, camera_y, screen_width, screen_height, zoom=1.0):
        """카메라가 맵 바깥을 향하지 않도록 월드 좌표에서 제한합니다."""
        view_width = screen_width / zoom
        view_height = screen_height / zoom
        world_width = self.map_width * self.tile_size
        world_height = self.map_height * self.tile_size
        max_camera_x = max(0, world_width - view_width)
        max_camera_y = max(0, world_height - view_height)
        return (
            max(0, min(camera_x, max_camera_x)),
            max(0, min(camera_y, max_camera_y)),
        )