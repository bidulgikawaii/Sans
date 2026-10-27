import copy
import socket
import threading
import pickle
import random
import time
import uuid
from Config import (
    DEFAULT_WEAPON_ID,
    DEATHMATCH_DURATION_MS,
    DEATHMATCH_RESPAWN_MS,
    BUSH_LEAF_INTERVAL_MS,
    GAME_MODE_DEBUG,
    GAME_MODE_DEATHMATCH,
    GAME_MODE_NORMAL,
    NETWORK_BUFFER_SIZE,
    PLAYER_MAX_HP,
    SERVER_IP,
    SERVER_PORT,
    SERVER_SEED,
    STEALTH_DURATION_MS,
    HEADSHOT_DAMAGE_MULTIPLIER,
    MAP_HEIGHT_TILES,
    MAP_WIDTH_TILES,
    MAX_PLAYERS,
    RUNE_ALERT_DURATION_MS,
    REVIVE_HP_RATIO,
)
from Weapon import WEAPONS
from Lobby import LobbyState
from Zone import MagneticZone
from GameModes import get_game_mode, get_game_modes, is_game_mode_registered
from NetworkProtocol import FramedSocket

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
# 클라이언트 이벤트를 검증해 HP와 승리 상태를 갱신하고, 결과를 스냅샷으로 돌려줍니다.
players = {}
player_lock = threading.Lock()


def new_match_events():
    return {
        "bullet_events": [],
        "next_bullet_event_id": 1,
        "verified_bullet_events": {},
        "destroyed_treasures": set(),
        "destroyed_furniture": set(),
        "rune_alerts": [],
        "kill_events": [],
        "next_kill_event_id": 1,
        "kill_scores": {},
        "damage_events": [],
        "next_damage_event_id": 1,
        "revive_events": [],
        "next_revive_event_id": 1,
        "supply_drops": {},
        "next_supply_drop_id": 1,
        "supply_collection_events": [],
        "next_supply_collection_id": 1,
        "bush_leaf_events": [],
        "next_bush_leaf_event_id": 1,
    }


def append_kill_event(events, killer_id, target_id, killer_name, target_name, weapon_id, cause):
    events["kill_events"].append({
        "event_id": events["next_kill_event_id"],
        "killer_id": killer_id,
        "target_id": target_id,
        "killer_name": killer_name,
        "target_name": target_name,
        "weapon_id": weapon_id,
        "cause": cause,
    })
    events["next_kill_event_id"] += 1


def consume_deathmatch_revive(events, player_id, player):
    if player["hp"] > 0 or not player.get("revive_armed", False):
        return False
    player["hp"] = 1
    player["revive_armed"] = False
    events["revive_events"].append({
        "event_id": events["next_revive_event_id"],
        "player_id": player_id,
        "x": player.get("posX", 0),
        "y": player.get("posY", 0),
    })
    events["next_revive_event_id"] += 1
    events["revive_events"] = events["revive_events"][-32:]
    return True


match_events = {mode.mode_id: new_match_events() for mode in get_game_modes()}
completed_match_winner_ids = {}
result_pending_player_ids = {}
cancelled_match_notices = {}
player_count = 0
lobby = LobbyState()
magnetic_zone = MagneticZone(MAP_WIDTH_TILES, MAP_HEIGHT_TILES, 32)


def reset_match_events(mode):
    match_events[mode] = new_match_events()


def update_player_count(delta):
    global player_count
    with player_lock:
        player_count += delta
        return player_count

def generate_player_id():
    return str(uuid.uuid4())


def validated_spawn_tiles(raw_tiles):
    if not isinstance(raw_tiles, (list, tuple)):
        return []
    spawn_tiles = []
    for raw_tile in raw_tiles:
        if not isinstance(raw_tile, (list, tuple)) or len(raw_tile) != 2:
            continue
        x, y = raw_tile
        if (
            not isinstance(x, int)
            or isinstance(x, bool)
            or not isinstance(y, int)
            or isinstance(y, bool)
            or not (0 <= x < MAP_WIDTH_TILES - 2)
            or not (0 <= y < MAP_HEIGHT_TILES - 2)
        ):
            continue
        if (x, y) not in spawn_tiles:
            spawn_tiles.append((x, y))
        if len(spawn_tiles) >= MAX_PLAYERS:
            break
    return spawn_tiles


