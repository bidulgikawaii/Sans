import socket
import threading
import pickle
import time
from Config import (
    DEFAULT_WEAPON_ID,
    NETWORK_BUFFER_SIZE,
    PLAYER_MAX_HP,
    SERVER_IP,
    SERVER_PORT,
    SERVER_SEED,
    STEALTH_DURATION_MS,
    HEADSHOT_DAMAGE_MULTIPLIER,
    MAP_HEIGHT_TILES,
    MAP_WIDTH_TILES,
    RUNE_ALERT_RADIUS,
    RUNE_ALERT_DURATION_MS,
    REVIVE_HP_RATIO,
)
from Weapon import WEAPONS
from Lobby import LobbyState
from Zone import MagneticZone
import random

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
bind_ip = SERVER_IP
for candidate_ip in (SERVER_IP, "127.0.0.1"):
    try:
        server.bind((candidate_ip, SERVER_PORT))
        bind_ip = candidate_ip
        break
    except OSError:
        continue
server.listen()
print(f"서버 시작: {bind_ip}:{SERVER_PORT}")

# 서버가 총괄하는 플레이어들의 실시간 딕셔너리
players = {}
player_lock = threading.Lock()
bullet_events = []
next_bullet_event_id = 1
destroyed_treasures = set()
destroyed_furniture = set()
rune_alerts = []
player_count = 0
next_player_id = 1
lobby = LobbyState()
magnetic_zone = MagneticZone(MAP_WIDTH_TILES, MAP_HEIGHT_TILES, 32)


def update_player_count(delta):
    global player_count
    with player_lock:
        player_count += delta
        return player_count

def get_next_player_id():
    global next_player_id
    with player_lock:
        player_id = next_player_id
        next_player_id += 1
        return player_id


