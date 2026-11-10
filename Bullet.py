import pygame
import math
import os
import time
from functools import lru_cache
from Config import (
    BULLET_IMAGE_FILE,
    DEFAULT_BULLET_DAMAGE,
    DEFAULT_BULLET_SIZE,
    DEFAULT_WEAPON_ID,
)


_BULLET_IMAGE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "Image", BULLET_IMAGE_FILE
)
_SPIRIT_TRIAL_GHOST_FRAMES = ()
_SPIRIT_TRIAL_AURA_FRAMES = ()
_BLACK_HOLE_BULLET_FRAMES = ()


def set_spirit_trial_animations(ghost_frames, aura_frames):
    global _SPIRIT_TRIAL_GHOST_FRAMES, _SPIRIT_TRIAL_AURA_FRAMES
    _SPIRIT_TRIAL_GHOST_FRAMES = tuple(ghost_frames)
    _SPIRIT_TRIAL_AURA_FRAMES = tuple(aura_frames)


def set_black_hole_bullet_frames(frames):
    global _BLACK_HOLE_BULLET_FRAMES
    _BLACK_HOLE_BULLET_FRAMES = tuple(frames)

# 크기별 총알 Surface를 재사용해 발사 때마다 같은 이미지 변환을 반복하지 않습니다.

@lru_cache(maxsize=16)
def _get_bullet_surface(size):
    """재사용 가능한 크기별 총알 이미지를 한 번만 생성합니다."""
    source = _get_bullet_image()
    image_width = max(8, round(size * 8))
    image_height = max(1, round(source.get_height() * image_width / source.get_width()))
    surface = pygame.transform.smoothscale(source, (image_width, image_height))
    return surface


@lru_cache(maxsize=1)
def _get_bullet_image():
    image = pygame.image.load(_BULLET_IMAGE_PATH).convert_alpha()
    visible_bounds = image.get_bounding_rect(min_alpha=8)
    if visible_bounds.width == 0 or visible_bounds.height == 0:
        raise ValueError(f"총알 이미지에 표시할 픽셀이 없습니다: {_BULLET_IMAGE_PATH}")
    return image.subsurface(visible_bounds).copy()

