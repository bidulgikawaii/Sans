import pickle

import pygame


def poll_players(client, buffer_size):
    """관전 대상 플레이어 스냅샷을 한 번 요청합니다."""
    client.sendall(pickle.dumps({"type": "spectator_join"}))
    response = client.recv(buffer_size)
    return pickle.loads(response) if response else {}


def draw_waiting(surface, font, screen_width, screen_height):
    surface.fill((10, 15, 24))
    waiting = font.render("진행 중인 게임이 없습니다", True, (230, 235, 245))
    surface.blit(waiting, waiting.get_rect(center=(screen_width // 2, screen_height // 2)))
    guide = font.render("ESC: 나가기", True, (180, 200, 220))
    surface.blit(guide, guide.get_rect(center=(screen_width // 2, screen_height // 2 + 55)))


def draw_world(surface, tile_generator, players, image, font, camera, zoom, screen_width):
    camera_x, camera_y = camera
    tile_generator.draw(surface, camera_x, camera_y, zoom)
    title = font.render("관전모드  |  ESC: 나가기", True, (255, 235, 150))
    surface.blit(title, (30, 25))
    for player_id, player_info in players.items():
        screen_x = round((player_info.get("posX", 0) - camera_x) * zoom)
        screen_y = round((player_info.get("posY", 0) - camera_y) * zoom)
        player_image = image if zoom == 1.0 else pygame.transform.smoothscale(
            image,
            (max(1, round(image.get_width() * zoom)), max(1, round(image.get_height() * zoom))),
        )
        surface.blit(player_image, (screen_x, screen_y))
        label = font.render(str(player_info.get("name", f"P{player_id}")), True, (255, 230, 160))
        surface.blit(label, label.get_rect(midbottom=(round(screen_x + image.get_width() * zoom / 2), round(screen_y - 5))))