def handle_client(conn, player_id):
    global next_bullet_event_id
    with player_lock:
        # 접속 전에 발생한 총알은 새 플레이어에게 전달하지 않습니다.
        last_sent_bullet_event_id = next_bullet_event_id - 1

    # 1. 접속한 클라이언트에게 고유 아이디 부여
    conn.send(pickle.dumps({"init_id": player_id, "seed": SERVER_SEED}))

    # 플레이어 초기값 세팅
    players[player_id] = {
        "posX": 0,
        "posY": 0,
        "angle": 0.0,
        "hp": PLAYER_MAX_HP,
        "weapon_id": DEFAULT_WEAPON_ID,
        "magazine_ammo": WEAPONS[DEFAULT_WEAPON_ID].magazine_size,
        "reserve_ammo": WEAPONS[DEFAULT_WEAPON_ID].reserve_ammo,
        "stealth": False,
        "in_bush": False,
        "stealth_token": 0,
        "stealth_until": 0.0,
        "wards": [],
        "revive_token": 0,
        "revive_armed": False,
        "rune_alerts": [],
        "stunned_until": 0.0,
        "zone_outside_since": None,
        "zone_damage_credit": 0.0,
        "zone_last_tick": time.monotonic(),
        "bullets": [],
    }

    try:
        while True:
            # 2. 클라이언트가 보낸 데이터(posX, posY, angle) 수신
            data = conn.recv(NETWORK_BUFFER_SIZE)
            if not data:
                break

            client_data = pickle.loads(data)

            if client_data.get("type") == "lobby_join":
                with player_lock:
                    accepted = lobby.join(
                        player_id,
                        client_data.get("mode"),
                        debug_enabled=bool(client_data.get("debug_enabled", False)),
                    )
                    lobby_status = lobby.status()
                    lobby_status["accepted"] = accepted
                    if not accepted:
                        lobby_status["message"] = "게임이 진행 중이라 참가할 수 없습니다."
                conn.sendall(pickle.dumps(lobby_status))
                continue

            if client_data.get("type") == "lobby_ready":
                with player_lock:
                    ready = bool(client_data.get("ready", False))
                    accepted = lobby.set_ready(player_id, ready)
                    lobby_status = lobby.status()
                    lobby_status["accepted"] = accepted
                    if not accepted:
                        lobby_status["message"] = "로비에 참여하지 않은 플레이어입니다."
                conn.sendall(pickle.dumps(lobby_status))
                continue

            for treasure in client_data.get("destroyed_treasures", []):
                if len(treasure) == 2:
                    destroyed_treasures.add((int(treasure[0]), int(treasure[1])))
            for furniture in client_data.get("destroyed_furniture", []):
                if len(furniture) == 2:
                    destroyed_furniture.add((int(furniture[0]), int(furniture[1])))

            # 3. 서버에 저장된 해당 유저 데이터 갱신
            players[player_id]["posX"] = client_data["posX"]
            players[player_id]["posY"] = client_data["posY"]
            players[player_id]["angle"] = client_data["angle"]
            weapon_id = client_data.get("weapon_id", DEFAULT_WEAPON_ID)
            players[player_id]["weapon_id"] = weapon_id if weapon_id in WEAPONS else DEFAULT_WEAPON_ID
            players[player_id]["magazine_ammo"] = max(
                0, client_data.get("magazine_ammo", players[player_id]["magazine_ammo"])
            )
            players[player_id]["reserve_ammo"] = max(
                0, client_data.get("reserve_ammo", players[player_id]["reserve_ammo"])
            )
            players[player_id]["in_bush"] = bool(client_data.get("in_bush", False))
            players[player_id]["wards"] = [
                (float(ward[0]), float(ward[1]))
                for ward in client_data.get("wards", [])
                if isinstance(ward, (list, tuple)) and len(ward) == 2
            ]
            players[player_id]["revive_armed"] = bool(
                client_data.get("revive_armed", False)
            )
            revive_token = int(client_data.get("revive_token", 0))
            if (
                client_data.get("revive_request", False)
                and revive_token != players[player_id]["revive_token"]
            ):
                players[player_id]["revive_token"] = revive_token
                players[player_id]["hp"] = max(1, round(PLAYER_MAX_HP * REVIVE_HP_RATIO))
                players[player_id]["revive_armed"] = False
            rune_ping = client_data.get("rune_ping")
            if isinstance(rune_ping, (list, tuple)) and len(rune_ping) == 2:
                rune_alerts.append((float(rune_ping[0]), float(rune_ping[1]), time.monotonic() + RUNE_ALERT_DURATION_MS / 1000))
            now_monotonic = time.monotonic()
            rune_alerts[:] = [alert for alert in rune_alerts if alert[2] > now_monotonic]
            stealth_token = int(client_data.get("stealth_token", 0))
            if stealth_token != players[player_id]["stealth_token"]:
                players[player_id]["stealth_token"] = stealth_token
                players[player_id]["stealth_until"] = time.monotonic() + STEALTH_DURATION_MS / 1000
            players[player_id]["stealth"] = (
                players[player_id]["in_bush"]
                or (
                    time.monotonic() < players[player_id]["stealth_until"]
                    and players[player_id]["stealth_token"] == stealth_token
                )
            )

            lobby_state = lobby.status()
            zone_elapsed_ms = (
                lobby_state.get("elapsed_ms", 0)
                if lobby.zone_enabled_for(player_id)
                else 0
            )
            zone_now = time.monotonic()
            player_center_x = players[player_id]["posX"] + 32
            player_center_y = players[player_id]["posY"] + 32
            if zone_elapsed_ms and not magnetic_zone.is_inside(
                player_center_x, player_center_y, zone_elapsed_ms
            ):
                if players[player_id]["zone_outside_since"] is None:
                    players[player_id]["zone_outside_since"] = zone_now
                outside_ms = (zone_now - players[player_id]["zone_outside_since"]) * 1000
                tick_seconds = max(0.0, zone_now - players[player_id]["zone_last_tick"])
                players[player_id]["zone_damage_credit"] += (
                    magnetic_zone.damage_per_second(outside_ms) * tick_seconds
                )
                damage = int(players[player_id]["zone_damage_credit"])
                if damage:
                    players[player_id]["hp"] = max(0, players[player_id]["hp"] - damage)
                    players[player_id]["zone_damage_credit"] -= damage
            else:
                players[player_id]["zone_outside_since"] = None
                players[player_id]["zone_damage_credit"] = 0.0
            players[player_id]["zone_last_tick"] = zone_now

            for hit_event in client_data.get("hit_events", []):
                target_id = int(hit_event.get("target_id", 0))
                target = players.get(target_id)
                if not target or target["hp"] <= 0:
                    continue
                damage = max(0, int(hit_event.get("damage", 0)))
                if hit_event.get("hit_part") == "head":
                    damage *= HEADSHOT_DAMAGE_MULTIPLIER
                target["hp"] = max(0, target["hp"] - damage)
                stun_ms = max(0, int(hit_event.get("stun_ms", 0)))
                if stun_ms:
                    target["stunned_until"] = max(
                        target.get("stunned_until", 0.0),
                        time.monotonic() + stun_ms / 1000,
                    )

            with player_lock:
                for bullet in client_data.get("bullets", []):
                    bullet_event = dict(bullet)
                    bullet_event["owner_id"] = player_id
                    bullet_event["event_id"] = next_bullet_event_id
                    next_bullet_event_id += 1
                    bullet_events.append(bullet_event)


            # 4. 현재 접속한 모든 유저들의 데이터를 통째로 패킹해서 응답
            with player_lock:
                active_ids = lobby.active_player_ids()
                active_players = {
                    active_id: players[active_id]
                    for active_id in active_ids
                    if active_id in players
                }
                alive_ids = [
                    active_id for active_id in active_ids
                    if active_id in players and players[active_id]["hp"] > 0
                ]
                revive_waiting_ids = [
                    active_id for active_id in active_ids
                    if active_id in players
                    and players[active_id]["hp"] <= 0
                    and players[active_id].get("revive_armed", False)
                ]
                lobby_mode = lobby.status()["mode"]
                winner_id = (
                    alive_ids[0]
                    if (
                        lobby.started
                        and lobby_mode == "normal"
                        and len(alive_ids) == 1
                        and not revive_waiting_ids
                    )
                    else None
                )
            snapshot = pickle.loads(pickle.dumps(active_players))
            pending_bullets = [
                bullet for bullet in bullet_events
                if bullet["event_id"] > last_sent_bullet_event_id
            ]
            if pending_bullets:
                last_sent_bullet_event_id = pending_bullets[-1]["event_id"]
            for snapshot_player_id, player in snapshot.items():
                player["bullets"] = list(pending_bullets)
                player["destroyed_treasures"] = list(destroyed_treasures)
                player["destroyed_furniture"] = list(destroyed_furniture)
                player["rune_alerts"] = [
                    (alert[0], alert[1], max(0, round((alert[2] - now_monotonic) * 1000)))
                    for alert in rune_alerts
                ]
                player["winner_id"] = (
                    winner_id
                    if winner_id is not None and int(snapshot_player_id) == int(winner_id)
                    else None
                )
                player["zone_elapsed_ms"] = lobby_state.get("elapsed_ms", 0)
                player["stun_ms_remaining"] = max(
                    0, round((player.get("stunned_until", 0.0) - time.monotonic()) * 1000)
                )
            conn.sendall(pickle.dumps(snapshot))
    except Exception as e:
        print(f"[네트워크 오류] 플레이어 {player_id}번: {e}")
    finally:
        print(f"[퇴장] 플레이어 {player_id}번 접속 종료")

        with player_lock:
            players.pop(player_id, None)
            lobby.leave(player_id)

        current_count = update_player_count(-1)
        print(f"[카운트] 현재 접속 인원: {current_count}")
        conn.close()


print("[서버 켜짐] 클라이언트 연결을 기다리는 중...")

while True:
    conn, addr = server.accept()
    player_id = get_next_player_id()
    current_count = update_player_count(1)
    print(f"[접속] 새로운 플레이어 (ID: {player_id})")
    print(f"[카운트] 현재 접속 인원: {current_count}")
    threading.Thread(target=handle_client, args=(conn, player_id), daemon=True).start()
