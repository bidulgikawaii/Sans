"""Shared game font loading and caching."""

from functools import lru_cache
from pathlib import Path

import pygame


FONT_PATH = Path(__file__).resolve().parent / "Font" / "HeirofLightRegular.ttf"


@lru_cache(maxsize=32)
def get_game_font(size):
    return pygame.font.Font(str(FONT_PATH), max(1, int(size)))