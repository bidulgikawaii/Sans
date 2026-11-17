"""Flagdown team base geometry and entry protection."""

import math

from Config import (
    FLAGDOWN_BASE_DEPTH_TILES,
    FLAGDOWN_BASE_END_Y_TILE,
    FLAGDOWN_BASE_START_Y_TILE,
    FLAGDOWN_MAP_WIDTH_TILES,
)


def flagdown_base_bounds(
    team_id,
    tile_size=32,
    map_width_tiles=FLAGDOWN_MAP_WIDTH_TILES,
):
    if team_id not in (0, 1):
        return None
    left_tile = (
        map_width_tiles - FLAGDOWN_BASE_DEPTH_TILES
        if team_id == 0
        else 0
    )
    return (
        left_tile * tile_size,
        FLAGDOWN_BASE_START_Y_TILE * tile_size,
        FLAGDOWN_BASE_DEPTH_TILES * tile_size,
        (FLAGDOWN_BASE_END_Y_TILE - FLAGDOWN_BASE_START_Y_TILE) * tile_size,
    )


def intersects_enemy_flagdown_base(
    team_id,
    x,
    y,
    width,
    height,
    tile_size=32,
    map_width_tiles=FLAGDOWN_MAP_WIDTH_TILES,
):
    if team_id not in (0, 1):
        return False
    try:
        values = tuple(float(value) for value in (x, y, width, height))
    except (TypeError, ValueError, OverflowError):
        return True
    if not all(math.isfinite(value) for value in values):
        return True
    x, y, width, height = values
    if width <= 0 or height <= 0:
        return True
    enemy_bounds = flagdown_base_bounds(
        1 - team_id, tile_size, map_width_tiles
    )
    base_x, base_y, base_width, base_height = enemy_bounds
    return (
        x < base_x + base_width
        and x + width > base_x
        and y < base_y + base_height
        and y + height > base_y
    )
