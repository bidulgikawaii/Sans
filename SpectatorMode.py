import pickle

import pygame


def poll_players(client, buffer_size):
    """관전 대상 플레이어 스냅샷을 한 번 요청합니다."""
    client.sendall(pickle.dumps({"type": "spectator_join"}))
    response = client.recv(buffer_size)
    return pickle.loads(response) if response else {}


def leave_spectator(client, buffer_size):
    """관전자 연결을 경기 조회 상태에서 해제합니다."""
    client.sendall(pickle.dumps({"type": "spectator_leave"}))
    response = client.recv(buffer_size)
    return pickle.loads(response) if response else {}


def draw_waiting(surface, font, screen_width, screen_height):
    surface.fill((10, 15, 24))
    waiting = font.render("진행 중인 게임이 없습니다", True, (230, 235, 245))
    surface.blit(waiting, waiting.get_rect(center=(screen_width // 2, screen_height // 2)))
    guide = font.render("ESC: 나가기", True, (180, 200, 220))
    surface.blit(guide, guide.get_rect(center=(screen_width // 2, screen_height // 2 + 55)))


def draw_world(
    surface,
    tile_generator,
    players,
    image,
    font,
    camera,
    zoom,
    screen_width,
    tracked_id=None,
    weapon_loader=None,
):
    camera_x, camera_y = camera
    tile_generator.draw(surface, camera_x, camera_y, zoom)
    title = font.render("관전모드  |  Q: 시점 변경  ESC: 나가기", True, (255, 235, 150))
    surface.blit(title, (30, 25))
    for player_id, player_info in players.items():
        screen_x = round((player_info.get("posX", 0) - camera_x) * zoom)
        screen_y = round((player_info.get("posY", 0) - camera_y) * zoom)
        player_image = image if zoom == 1.0 else pygame.transform.smoothscale(
            image,
            (max(1, round(image.get_width() * zoom)), max(1, round(image.get_height() * zoom))),
        )
        surface.blit(player_image, (screen_x, screen_y))
        if str(player_id) == str(tracked_id):
            pygame.draw.circle(
                surface,
                (255, 225, 100),
                (round(screen_x + image.get_width() * zoom / 2), round(screen_y + image.get_height() * zoom / 2)),
                max(22, round(image.get_width() * zoom * 0.7)),
                3,
            )
        if weapon_loader is not None:
            weapon_id = player_info.get("weapon_id", "pistol")
            weapon_image = (
                weapon_loader.GetBladeFrames()[0]
                if weapon_id == "knife" and weapon_loader.GetBladeFrames()
                else weapon_loader.GetWeaponImage(weapon_id)
            )
            weapon_image = pygame.transform.smoothscale(
                weapon_image,
                (
                    max(1, round(weapon_image.get_width() * zoom * 0.15)),
                    max(1, round(weapon_image.get_height() * zoom * 0.15)),
                ),
            )
            if weapon_id in ("pistol", "knife"):
                weapon_image = pygame.transform.flip(weapon_image, True, False)
            weapon_image = pygame.transform.rotate(weapon_image, -player_info.get("angle", 0))
            weapon_rect = weapon_image.get_rect(
                center=(
                    round(screen_x + image.get_width() * zoom / 2),
                    round(screen_y + image.get_height() * zoom / 2),
                )
            )
            surface.blit(weapon_image, weapon_rect)
        label = font.render(str(player_info.get("name", f"P{player_id}")), True, (255, 230, 160))
        surface.blit(label, label.get_rect(midbottom=(round(screen_x + image.get_width() * zoom / 2), round(screen_y - 5))))

    kill_events = []
    for player_info in players.values():
        kill_events.extend(player_info.get("kill_events", []))
    seen_events = set()
    for index, event in enumerate(sorted(kill_events, key=lambda item: item.get("event_id", 0), reverse=True)[:5]):
        event_id = event.get("event_id")
        if event_id in seen_events:
            continue
        seen_events.add(event_id)
        kill_text = font.render(
            f"{event.get('killer_name', '플레이어')}  >  {event.get('target_name', '플레이어')}",
            True,
            (255, 225, 150),
        )
        surface.blit(kill_text, (screen_width - 360, 95 + index * 26))