# 발사 시점의 원점과 조준 방향으로 궤적을 고정해, 이후 플레이어 이동과 분리합니다.
class Bullet:
    def __init__(
        self,
        size=DEFAULT_BULLET_SIZE,
        damage=DEFAULT_BULLET_DAMAGE,
        owner_id=None,
        weapon_id=DEFAULT_WEAPON_ID,
        stun_ms=0,
    ):
        if weapon_id == "spirit_trial":
            self.surface = (
                _SPIRIT_TRIAL_GHOST_FRAMES[0]
                if _SPIRIT_TRIAL_GHOST_FRAMES
                else pygame.Surface((34, 16), pygame.SRCALPHA)
            )
        elif weapon_id == "blackhole_generator":
            self.surface = (
                _BLACK_HOLE_BULLET_FRAMES[0]
                if _BLACK_HOLE_BULLET_FRAMES
                else pygame.Surface((32, 32), pygame.SRCALPHA)
            )
        elif weapon_id == "Revolver_golden":
            self.surface = pygame.Surface((30, 18), pygame.SRCALPHA)
            pygame.draw.ellipse(self.surface, (255, 195, 45, 80), (0, 1, 30, 16))
            pygame.draw.ellipse(self.surface, (255, 220, 95, 230), (4, 4, 23, 10))
            pygame.draw.ellipse(self.surface, (255, 250, 210), (10, 5, 12, 8))
        else:
            self.surface = _get_bullet_surface(size)
        
        # 좌표 및 속도 초기화
        self.x = 0
        self.y = 0
        self.previous_x = 0
        self.previous_y = 0
        self.speed_x = 0
        self.speed_y = 0

        # 현재 이 총알이 화면에서 움직이고 있는 상태인가?
        self.is_active = False
        self.damage = damage
        self.owner_id = owner_id
        self.weapon_id = weapon_id
        self.stun_ms = stun_ms
        self.angle = 0.0
        self.life_time = 2.5
        self.spawn_time = 0.0
        self.flight_start_time = 0.0
        self.launch_hold_ms = 0
        self.reflect_until = 0

    @property
    def rect(self):
        rect = (
            pygame.Rect(0, 0, 30, 30)
            if self.weapon_id == "spirit_trial"
            else self.surface.get_rect()
        )
        rect.center = (round(self.x), round(self.y))
        return rect

    @property
    def collision_rect(self):
        rect = pygame.Rect(0, 0, 4, 4)
        rect.center = self.rect.center
        return rect

    @property
    def pierces_walls(self):
        return False

    def launch(self, start_x, start_y, target_x, target_y, speed=15, hold_ms=0):
        # 발사 위치 설정 (보통 플레이어의 화면 중심 좌표)
        self.x = start_x
        self.y = start_y
        self.previous_x = start_x
        self.previous_y = start_y

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
        self.launch_hold_ms = max(0, round(hold_ms))
        self.flight_start_time = self.spawn_time + self.launch_hold_ms / 1000

    def update(self):
        # 활성화 상태일 때만 매 프레임 위치 이동
        if self.is_active:
            if time.monotonic() < self.flight_start_time:
                return
            self.previous_x = self.x
            self.previous_y = self.y
            self.x += self.speed_x
            self.y += self.speed_y

            if time.monotonic() - self.spawn_time > self.life_time:
                self.is_active = False

    def reflect(self, horizontal=False, vertical=False):
        if horizontal:
            self.speed_x *= -1
        if vertical:
            self.speed_y *= -1
        self.angle = math.degrees(math.atan2(self.speed_y, self.speed_x))
        self.x += self.speed_x * 2
        self.y += self.speed_y * 2
        self.reflect_until = pygame.time.get_ticks() + 80

    def draw(self, display, camera_x=0, camera_y=0, zoom=1.0, force_visible=False):
        # 활성화 상태일 때만 메인 화면(display)에 총알 그리기
        if self.is_active:
            if (
                self.weapon_id == "spirit_trial"
                and _SPIRIT_TRIAL_GHOST_FRAMES
            ):
                frame_index = (pygame.time.get_ticks() // 70) % len(
                    _SPIRIT_TRIAL_GHOST_FRAMES
                )
                source_image = _SPIRIT_TRIAL_GHOST_FRAMES[frame_index]
            elif (
                self.weapon_id == "blackhole_generator"
                and _BLACK_HOLE_BULLET_FRAMES
            ):
                frame_index = (pygame.time.get_ticks() // 45) % len(
                    _BLACK_HOLE_BULLET_FRAMES
                )
                source_image = _BLACK_HOLE_BULLET_FRAMES[frame_index]
            else:
                source_image = self.surface
            image = pygame.transform.rotate(source_image, -self.angle)
            if zoom != 1.0:
                image = pygame.transform.smoothscale(
                    image,
                    (
                        max(1, round(image.get_width() * zoom)),
                        max(1, round(image.get_height() * zoom)),
                    ),
                )

            center_x = (self.x - camera_x) * zoom
            center_y = (self.y - camera_y) * zoom
            if self.weapon_id == "blackhole_generator" and not _BLACK_HOLE_BULLET_FRAMES:
                pulse = 1.0 + 0.22 * math.sin(pygame.time.get_ticks() * 0.03)
                pygame.draw.circle(
                    display,
                    (145, 80, 230),
                    (round(center_x), round(center_y)),
                    max(8, round(18 * zoom * pulse)),
                    max(1, round(2 * zoom)),
                )
                pygame.draw.circle(
                    display,
                    (30, 15, 45),
                    (round(center_x), round(center_y)),
                    max(5, round(9 * zoom)),
                )
            elif self.weapon_id == "Revolver_golden":
                pygame.draw.circle(
                    display,
                    (255, 220, 95),
                    (round(center_x), round(center_y)),
                    max(4, round(9 * zoom)),
                    max(1, round(2 * zoom)),
                )
            elif self.weapon_id == "spirit_trial":
                previous_x = (self.previous_x - camera_x) * zoom
                previous_y = (self.previous_y - camera_y) * zoom
                now = pygame.time.get_ticks()
                pulse = 1.0 + 0.08 * math.sin(now * 0.025)
                if _SPIRIT_TRIAL_AURA_FRAMES:
                    aura_index = (now // 65) % len(_SPIRIT_TRIAL_AURA_FRAMES)
                    aura = _SPIRIT_TRIAL_AURA_FRAMES[aura_index]
                    aura_size = max(1, round(aura.get_width() * zoom * pulse))
                    if aura_size != aura.get_width():
                        aura = pygame.transform.smoothscale(
                            aura, (aura_size, aura_size)
                        )
                    display.blit(
                        aura,
                        aura.get_rect(center=(round(center_x), round(center_y))),
                    )
                pygame.draw.line(
                    display,
                    (60, 190, 255),
                    (round(previous_x), round(previous_y)),
                    (round(center_x), round(center_y)),
                    max(2, round(4 * zoom * pulse)),
                )
            elif self.stun_ms:
                pulse = 1.0 + 0.15 * math.sin(pygame.time.get_ticks() * 0.025)
                glow_radius = max(4, round(7 * zoom * pulse))
                pygame.draw.circle(
                    display,
                    (120, 225, 255),
                    (round(center_x), round(center_y)),
                    glow_radius,
                    max(1, round(2 * zoom)),
                )
            display.blit(image, image.get_rect(center=(round(center_x), round(center_y))))
            if self.stun_ms:
                angle = math.radians(self.angle)
                direction = (math.cos(angle), math.sin(angle))
                perpendicular = (-direction[1], direction[0])
                bolt_points = []
                for along, across in (
                    (-5, -4),
                    (-1, -1),
                    (-3, 2),
                    (2, 4),
                    (1, 0),
                    (5, -3),
                ):
                    bolt_points.append(
                        (
                            round(center_x + (direction[0] * along + perpendicular[0] * across) * zoom),
                            round(center_y + (direction[1] * along + perpendicular[1] * across) * zoom),
                        )
                    )
                pygame.draw.lines(
                    display, (70, 195, 255), False, bolt_points,
                    max(1, round(2 * zoom)),
                )
                pygame.draw.lines(
                    display, (220, 250, 255), False, bolt_points,
                    max(1, round(zoom)),
                )
            return

        # 총알은 시야 레이어에서 가려지지 않도록 최종 렌더 단계에서 강제로 다시 그린다.
        # 이 함수는 기존 호출 호환성을 위해 유지하며, force_visible=True가 들어오면
        # 시야 검사를 우회해 최종 레이어에 그린다.
