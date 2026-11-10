import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from ImageLoad import Imageload


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


if __name__ == "__main__":
    unittest.main()
