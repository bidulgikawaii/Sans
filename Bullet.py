import pygame
import math
import os
import time
from Config import (
    BULLET_IMAGE_FILE,
    DEFAULT_BULLET_DAMAGE,
    DEFAULT_BULLET_SIZE,
    DEFAULT_WEAPON_ID,
)

class Bullet:
    def __init__(
        self,
        size=DEFAULT_BULLET_SIZE,
        damage=DEFAULT_BULLET_DAMAGE,
        owner_id=None,
        weapon_id=DEFAULT_WEAPON_ID,
    ):
        image_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "Image",
            BULLET_IMAGE_FILE,
        )
        bullet_image = pygame.image.load(image_path).convert_alpha()
        image_width = max(8, size * 4)
        image_height = max(1, round(bullet_image.get_height() * image_width / bullet_image.get_width()))
        self.surface = pygame.transform.smoothscale(
            bullet_image,
            (image_width, image_height),
        )
        
        # 좌표 및 속도 초기화
        self.x = 0
        self.y = 0
        self.speed_x = 0
        self.speed_y = 0

        # 현재 이 총알이 화면에서 움직이고 있는 상태인가?
        self.is_active = False
        self.damage = damage
        self.owner_id = owner_id
        self.weapon_id = weapon_id
        self.angle = 0.0
        self.life_time = 2.5
        self.spawn_time = 0.0

    @property
    def rect(self):
        return pygame.Rect(round(self.x), round(self.y), self.surface.get_width(), self.surface.get_height())

    def launch(self, start_x, start_y, target_x, target_y, speed=15):
        # 발사 위치 설정 (보통 플레이어의 화면 중심 좌표)
        self.x = start_x
        self.y = start_y

        # 🌟 3. 목표물과의 거리 차이(dx, dy) 계산
        dx = target_x - start_x
        dy = target_y - start_y

        # 🌟 4. atan2를 이용해 목표물까지의 정확한 각도(라디안) 계산
        angle_rad = math.atan2(dy, dx)
        self.angle = math.degrees(angle_rad)

        # 🌟 5. 삼각함수를 이용해 매 프레임 이동할 X축, Y축 속도 분할 분배
        self.speed_x = math.cos(angle_rad) * speed
        self.speed_y = math.sin(angle_rad) * speed

        # 총알 활성화
        self.is_active = True
        self.spawn_time = time.monotonic()

    def update(self):
        # 활성화 상태일 때만 매 프레임 위치 이동
        if self.is_active:
            self.x += self.speed_x
            self.y += self.speed_y

            if time.monotonic() - self.spawn_time > self.life_time:
                self.is_active = False

    def draw(self, display, camera_x=0, camera_y=0, zoom=1.0, force_visible=False):
        # 활성화 상태일 때만 메인 화면(display)에 총알 그리기
        if self.is_active:
            image = pygame.transform.rotate(self.surface, self.angle + 35)
            if zoom != 1.0:
                image = pygame.transform.smoothscale(
                    image,
                    (
                        max(1, round(image.get_width() * zoom)),
                        max(1, round(image.get_height() * zoom)),
                    ),
                )

            center_x = (self.x - camera_x + self.surface.get_width() / 2) * zoom
            center_y = (self.y - camera_y + self.surface.get_height() / 2) * zoom
            display.blit(image, image.get_rect(center=(round(center_x), round(center_y))))
            return

        # 총알은 시야 레이어에서 가려지지 않도록 최종 렌더 단계에서 강제로 다시 그린다.
        # 이 함수는 기존 호출 호환성을 위해 유지하며, force_visible=True가 들어오면
        # 시야 검사를 우회해 최종 레이어에 그린다.