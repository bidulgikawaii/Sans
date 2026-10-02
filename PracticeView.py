import pygame

from GameRendering import draw_player_hitboxes
from Tool_Cordinate import world_to_screen


class PracticeView:
    """훈련장 더미와 훈련 전용 상태 표시를 그립니다."""

    def __init__(self, surface, font, screen_width):
        self.surface = surface
        self.font = font
        self.screen_width = screen_width

    def draw_training_dummy(self, dummy, camera_x, camera_y, zoom):
        if dummy is None or dummy.Hp <= 0:
            return

        screen_x, screen_y = world_to_screen(
            dummy.X, dummy.Y, camera_x, camera_y, zoom
        )
        image = dummy.image if zoom == 1.0 else pygame.transform.scale(
            dummy.image,
            (
                round(dummy.image.get_width() * zoom),
                round(dummy.image.get_height() * zoom),
            ),
        )
        self.surface.blit(image, (screen_x, screen_y))
        hp_text = self.font.render(
            f"더미 {dummy.Hp}/{dummy.MaxHp}", True, (255, 235, 120)
        )
        self.surface.blit(
            hp_text,
            hp_text.get_rect(
                midbottom=(
                    round(screen_x + image.get_width() / 2),
                    round(screen_y - 8),
                )
            ),
        )

    def draw_training_dummy_hitboxes(self, dummy, camera_x, camera_y, zoom):
        if dummy is None or dummy.Hp <= 0:
            return
        draw_player_hitboxes(
            self.surface,
            dummy.head_hitbox,
            dummy.body_hitbox,
            camera_x,
            camera_y,
            zoom,
        )

    def draw_training_status(
        self, vision_shape, camera_fov, max_camera_fov, zone_status, zone_color
    ):
        inventory_text = self.font.render(
            "🎒 인벤토리: [I]", True, (170, 220, 180)
        )
        self.surface.blit(inventory_text, (self.screen_width - 300, 20))

        vision_text = self.font.render(
            f"시야: {vision_shape} [V]", True, (255, 220, 120)
        )
        self.surface.blit(vision_text, (self.screen_width - 300, 55))

        fov_text = self.font.render(
            f"카메라 FOV: {camera_fov:.2f} / 최대 {max_camera_fov:.2f}",
            True,
            (180, 230, 255),
        )
        self.surface.blit(fov_text, (self.screen_width - 420, 90))

        zone_text = self.font.render(zone_status, True, zone_color)
        self.surface.blit(zone_text, (self.screen_width - 420, 125))