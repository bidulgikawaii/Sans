"""배트에 맞은 플레이어 스프라이트의 맵 밖 비행 연출."""

import math


def create_bat_launch(event, map_width, map_height, now):
    launch = event.get("bat_launch")
    if not isinstance(launch, dict):
        return None

    start_x = float(launch.get("x", 0))
    start_y = float(launch.get("y", 0))
    direction_x = float(launch.get("direction_x", 1))
    direction_y = float(launch.get("direction_y", 0))
    direction_length = math.hypot(direction_x, direction_y)
    if direction_length <= 0.001:
        direction_x, direction_y = 1.0, 0.0
    else:
        direction_x /= direction_length
        direction_y /= direction_length

    distances_to_edge = []
    if direction_x > 0:
        distances_to_edge.append((map_width - start_x) / direction_x)
    elif direction_x < 0:
        distances_to_edge.append(-start_x / direction_x)
    if direction_y > 0:
        distances_to_edge.append((map_height - start_y) / direction_y)
    elif direction_y < 0:
        distances_to_edge.append(-start_y / direction_y)
    distance_to_edge = min(value for value in distances_to_edge if value >= 0)
    distance = distance_to_edge + 240

    return {
        "x": start_x,
        "y": start_y,
        "direction_x": direction_x,
        "direction_y": direction_y,
        "distance": distance,
        "started_at": now,
        "duration": max(1200, min(2800, round(distance / 2.2))),
    }


def get_bat_launch_frame(launch, now):
    elapsed = max(0, now - launch["started_at"])
    progress = min(1.0, elapsed / launch["duration"])
    eased_progress = progress * progress * (3 - 2 * progress)
    arc_height = min(320, launch["distance"] * 0.16)
    center_x = launch["x"] + launch["direction_x"] * launch["distance"] * eased_progress
    center_y = (
        launch["y"]
        + launch["direction_y"] * launch["distance"] * eased_progress
        - math.sin(progress * math.pi) * arc_height
    )
    alpha = 255 if progress < 0.72 else round(255 * (1 - progress) / 0.28)
    rotation = math.degrees(math.atan2(launch["direction_y"], launch["direction_x"]))
    rotation += 900 * eased_progress
    return center_x, center_y, rotation, max(0, alpha), progress >= 1.0