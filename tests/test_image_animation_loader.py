import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from ImageLoad import Imageload
from GameRendering import tint_player_image


class ImageAnimationLoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        if pygame.display.get_surface() is None:
            pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_animation_frames_with_different_canvas_sizes_are_normalized(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            frame_directory = root / "frames"
            frame_directory.mkdir()
            for name, size in (
                ("frame_0000.png", (80, 60)),
                ("frame_0001.png", (24, 32)),
            ):
                image = pygame.Surface(size, pygame.SRCALPHA)
                pygame.draw.circle(
                    image,
                    (120, 220, 255, 255),
                    (size[0] // 2, size[1] // 2),
                    max(2, min(size) // 4),
                )
                pygame.image.save(image, str(frame_directory / name))

            loader = Imageload.__new__(Imageload)
            loader.root = root
            frames = loader._load_animation(
                "frame_", (64, 48), directory="frames"
            )

        self.assertEqual(len(frames), 2)
        self.assertTrue(all(frame.get_size() == (64, 48) for frame in frames))
        self.assertTrue(all(frame.get_bounding_rect().width > 0 for frame in frames))

    def test_missing_weapon_and_skill_images_fall_back_to_plasma_gun(self):
        loader = Imageload.__new__(Imageload)
        loader.PlasmaGun = pygame.Surface((128, 64))
        loader.PlasmaSkillIcon = pygame.Surface((32, 32))
        loader.ShotGun = [pygame.Surface((48, 48))]
        loader.HBlade = [pygame.Surface((48, 48))]
        loader.skill_icons = {}

        self.assertIs(loader.GetWeaponImage("missing_weapon"), loader.PlasmaGun)
        self.assertIs(loader.GetWeaponImage(None), loader.PlasmaGun)
        self.assertIs(loader.GetWeaponImage("knife"), loader.HBlade[0])
        self.assertIs(loader.GetWeaponImage("shotgun"), loader.ShotGun[0])
        self.assertEqual(loader.GetSkillIcon("missing_skill").get_size(), (32, 32))

    def test_animation_frames_are_ordered_by_numeric_suffix(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            frame_directory = root / "ion-cannon-frames"
            frame_directory.mkdir()
            for index in (2, 0, 1):
                image = pygame.Surface((4, 4), pygame.SRCALPHA)
                image.fill((index * 50, 0, 0, 255))
                pygame.image.save(
                    image,
                    str(frame_directory / f"ion-cannon_{index:04d}.png"),
                )

            loader = Imageload.__new__(Imageload)
            loader.root = root
            frames = loader._load_animation(
                "ion-cannon_", directory="ion-cannon-frames"
            )

        self.assertEqual(
            [frame.get_at((1, 1)).r for frame in frames],
            [0, 50, 100],
        )

    def test_team_tint_changes_player_hue_without_changing_alpha(self):
        image = pygame.Surface((1, 1), pygame.SRCALPHA)
        image.set_at((0, 0), (255, 255, 255, 128))

        tinted = tint_player_image(image, (255, 0, 0))

        self.assertEqual(tinted.get_at((0, 0)), pygame.Color(255, 0, 0, 128))
        self.assertEqual(image.get_at((0, 0)), pygame.Color(255, 255, 255, 128))


if __name__ == "__main__":
    unittest.main()
