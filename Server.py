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
)
from Weapon import WEAPONS
import random

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind((SERVER_IP, SERVER_PORT))
server.listen()

# 서버가 총괄하는 플레이어들의 실시간 딕셔너리
players = {}
player_lock = threading.Lock()
bullet_events = []
next_bullet_event_id = 1
destroyed_treasures = set()
player_count = 0
next_player_id = 1


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
        "bullets": [],
    }

    try:
        while True:
            # 2. 클라이언트가 보낸 데이터(posX, posY, angle) 수신
            data = conn.recv(NETWORK_BUFFER_SIZE)
            if not data:
                break

            client_data = pickle.loads(data)

            for treasure in client_data.get("destroyed_treasures", []):
                if len(treasure) == 2:
                    destroyed_treasures.add((int(treasure[0]), int(treasure[1])))

            # 3. 서버에 저장된 해당 유저 데이터 갱신
            players[player_id]["posX"] = client_data["posX"]
            players[player_id]["posY"] = client_data["posY"]
            players[player_id]["angle"] = client_data["angle"]
            players[player_id]["hp"] = max(0, client_data.get("hp", PLAYER_MAX_HP))
            weapon_id = client_data.get("weapon_id", DEFAULT_WEAPON_ID)
            players[player_id]["weapon_id"] = weapon_id if weapon_id in WEAPONS else DEFAULT_WEAPON_ID
            players[player_id]["magazine_ammo"] = max(
                0, client_data.get("magazine_ammo", players[player_id]["magazine_ammo"])
            )
            players[player_id]["reserve_ammo"] = max(
                0, client_data.get("reserve_ammo", players[player_id]["reserve_ammo"])
            )
            players[player_id]["in_bush"] = bool(client_data.get("in_bush", False))
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

            with player_lock:
                for bullet in client_data.get("bullets", []):
                    bullet_event = dict(bullet)
                    bullet_event["owner_id"] = player_id
                    bullet_event["event_id"] = next_bullet_event_id
                    next_bullet_event_id += 1
                    bullet_events.append(bullet_event)


            # 4. 현재 접속한 모든 유저들의 데이터를 통째로 패킹해서 응답
            snapshot = pickle.loads(pickle.dumps(players))
            pending_bullets = [
                bullet for bullet in bullet_events
                if bullet["event_id"] > last_sent_bullet_event_id
            ]
            if pending_bullets:
                last_sent_bullet_event_id = pending_bullets[-1]["event_id"]
            for player in snapshot.values():
                player["bullets"] = list(pending_bullets)
                player["destroyed_treasures"] = list(destroyed_treasures)
            conn.sendall(pickle.dumps(snapshot))
    except Exception as e:
        print(f"[네트워크 오류] 플레이어 {player_id}번: {e}")
    finally:
        print(f"[퇴장] 플레이어 {player_id}번 접속 종료")

        if player_id in players:
            del players[player_id]

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
