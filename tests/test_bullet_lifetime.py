import math
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from Bullet import Bullet
from Config import (
    BULLET_MAX_TRAVEL_DISTANCE,
    FLAGDOWN_MAP_HEIGHT_TILES,
    FLAGDOWN_MAP_WIDTH_TILES,
    FPS,
)
from GoldenRevolverEffects import GOLDEN_BULLET_MAX_SPEED_MULTIPLIER


class BulletLifetimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        if pygame.display.get_surface() is None:
            pygame.display.set_mode((1, 1))

    def test_fast_bullets_expire_before_crossing_the_short_map_edge(self):
        map_short_edge = min(
            FLAGDOWN_MAP_WIDTH_TILES, FLAGDOWN_MAP_HEIGHT_TILES
        ) * 32
        bullets = (
            ("sniper", 80.0, False),
            ("Revolver_golden", 32.0, True),
        )

        for weapon_id, speed, golden in bullets:
            bullet = Bullet(weapon_id=weapon_id)
            bullet.launch(0, 0, 10_000, 0, speed=speed)
            bullet.life_time = float("inf")
            bullet.spawn_time = 100.0
            bullet.flight_start_time = 100.0
            bullet.aim_released = True
            max_speed = (
                speed * GOLDEN_BULLET_MAX_SPEED_MULTIPLIER
                if golden else speed
            )
            frame = 1
            while bullet.is_active:
                with patch(
                    "Bullet.time.monotonic",
                    return_value=100.0 + frame / FPS,
                ):
                    bullet.update()
                frame += 1

            self.assertLess(math.hypot(bullet.x, bullet.y), map_short_edge)
            self.assertLessEqual(
                math.hypot(bullet.x, bullet.y),
                BULLET_MAX_TRAVEL_DISTANCE + max_speed,
            )


if __name__ == "__main__":
    unittest.main()
