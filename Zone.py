import pygame
from Config import MAGNETIC_ZONE_FINAL_RATIO


class MagneticZone:
    """게임 시간에 따라 맵 중앙으로 줄어드는 자기장입니다."""

    def __init__(self, map_width_tiles, map_height_tiles, tile_size):
        self.world_width = map_width_tiles * tile_size
        self.world_height = map_height_tiles * tile_size
        self.center = pygame.Vector2(self.world_width / 2, self.world_height / 2)
        self.stages = ((60_000, 0.72), (110_000, 0.42), (180_000, MAGNETIC_ZONE_FINAL_RATIO))
        self._overlay = None
        self._overlay_size = None

    def bounds_at(self, elapsed_ms):
        elapsed_ms = max(0, elapsed_ms)
        if elapsed_ms < self.stages[0][0]:
            return self._rect_for_ratio(1.0)

        first_stage_time, first_target = self.stages[0]
        second_stage_time, second_target = self.stages[1]
        if elapsed_ms < second_stage_time:
            progress = (elapsed_ms - first_stage_time) / max(1, second_stage_time - first_stage_time)
            return self._rect_for_ratio(1.0 + (first_target - 1.0) * progress)

        if elapsed_ms < self.stages[2][0]:
            progress = (elapsed_ms - second_stage_time) / max(1, self.stages[2][0] - second_stage_time)
            return self._rect_for_ratio(first_target + (second_target - first_target) * progress)

        return self._rect_for_ratio(0.0)

    def _rect_for_ratio(self, ratio):
        half_width = self.world_width * ratio / 2
        half_height = self.world_height * ratio / 2
        return pygame.Rect(
            round(self.center.x - half_width),
            round(self.center.y - half_height),
            max(1, round(half_width * 2)),
            max(1, round(half_height * 2)),
        )

    def is_inside(self, world_x, world_y, elapsed_ms):
        return self.bounds_at(elapsed_ms).collidepoint(world_x, world_y)

    def damage_per_second(self, outside_ms):
        outside_seconds = max(0.0, outside_ms / 1000.0)
        if outside_seconds < 3.0:
            return 0.0
        return 4.0 + (outside_seconds - 3.0) * 2.0

    def draw(self, surface, camera_x, camera_y, zoom, elapsed_ms):
        safe_rect = self.bounds_at(elapsed_ms)
        screen_rect = pygame.Rect(
            round((safe_rect.left - camera_x) * zoom),
            round((safe_rect.top - camera_y) * zoom),
            max(1, round(safe_rect.width * zoom)),
            max(1, round(safe_rect.height * zoom)),
        )
        if self._overlay_size != surface.get_size():
            self._overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
            self._overlay_size = surface.get_size()
        overlay = self._overlay
        overlay.fill((190, 20, 35, 92))
        pygame.draw.rect(overlay, (0, 0, 0, 0), screen_rect)
        surface.blit(overlay, (0, 0))
        pygame.draw.rect(surface, (255, 90, 100), screen_rect, max(2, round(3 * zoom)))

    def stage_text(self, elapsed_ms):
        if elapsed_ms < self.stages[0][0]:
            return "자기장 형성 중"
        if elapsed_ms < self.stages[1][0]:
            return "자기장 1단계"
        if elapsed_ms < self.stages[2][0]:
            return "자기장 2단계"
        return "자기장 중앙 고정"

    def next_stage_remaining_ms(self, elapsed_ms):
        for stage_time, _ratio in self.stages:
            if elapsed_ms < stage_time:
                return stage_time - max(0, elapsed_ms)
        return 0