def handle_client(conn, player_id):
    conn = FramedSocket(conn)
    with player_lock:
        # 접속 전에 발생한 총알은 새 플레이어에게 전달하지 않습니다.
        last_sent_bullet_event_ids = {
            mode: events["next_bullet_event_id"] - 1
            for mode, events in match_events.items()
        }

    # 1. 접속한 클라이언트에게 고유 아이디 부여
    conn.send(pickle.dumps({"init_id": player_id, "seed": SERVER_SEED}))

    # 플레이어 초기값 세팅
    players[player_id] = {
        "posX": 0,
        "posY": 0,
        "angle": 0.0,
        "hp": PLAYER_MAX_HP,
        "name": f"유저_{player_id}",
        "weapon_id": DEFAULT_WEAPON_ID,
        "weapon_name": WEAPONS[DEFAULT_WEAPON_ID].name,
        "magazine_ammo": WEAPONS[DEFAULT_WEAPON_ID].magazine_size,
        "reserve_ammo": WEAPONS[DEFAULT_WEAPON_ID].reserve_ammo,
        "stealth": False,
        "in_bush": False,
        "last_bush_leaf_token": 0,
        "last_bush_leaf_at": 0.0,
        "stealth_token": 0,
        "stealth_until": 0.0,
        "wards": [],
        "revive_token": 0,
        "revive_accepted_token": 0,
        "revive_armed": False,
        "deathmatch_revive_used": False,
        "heal_token": 0,
        "shield_active": False,
        "rune_alerts": [],
        "stunned_until": 0.0,
        "zone_outside_since": None,
        "zone_damage_credit": 0.0,
        "zone_last_tick": time.monotonic(),
        "bullets": [],
        "deathmatch_respawn_at": None,
        "spawn_index": None,
        "spawn_tiles": [],
        "kill_count": 0,
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
                    cancelled_mode = cancelled_match_notices.pop(player_id, None)
                    if cancelled_mode is not None:
                        conn.sendall(pickle.dumps({
                            "type": "match_cancelled",
                            "mode": cancelled_mode,
                        }))
                        continue
                    requested_mode = client_data.get("mode")
                    if client_data.get("debug_enabled", False):
                        requested_mode = GAME_MODE_DEBUG
                    if not is_game_mode_registered(requested_mode):
                        requested_mode = GAME_MODE_NORMAL
                    previous_mode = lobby.mode_for(player_id)
                    accepted = lobby.join(
                        player_id,
                        requested_mode,
                        debug_enabled=bool(client_data.get("debug_enabled", False)),
                    )
                    if accepted:
                        last_sent_bullet_event_ids[requested_mode] = (
                            match_events[requested_mode]["next_bullet_event_id"] - 1
                        )
                        requested_name = str(client_data.get("name", "")).strip()
                        player = players[player_id]
                        player.update({
                            "name": (requested_name or f"유저_{player_id}")[:16],
                            "hp": PLAYER_MAX_HP,
                            "weapon_id": DEFAULT_WEAPON_ID,
                            "weapon_name": WEAPONS[DEFAULT_WEAPON_ID].name,
                            "magazine_ammo": WEAPONS[DEFAULT_WEAPON_ID].magazine_size,
                            "reserve_ammo": WEAPONS[DEFAULT_WEAPON_ID].reserve_ammo,
                            "stealth": False,
                            "in_bush": False,
                            "last_bush_leaf_token": 0,
                            "last_bush_leaf_at": 0.0,
                            "stealth_token": 0,
                            "stealth_until": 0.0,
                            "wards": [],
                            "revive_token": 0,
                            "revive_accepted_token": 0,
                            "revive_armed": False,
                            "deathmatch_revive_used": False,
                            "heal_token": 0,
                            "shield_active": False,
                            "rune_alerts": [],
                            "stunned_until": 0.0,
                            "zone_outside_since": None,
                            "zone_damage_credit": 0.0,
                            "zone_last_tick": time.monotonic(),
                            "bullets": [],
                            "deathmatch_respawn_at": None,
                            "kill_count": 0,
                        })
                        if requested_mode == GAME_MODE_DEATHMATCH:
                            spawn_candidates = validated_spawn_tiles(
                                client_data.get("spawn_tiles")
                            )
                            if not spawn_candidates:
                                accepted = False
                                lobby.leave(player_id)
                            else:
                                if previous_mode != GAME_MODE_DEATHMATCH:
                                    player["spawn_index"] = None
                                player["spawn_tiles"] = spawn_candidates
                                occupied_indices = {
                                    players[active_id].get("spawn_index")
                                    for active_id in lobby.active_player_ids(requested_mode)
                                    if active_id != player_id and active_id in players
                                }
                                spawn_index = player.get("spawn_index")
                                if (
                                    spawn_index is None
                                    or spawn_index >= len(spawn_candidates)
                                    or spawn_index in occupied_indices
                                ):
                                    available_indices = [
                                        index for index in range(len(spawn_candidates))
                                        if index not in occupied_indices
                                    ]
                                    if not available_indices:
                                        accepted = False
                                        lobby.leave(player_id)
                                    else:
                                        player["spawn_index"] = random.choice(available_indices)
                    lobby_status = lobby.status(player_id, mode=requested_mode)
                    lobby_status["accepted"] = accepted
                    if accepted:
                        if requested_mode == GAME_MODE_DEATHMATCH:
                            lobby_status["spawn_index"] = players[player_id]["spawn_index"]
                        else:
                            lobby_status["spawn_index"] = sorted(
                                lobby.active_player_ids(requested_mode)
                            ).index(player_id)
                    else:
                        lobby_status["message"] = (
                            "게임이 진행 중이라 참가할 수 없습니다."
                            if lobby.started[requested_mode]
                            or lobby.start_at[requested_mode] is not None
                            else (
                                "안전한 스폰 위치를 확보하지 못했습니다."
                                if requested_mode == GAME_MODE_DEATHMATCH
                                else f"로비가 가득 찼습니다. 최대 {MAX_PLAYERS}명까지 참가할 수 있습니다."
                            )
                        )
                conn.sendall(pickle.dumps(lobby_status))
                continue

            if client_data.get("type") == "lobby_leave":
                with player_lock:
                    mode = lobby.mode_for(player_id)
                    if (
                        mode is not None
                        and lobby.started[mode]
                        and player_id in lobby.match_player_ids[mode]
                        and mode != GAME_MODE_DEBUG
                    ):
                        if mode in completed_match_winner_ids:
                            lobby.leave(player_id)
                            pending_ids = result_pending_player_ids.get(mode)
                            if pending_ids is not None:
                                pending_ids.discard(player_id)
                                if not pending_ids:
                                    lobby.finish_match(mode)
                                    completed_match_winner_ids.pop(mode, None)
                                    result_pending_player_ids.pop(mode, None)
                                    reset_match_events(mode)
                            response = {"type": "match_result_complete", "mode": mode}
                        else:
                            players[player_id]["hp"] = 0
                            players[player_id]["revive_armed"] = False
                            players[player_id]["deathmatch_respawn_at"] = None
                            lobby.leave(player_id)
                            response = {"type": "match_defeat", "mode": mode}
                    else:
                        cancelled_ids = lobby.cancel(mode) if mode is not None else set()
                        for cancelled_id in cancelled_ids:
                            if cancelled_id != player_id:
                                cancelled_match_notices[cancelled_id] = mode
                        if mode is not None:
                            completed_match_winner_ids.pop(mode, None)
                            result_pending_player_ids.pop(mode, None)
                            reset_match_events(mode)
                        for pending_mode, pending_ids in tuple(result_pending_player_ids.items()):
                            pending_ids.discard(player_id)
                            if not pending_ids and pending_mode in completed_match_winner_ids:
                                lobby.finish_match(pending_mode)
                                completed_match_winner_ids.pop(pending_mode, None)
                                result_pending_player_ids.pop(pending_mode, None)
                                reset_match_events(pending_mode)
                        response = (
                            {"type": "match_cancelled", "mode": mode}
                            if mode is not None
                            else lobby.status(player_id)
                        )
                conn.sendall(pickle.dumps(response))
                continue

            if client_data.get("type") == "lobby_ready":
                with player_lock:
                    ready = bool(client_data.get("ready", False))
                    accepted = lobby.set_ready(player_id, ready)
                    lobby_status = lobby.status(player_id)
                    lobby_status["accepted"] = accepted
                    if not accepted:
                        lobby_status["message"] = "로비에 참여하지 않은 플레이어입니다."
                conn.sendall(pickle.dumps(lobby_status))
                continue

            with player_lock:
                mode = lobby.mode_for(player_id)
                if mode is None:
                    cancelled_mode = cancelled_match_notices.pop(player_id, None)
                    conn.sendall(pickle.dumps(
                        {"type": "match_cancelled", "mode": cancelled_mode}
                        if cancelled_mode is not None
                        else {}
                    ))
                    continue
                events = match_events[mode]

            with player_lock:
                now_monotonic = time.monotonic()
                events["supply_drops"] = {
                    drop_id: drop
                    for drop_id, drop in events["supply_drops"].items()
                    if drop["expires_at"] > now_monotonic
                }
                spawn_requests = client_data.get("supply_spawn_requests", [])
                if isinstance(spawn_requests, list):
                    for request in spawn_requests:
                        if not isinstance(request, dict):
                            continue
                        drop_type = request.get("type")
                        if drop_type not in (
                            "heal", "skill", "special_weapon",
                            "flare_ammo", "flare_skill",
                        ):
                            continue
                        try:
                            drop_x = float(request["x"])
                            drop_y = float(request["y"])
                            warning_ms = int(request.get("warning_ms", 2200))
                            lifetime_ms = int(request.get("lifetime_ms", 30_000))
                        except (KeyError, TypeError, ValueError):
                            continue
                        if not (0 <= drop_x < MAP_WIDTH_TILES * 32 and 0 <= drop_y < MAP_HEIGHT_TILES * 32):
                            continue
                        if len(events["supply_drops"]) >= 64:
                            continue
                        if drop_type in ("heal", "skill", "special_weapon"):
                            active_ids = sorted(lobby.active_player_ids(mode))
                            if not active_ids or player_id != active_ids[0]:
                                continue
                        drop_id = events["next_supply_drop_id"]
                        events["next_supply_drop_id"] += 1
                        warning_ms = max(0, min(10_000, warning_ms))
                        lifetime_ms = max(warning_ms + 1000, min(120_000, lifetime_ms))
                        events["supply_drops"][drop_id] = {
                            "id": drop_id,
                            "x": drop_x,
                            "y": drop_y,
                            "type": drop_type,
                            "warning_duration_ms": warning_ms,
                            "warning_until": now_monotonic + warning_ms / 1000,
                            "expires_at": now_monotonic + lifetime_ms / 1000,
                        }
                collect_ids = client_data.get("supply_collect_ids", [])
                if isinstance(collect_ids, list):
                    for requested_drop_id in collect_ids:
                        try:
                            drop_id = int(requested_drop_id)
                            player_center_x = float(client_data["posX"]) + 36
                            player_center_y = float(client_data["posY"]) + 36
                        except (KeyError, TypeError, ValueError):
                            continue
                        drop = events["supply_drops"].get(drop_id)
                        if drop is None or drop["warning_until"] > now_monotonic:
                            continue
                        if (
                            abs(player_center_x - drop["x"]) > 36 + 18
                            or abs(player_center_y - drop["y"]) > 36 + 18
                        ):
                            continue
                        events["supply_collection_events"].append({
                            "event_id": events["next_supply_collection_id"],
                            "drop_id": drop_id,
                            "player_id": player_id,
                            "type": drop["type"],
                        })
                        events["next_supply_collection_id"] += 1
                        events["supply_drops"].pop(drop_id, None)
                events["supply_collection_events"][:] = events["supply_collection_events"][-64:]

            for treasure in client_data.get("destroyed_treasures", []):
                if len(treasure) == 2:
                    events["destroyed_treasures"].add((int(treasure[0]), int(treasure[1])))
            for furniture in client_data.get("destroyed_furniture", []):
                if len(furniture) == 2:
                    events["destroyed_furniture"].add((int(furniture[0]), int(furniture[1])))

            # 3. 서버에 저장된 해당 유저 데이터 갱신
            if mode != GAME_MODE_DEATHMATCH or players[player_id]["hp"] > 0:
                players[player_id]["posX"] = client_data["posX"]
                players[player_id]["posY"] = client_data["posY"]
            players[player_id]["angle"] = client_data["angle"]
            weapon_id = client_data.get("weapon_id", DEFAULT_WEAPON_ID)
            if weapon_id not in WEAPONS:
                weapon_id = DEFAULT_WEAPON_ID
            players[player_id]["weapon_id"] = weapon_id
            players[player_id]["weapon_name"] = WEAPONS[weapon_id].name
            players[player_id]["magazine_ammo"] = max(
                0, client_data.get("magazine_ammo", players[player_id]["magazine_ammo"])
            )
            players[player_id]["reserve_ammo"] = max(
                0, client_data.get("reserve_ammo", players[player_id]["reserve_ammo"])
            )
            try:
                reported_kill_count = max(0, int(client_data.get("kill_count", 0)))
            except (TypeError, ValueError):
                reported_kill_count = 0
            verified_kill_count = events["kill_scores"].get(player_id, 0)
            players[player_id]["kill_count"] = min(reported_kill_count, verified_kill_count)
            players[player_id]["in_bush"] = bool(client_data.get("in_bush", False))
            if players[player_id]["in_bush"]:
                leaf_requests = client_data.get("bush_leaf_requests", [])
                if isinstance(leaf_requests, list):
                    for request in leaf_requests[:4]:
                        if not isinstance(request, dict):
                            continue
                        try:
                            leaf_token = int(request.get("token", 0))
                        except (TypeError, ValueError):
                            continue
                        if (
                            leaf_token <= players[player_id]["last_bush_leaf_token"]
                            or now_monotonic - players[player_id]["last_bush_leaf_at"]
                            < BUSH_LEAF_INTERVAL_MS / 1000
                        ):
                            continue
                        try:
                            player_x = float(client_data["posX"]) + 36
                            player_y = float(client_data["posY"]) + 60
                        except (KeyError, TypeError, ValueError):
                            continue
                        if not (
                            0 <= player_x < MAP_WIDTH_TILES * 32
                            and 0 <= player_y < MAP_HEIGHT_TILES * 32
                        ):
                            continue
                        events["bush_leaf_events"].append({
                            "event_id": events["next_bush_leaf_event_id"],
                            "player_id": player_id,
                            "x": player_x,
                            "y": player_y,
                            "seed": random.getrandbits(32),
                        })
                        events["next_bush_leaf_event_id"] += 1
                        players[player_id]["last_bush_leaf_token"] = leaf_token
                        players[player_id]["last_bush_leaf_at"] = now_monotonic
                events["bush_leaf_events"][:] = events["bush_leaf_events"][-64:]
            players[player_id]["wards"] = [
                (float(ward[0]), float(ward[1]))
                for ward in client_data.get("wards", [])
                if isinstance(ward, (list, tuple)) and len(ward) == 2
            ]
            if mode != GAME_MODE_DEATHMATCH:
                players[player_id]["revive_armed"] = bool(
                    client_data.get("revive_armed", False)
                )
            players[player_id]["shield_active"] = bool(client_data.get("shield_active", False))
            heal_token = int(client_data.get("heal_token", 0))
            if heal_token != players[player_id]["heal_token"]:
                players[player_id]["heal_token"] = heal_token
                heal_amount = max(0, int(client_data.get("heal_amount", 0)))
                players[player_id]["hp"] = min(
                    PLAYER_MAX_HP,
                    players[player_id]["hp"] + heal_amount,
                )
            revive_token = int(client_data.get("revive_token", 0))
            if (
                client_data.get("revive_request", False)
                and revive_token != players[player_id]["revive_token"]
            ):
                players[player_id]["revive_token"] = revive_token
                if mode == GAME_MODE_DEATHMATCH:
                    if not players[player_id]["deathmatch_revive_used"]:
                        players[player_id]["hp"] = PLAYER_MAX_HP
                        players[player_id]["revive_armed"] = True
                        players[player_id]["deathmatch_revive_used"] = True
                        players[player_id]["revive_accepted_token"] = revive_token
                else:
                    players[player_id]["hp"] = max(1, round(PLAYER_MAX_HP * REVIVE_HP_RATIO))
                    players[player_id]["revive_armed"] = False
            rune_ping = client_data.get("rune_ping")
            if isinstance(rune_ping, (list, tuple)) and len(rune_ping) == 2:
                events["rune_alerts"].append((float(rune_ping[0]), float(rune_ping[1]), time.monotonic() + RUNE_ALERT_DURATION_MS / 1000))
            now_monotonic = time.monotonic()
            events["rune_alerts"][:] = [
                alert for alert in events["rune_alerts"] if alert[2] > now_monotonic
            ]
            stealth_token = int(client_data.get("stealth_token", 0))
            if stealth_token != players[player_id]["stealth_token"]:
                players[player_id]["stealth_token"] = stealth_token
                players[player_id]["stealth_until"] = (
                    time.monotonic() + STEALTH_DURATION_MS / 1000
                    if client_data.get("stealth", False)
                    else 0.0
                )
            elif not client_data.get("stealth", False):
                players[player_id]["stealth_until"] = 0.0
            # stealth는 스킬 은신만 나타내며, 부쉬 은폐는 in_bush로 별도 전달합니다.
            players[player_id]["stealth"] = (
                bool(client_data.get("stealth", False))
                and time.monotonic() < players[player_id]["stealth_until"]
                and players[player_id]["stealth_token"] == stealth_token
            )

            lobby_state = lobby.status(player_id)
            zone_elapsed_ms = (
                lobby_state.get("elapsed_ms", 0)
                if lobby.zone_enabled_for(player_id)
                else 0
            )
            zone_now = time.monotonic()
            player_center_x = players[player_id]["posX"] + 36
            player_center_y = players[player_id]["posY"] + 36
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
                    previous_hp = players[player_id]["hp"]
                    players[player_id]["hp"] = max(0, players[player_id]["hp"] - damage)
                    players[player_id]["zone_damage_credit"] -= damage
                    if mode == GAME_MODE_DEATHMATCH:
                        consume_deathmatch_revive(
                            events, player_id, players[player_id]
                        )
                    if (
                        previous_hp > 0
                        and players[player_id]["hp"] <= 0
                        and not players[player_id].get("revive_armed", False)
                    ):
                        append_kill_event(
                            events,
                            None,
                            player_id,
                            "자기장",
                            players[player_id].get("name", "플레이어"),
                            None,
                            "magnetic_zone",
                        )
            else:
                players[player_id]["zone_outside_since"] = None
                players[player_id]["zone_damage_credit"] = 0.0
            players[player_id]["zone_last_tick"] = zone_now

            for hit_event in client_data.get("hit_events", []):
                if mode == GAME_MODE_DEATHMATCH and players[player_id]["hp"] <= 0:
                    break
                target_id = hit_event.get("target_id")
                if not isinstance(target_id, str) or target_id not in lobby.visible_player_ids(player_id):
                    continue
                target = players.get(target_id)
                if not target or target["hp"] <= 0:
                    continue
                attacker_id = hit_event.get("attacker_id", player_id)
                if (
                    not isinstance(attacker_id, str)
                    or attacker_id not in lobby.visible_player_ids(player_id)
                ):
                    continue
                if attacker_id != player_id:
                    try:
                        source_bullet_event_id = int(
                            hit_event.get("source_bullet_event_id")
                        )
                    except (TypeError, ValueError):
                        continue
                    source_bullet = events["verified_bullet_events"].get(
                        source_bullet_event_id
                    )
                    if (
                        source_bullet is None
                        or source_bullet["owner_id"] != attacker_id
                        or now_monotonic - source_bullet["created_at"] > 5000
                    ):
                        continue
                if target.get("shield_active", False):
                    continue
                damage = max(0, int(hit_event.get("damage", 0)))
                if hit_event.get("hit_part") == "head":
                    damage *= HEADSHOT_DAMAGE_MULTIPLIER
                stun_ms = max(0, int(hit_event.get("stun_ms", 0)))
                previous_hp = target["hp"]
                damage = min(damage, previous_hp)
                target["hp"] = previous_hp - damage
                if mode == GAME_MODE_DEATHMATCH and consume_deathmatch_revive(
                    events, target_id, target
                ):
                    damage = previous_hp - target["hp"]
                events["damage_events"].append({
                    "event_id": events["next_damage_event_id"],
                    "attacker_id": attacker_id,
                    "target_id": target_id,
                    "damage": damage,
                    "hit_part": hit_event.get("hit_part", "body"),
                    "stun_ms": stun_ms,
                })
                events["next_damage_event_id"] += 1
                if (
                    previous_hp > 0
                    and target["hp"] <= 0
                    and (
                        mode == GAME_MODE_DEATHMATCH
                        or not target.get("revive_armed", False)
                    )
                ):
                    if mode == GAME_MODE_DEATHMATCH:
                        target["revive_armed"] = False
                        target["deathmatch_respawn_at"] = (
                            time.monotonic() + DEATHMATCH_RESPAWN_MS / 1000
                        )
                        if attacker_id != target_id:
                            with player_lock:
                                events["kill_scores"][attacker_id] = (
                                    events["kill_scores"].get(attacker_id, 0) + 1
                                )
                    append_kill_event(
                        events,
                        attacker_id,
                        target_id,
                        players[attacker_id].get("name", "플레이어"),
                        target.get("name", "플레이어"),
                        (
                            source_bullet["weapon_id"]
                            if attacker_id != player_id
                            else (
                                hit_event.get("weapon_id")
                                if isinstance(hit_event.get("weapon_id"), str)
                                and hit_event.get("weapon_id") in WEAPONS
                                else players[attacker_id].get("weapon_id", DEFAULT_WEAPON_ID)
                            )
                        ),
                        "self_inflicted" if attacker_id == target_id else "player",
                    )
                if stun_ms:
                    target["stunned_until"] = max(
                        target.get("stunned_until", 0.0),
                        time.monotonic() + stun_ms / 1000,
                    )

            with player_lock:
                for bullet in (
                    client_data.get("bullets", [])
                    if players[player_id]["hp"] > 0
                    else ()
                ):
                    bullet_event = dict(bullet)
                    bullet_event["owner_id"] = player_id
                    bullet_event["event_id"] = events["next_bullet_event_id"]
                    bullet_event["created_at"] = now_monotonic
                    if (
                        not isinstance(bullet_event.get("weapon_id"), str)
                        or bullet_event["weapon_id"] not in WEAPONS
                    ):
                        bullet_event["weapon_id"] = players[player_id].get(
                            "weapon_id", DEFAULT_WEAPON_ID
                        )
                    events["verified_bullet_events"][bullet_event["event_id"]] = {
                        "owner_id": player_id,
                        "weapon_id": bullet_event["weapon_id"],
                        "created_at": now_monotonic,
                    }
                    events["next_bullet_event_id"] += 1
                    events["bullet_events"].append(bullet_event)
                events["verified_bullet_events"] = {
                    event_id: bullet_info
                    for event_id, bullet_info
                    in events["verified_bullet_events"].items()
                    if now_monotonic - bullet_info["created_at"] <= 5000
                }

            # 4. 현재 접속한 모든 유저들의 데이터를 통째로 패킹해서 응답
            with player_lock:
                now_monotonic = time.monotonic()
                if mode == GAME_MODE_DEATHMATCH:
                    for respawn_id in lobby.match_player_ids[mode]:
                        respawning_player = players.get(respawn_id)
                        respawn_at = (
                            respawning_player.get("deathmatch_respawn_at")
                            if respawning_player else None
                        )
                        if (
                            respawning_player
                            and respawning_player["hp"] <= 0
                            and respawn_at is not None
                            and now_monotonic >= respawn_at
                        ):
                            available_spawns = []
                            for spawn_x, spawn_y in respawning_player.get("spawn_tiles", ()):
                                overlaps_player = False
                                for active_id in lobby.match_player_ids[mode]:
                                    if active_id == respawn_id:
                                        continue
                                    other_player = players.get(active_id)
                                    if not other_player or other_player["hp"] <= 0:
                                        continue
                                    other_x = int(other_player["posX"] // 32)
                                    other_y = int(other_player["posY"] // 32)
                                    if (
                                        spawn_x < other_x + 3
                                        and spawn_x + 3 > other_x
                                        and spawn_y < other_y + 3
                                        and spawn_y + 3 > other_y
                                    ):
                                        overlaps_player = True
                                        break
                                if not overlaps_player:
                                    available_spawns.append((spawn_x, spawn_y))
                            if available_spawns:
                                spawn_x, spawn_y = random.choice(available_spawns)
                                respawning_player["posX"] = spawn_x * 32
                                respawning_player["posY"] = spawn_y * 32
                                respawning_player["magazine_ammo"] = WEAPONS[
                                    respawning_player["weapon_id"]
                                ].magazine_size
                                respawning_player["hp"] = PLAYER_MAX_HP
                                respawning_player["deathmatch_respawn_at"] = None

                active_ids = lobby.visible_player_ids(player_id)
                active_players = {
                    active_id: players[active_id]
                    for active_id in active_ids
                    if active_id in players
                }
                match_player_ids = lobby.match_player_ids[mode]
                alive_ids = [
                    active_id for active_id in match_player_ids
                    if active_id in players and players[active_id]["hp"] > 0
                ]
                revive_waiting_ids = [
                    active_id for active_id in match_player_ids
                    if active_id in players
                    and players[active_id]["hp"] <= 0
                    and players[active_id].get("revive_armed", False)
                ]
                winner_ids = completed_match_winner_ids.get(mode)
                if (
                    winner_ids is None
                    and mode == GAME_MODE_DEATHMATCH
                    and lobby.started[mode]
                    and lobby.status(player_id, mode).get("elapsed_ms", 0)
                    >= DEATHMATCH_DURATION_MS
                ):
                    scores = {
                        match_id: events["kill_scores"].get(match_id, 0)
                        for match_id in match_player_ids
                    }
                    highest_score = max(scores.values(), default=0)
                    winner_ids = [
                        match_id for match_id, score in scores.items()
                        if score == highest_score
                    ]
                    completed_match_winner_ids[mode] = winner_ids
                    result_pending_player_ids[mode] = (
                        set(match_player_ids)
                        & lobby.active_player_ids(mode)
                        & players.keys()
                    )
                active_match_player_ids = (
                    set(match_player_ids)
                    & lobby.active_player_ids(mode)
                    & players.keys()
                )
                if (
                    winner_ids is None
                    and mode != GAME_MODE_DEBUG
                    and lobby.started[mode]
                    and len(match_player_ids) >= get_game_mode(mode).min_players
                    and len(active_match_player_ids) == 1
                ):
                    winner_ids = [next(iter(active_match_player_ids))]
                    completed_match_winner_ids[mode] = winner_ids
                    result_pending_player_ids[mode] = set(active_match_player_ids)
                if winner_ids is None and get_game_mode(mode).elimination and (
                    lobby.started[mode]
                        and len(match_player_ids) >= get_game_mode(mode).min_players
                        and len(alive_ids) == 1
                        and not revive_waiting_ids
                ):
                    winner_ids = [alive_ids[0]]
                    completed_match_winner_ids[mode] = winner_ids
                    result_pending_player_ids[mode] = (
                        set(match_player_ids)
                        & lobby.active_player_ids(mode)
                        & players.keys()
                    )
            # 네트워크 직렬화 전 복사본을 만들되, pickle 왕복은 피합니다.
            snapshot = copy.deepcopy(active_players)
            with player_lock:
                score_snapshot = {
                    match_id: events["kill_scores"].get(match_id, 0)
                    for match_id in match_player_ids
                }
            pending_bullets = [
                bullet for bullet in events["bullet_events"]
                if bullet["event_id"] > last_sent_bullet_event_ids[mode]
            ]
            if pending_bullets:
                last_sent_bullet_event_ids[mode] = pending_bullets[-1]["event_id"]
            for snapshot_player_id, player in snapshot.items():
                player["bullets"] = list(pending_bullets)
                player["destroyed_treasures"] = list(events["destroyed_treasures"])
                player["destroyed_furniture"] = list(events["destroyed_furniture"])
                player["rune_alerts"] = [
                    (alert[0], alert[1], max(0, round((alert[2] - now_monotonic) * 1000)))
                    for alert in events["rune_alerts"]
                ]
                player["winner_id"] = winner_ids[0] if winner_ids and len(winner_ids) == 1 else None
                player["winner_ids"] = list(winner_ids or [])
                player["kill_scores"] = dict(score_snapshot)
                player["kill_count"] = score_snapshot.get(snapshot_player_id, 0)
                player["deathmatch_revive_used"] = player.get(
                    "deathmatch_revive_used", False
                )
                player["revive_token"] = player.get("revive_token", 0)
                player["revive_accepted_token"] = player.get(
                    "revive_accepted_token", 0
                )
                player["match_elapsed_ms"] = lobby_state.get("elapsed_ms", 0)
                respawn_at = player.get("deathmatch_respawn_at")
                player["respawn_ms_remaining"] = (
                    max(0, round((respawn_at - now_monotonic) * 1000))
                    if respawn_at is not None else 0
                )
                player["zone_elapsed_ms"] = lobby_state.get("elapsed_ms", 0)
                player["kill_events"] = list(events["kill_events"][-12:])
                player["damage_events"] = list(events["damage_events"][-32:])
                player["revive_events"] = list(events["revive_events"])
                player["supply_drops"] = [
                    {
                        **drop,
                        "warning_remaining_ms": max(
                            0, round((drop["warning_until"] - now_monotonic) * 1000)
                        ),
                        "expires_remaining_ms": max(
                            0, round((drop["expires_at"] - now_monotonic) * 1000)
                        ),
                    }
                    for drop in events["supply_drops"].values()
                ]
                player["supply_collection_events"] = list(
                    events["supply_collection_events"]
                )
                player["bush_leaf_events"] = list(events["bush_leaf_events"])
                player["stun_ms_remaining"] = max(
                    0, round((player.get("stunned_until", 0.0) - time.monotonic()) * 1000)
                )
                player["hidden"] = player.get("hp", 0) <= 0
            conn.sendall(pickle.dumps(snapshot))
            if winner_ids is not None:
                with player_lock:
                    pending_ids = result_pending_player_ids.get(mode, set())
                    pending_ids.discard(player_id)
                    if not pending_ids:
                        lobby.finish_match(mode)
                        completed_match_winner_ids.pop(mode, None)
                        result_pending_player_ids.pop(mode, None)
                        reset_match_events(mode)
    except Exception as e:
        print(f"[네트워크 오류] 플레이어 {player_id}번: {e}")
    finally:
        print(f"[퇴장] 플레이어 {player_id}번 접속 종료")

        with player_lock:
            mode = lobby.mode_for(player_id)
            players.pop(player_id, None)
            lobby.leave(player_id)
            if mode is not None and not lobby.active_player_ids(mode):
                reset_match_events(mode)
            for pending_mode, pending_ids in tuple(result_pending_player_ids.items()):
                pending_ids.discard(player_id)
                if not pending_ids and pending_mode in completed_match_winner_ids:
                    lobby.finish_match(pending_mode)
                    completed_match_winner_ids.pop(pending_mode, None)
                    result_pending_player_ids.pop(pending_mode, None)
                    reset_match_events(pending_mode)

        current_count = update_player_count(-1)
        print(f"[카운트] 현재 접속 인원: {current_count}")
        conn.close()


print("[서버 켜짐] 클라이언트 연결을 기다리는 중...")

while True:
    conn, addr = server.accept()
    player_id = generate_player_id()
    current_count = update_player_count(1)
    print(f"[접속] 새로운 플레이어 (ID: {player_id})")
    print(f"[카운트] 현재 접속 인원: {current_count}")
    threading.Thread(target=handle_client, args=(conn, player_id), daemon=True).start()
