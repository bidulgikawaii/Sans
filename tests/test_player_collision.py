import unittest

import pygame

from PlayerClass import Player


class Wall:
    tile_size = 32

    def __init__(self, rect):
        self.rect = rect

    def check_collision(self, rect):
        return rect.colliderect(self.rect)


class PlayerCollisionTests(unittest.TestCase):
    def test_player_moves_out_of_wall_overlap(self):
        player = Player.__new__(Player)
        player.X = 95
        player.Y = 40
        player.rect = pygame.Rect(95, 40, 72, 72)
        player.tile_generator = Wall(pygame.Rect(100, 50, 32, 32))
        player._update_hitboxes()

        self.assertTrue(player._position_collides(player.X, player.Y))
        self.assertTrue(player.Move(1, 0))
        self.assertFalse(player._position_collides(player.X, player.Y))


if __name__ == "__main__":
    unittest.main()
