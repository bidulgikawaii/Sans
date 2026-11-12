import copy
import math
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
    DEATHMATCH_RESPAWN_SAFE_DISTANCE_TILES,
    FLAGDOWN_DURATION_MS,
    FLAGDOWN_SKILL_NAMES,
    FLAGDOWN_SKILL_REWARD_INTERVAL_MS,
    FLAGDOWN_MAP_HEIGHT_TILES,
    FLAGDOWN_MAP_WIDTH_TILES,
    FLAGDOWN_SPAWN_TILES,
    FLAGDOWN_RESPAWN_MS,
    MINE_ARM_DELAY_MS,
    MINE_BLAST_RADIUS,
    MINE_DAMAGE,
    MINE_MAX_COUNT,
    MINE_TRIGGER_DELAY_MS,
    MINE_TRIGGER_RADIUS,
    BUSH_LEAF_INTERVAL_MS,
    GAME_MODE_DEBUG,
    GAME_MODE_DEATHMATCH,
    GAME_MODE_FLAGDOWN,
    GAME_MODE_NORMAL,
    FLAGDOWN_CAPTURE_GOAL,
    FLAGDOWN_CAPTURE_RADIUS,
    FLAGDOWN_CAPTURE_RATE,
    NETWORK_BUFFER_SIZE,
    LEADERBOARD_PORT,
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
    SPIRIT_TRIAL_CLONE_HP,
    SPIRIT_TRIAL_CLONE_LIFETIME_MS,
    SHIELD_HP,
    SUICIDE_RESPAWN_PENALTY_MS,
)
from CombatMechanics import apply_shield_activation, is_suicide_hit
from Weapon import WEAPONS
from Lobby import LobbyState
from Zone import MagneticZone
from GameModes import get_game_mode, get_game_modes, is_game_mode_registered
from FlareSupply import supply_spawn_requires_leader
from NetworkProtocol import FramedSocket
from FlagdownRewards import (
    acknowledge_flagdown_skill_rewards,
    update_flagdown_skill_rewards,
)
from MineAuthority import advance_mines, register_mine_placements, serialize_mines
from LeaderboardAPI import (
    LeaderboardHTTPServer,
    build_leaderboard_snapshot,
)

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
        "spectator_skill_events": [],
        "next_spectator_skill_event_id": 1,
        "verified_bullet_events": {},
        "client_bullet_tokens": {},
        "consumed_spirit_shots": set(),
        "processed_clone_hits": set(),
        "linked_clones": [],
        "next_clone_id": 1,
        "destroyed_treasures": set(),
        "destroyed_furniture": set(),
        "rune_alerts": [],
        "kill_events": [],
        "next_kill_event_id": 1,
        "kill_scores": {},
        "damage_events": [],
        "next_damage_event_id": 1,
        "supply_drops": {},
        "next_supply_drop_id": 1,
        "supply_collection_events": [],
        "next_supply_collection_id": 1,
        "bush_leaf_events": [],
        "next_bush_leaf_event_id": 1,
        "mines": [],
        "next_mine_id": 1,
        "mine_hit_authorizations": {},
        "mine_blast_events": [],
        "flagdown_progress": {0: 0.0, 1: 0.0},
        "flagdown_updated_at": None,
    }


def append_kill_event(
    events, killer_id, target_id, killer_name, target_name, weapon_id, cause,
    bat_launch=None,
):
    event = {
        "event_id": events["next_kill_event_id"],
        "killer_id": killer_id,
        "target_id": target_id,
        "killer_name": killer_name,
        "target_name": target_name,
        "weapon_id": weapon_id,
        "cause": cause,
    }
    if bat_launch is not None:
        event["bat_launch"] = bat_launch
    events["kill_events"].append(event)
    events["next_kill_event_id"] += 1


def serialize_linked_clones(clones, now):
    return [
        {
            **clone,
            "age_ms": max(0, round((now - clone["created_at"]) * 1000)),
        }
        for clone in clones
    ]


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


def mode_map_dimensions(mode):
    if mode == GAME_MODE_FLAGDOWN:
        return FLAGDOWN_MAP_WIDTH_TILES, FLAGDOWN_MAP_HEIGHT_TILES
    return MAP_WIDTH_TILES, MAP_HEIGHT_TILES


def validated_spawn_tiles(raw_tiles, mode=GAME_MODE_NORMAL):
    if mode == GAME_MODE_FLAGDOWN:
        return list(FLAGDOWN_SPAWN_TILES)
    if not isinstance(raw_tiles, (list, tuple)):
        return []
    map_width, map_height = mode_map_dimensions(mode)
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
            or not (0 <= x < map_width - 2)
            or not (0 <= y < map_height - 2)
        ):
            continue
        if (x, y) not in spawn_tiles:
            spawn_tiles.append((x, y))
        if len(spawn_tiles) >= MAX_PLAYERS:
            break
    return spawn_tiles


def select_respawn_spawn(mode, player_id, spawn_tiles, match_player_ids, players, lobby):
    """Choose the player's fixed team slot or the safest deathmatch spawn."""
    if mode == GAME_MODE_FLAGDOWN:
        return lobby.team_spawn_tile(player_id)

    if mode == GAME_MODE_DEATHMATCH:
        enemy_positions = [
            (other_player["posX"] / 32, other_player["posY"] / 32)
            for active_id in match_player_ids
            if active_id != player_id
            and (other_player := players.get(active_id)) is not None
            and other_player["hp"] > 0
        ]
        player = players.get(player_id, {})
        return choose_respawn(
            spawn_tiles,
            enemy_positions,
            safe_radius=DEATHMATCH_RESPAWN_SAFE_DISTANCE_TILES,
            recent_spawns=player.get("recent_spawn_points", ()),
            weighted=True,
        )

    return random.choice(spawn_tiles) if spawn_tiles else None


def choose_respawn(
    spawn_points,
    enemies,
    safe_radius=DEATHMATCH_RESPAWN_SAFE_DISTANCE_TILES,
    recent_spawns=(),
    weighted=False,
):
    """Choose a safe spawn, preferring locations not used in recent respawns."""
    if safe_radius <= 0:
        raise ValueError("safe_radius must be positive")
    radius_squared = safe_radius ** 2
    candidates = [
        point
        for point in spawn_points
        if all(
            (point[0] - enemy[0]) ** 2 + (point[1] - enemy[1]) ** 2
            >= radius_squared
            for enemy in enemies
        )
    ]
    if not candidates:
        return None

    recent = set(recent_spawns)
    fresh_candidates = [point for point in candidates if point not in recent]
    pool = fresh_candidates or candidates
    if not weighted or not enemies:
        return random.choice(pool)

    weights = [
        min(math.dist(point, enemy) for enemy in enemies)
        for point in pool
    ]
    return random.choices(pool, weights=weights, k=1)[0]


def is_friendly_fire(mode, attacker_id, target_id, lobby):
    return (
        mode == GAME_MODE_FLAGDOWN
        and attacker_id != target_id
        and lobby.team_for(attacker_id) == lobby.team_for(target_id)
    )


def get_last_match_player(mode, match_started, active_match_player_ids):
    if mode == GAME_MODE_DEBUG or not match_started or len(active_match_player_ids) != 1:
        return None
    return next(iter(active_match_player_ids))


def handle_client(conn, player_id):
    conn = FramedSocket(conn)
    with player_lock:
        # 접속 전에 발생한 총알은 새 플레이어에게 전달하지 않습니다.
        last_sent_bullet_event_ids = {
            mode: events["next_bullet_event_id"] - 1
            for mode, events in match_events.items()
        }
        last_sent_skill_event_ids = {
            mode: events["next_spectator_skill_event_id"] - 1
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
        "heal_token": 0,
        "shield_active": False,
        "shield_hp": 0,
        "shield_token": 0,
        "rune_alerts": [],
        "stunned_until": 0.0,
        "zone_outside_since": None,
        "zone_damage_credit": 0.0,
        "zone_last_tick": time.monotonic(),
        "bullets": [],
        "deathmatch_respawn_at": None,
        "spawn_index": None,
        "spawn_tiles": [],
        "recent_spawn_points": [],
        "spawn_history_initialized": False,
        "kill_count": 0,
        "flagdown_skill_rewards": [],
        "flagdown_awarded_skills": [],
        "next_flagdown_skill_reward_id": 1,
        "next_flagdown_skill_reward_ms": FLAGDOWN_SKILL_REWARD_INTERVAL_MS,
        "last_mine_request_id": 0,
        "mine_ack_id": 0,
    }

    try:
        while True:
            # 2. 클라이언트가 보낸 데이터(posX, posY, angle) 수신
            data = conn.recv(NETWORK_BUFFER_SIZE)
            if not data:
                break

            client_data = pickle.loads(data)

            if client_data.get("type") == "spectator_snapshot":
                with player_lock:
                    mode = lobby.mode_for(player_id)
                    if mode is None:
                        snapshot = lobby.status(player_id)
                    else:
                        events = match_events[mode]
                        visible_ids = lobby.visible_player_ids(player_id)
                        snapshot = copy.deepcopy({
                            visible_id: players[visible_id]
                            for visible_id in visible_ids
                            if visible_id in players
                        })
                        pending_bullets = [
                            bullet for bullet in events["bullet_events"]
                            if bullet["event_id"] > last_sent_bullet_event_ids[mode]
                        ]
                        pending_skills = [
                            event for event in events["spectator_skill_events"]
                            if event["event_id"] > last_sent_skill_event_ids[mode]
                        ]
                        if pending_bullets:
                            last_sent_bullet_event_ids[mode] = pending_bullets[-1]["event_id"]
                        if pending_skills:
                            last_sent_skill_event_ids[mode] = pending_skills[-1]["event_id"]
                        lobby_state = lobby.status(player_id, mode)
                        winner_ids = list(completed_match_winner_ids.get(mode, []))
                        scores = dict(events["kill_scores"])
                        for snapshot_player_id, player in snapshot.items():
                            player["bullets"] = list(pending_bullets)
                            player["flagdown_skill_rewards"] = []
                            player["spectator_skill_events"] = list(pending_skills)
                            player["linked_clones"] = serialize_linked_clones(
                                events["linked_clones"], time.monotonic()
                            )
                            player["winner_id"] = (
                                winner_ids[0] if len(winner_ids) == 1 else None
                            )
                            player["winner_ids"] = winner_ids
                            player["match_draw"] = (
                                mode == GAME_MODE_FLAGDOWN
                                and mode in completed_match_winner_ids
                                and not winner_ids
                            )
                            player["kill_scores"] = scores
                            player["kill_count"] = scores.get(snapshot_player_id, 0)
                            player["match_elapsed_ms"] = lobby_state.get("elapsed_ms", 0)
                            player["flagdown_remaining_ms"] = max(
                                0,
                                FLAGDOWN_DURATION_MS - lobby_state.get("elapsed_ms", 0),
                            )
                            player["zone_elapsed_ms"] = lobby_state.get("elapsed_ms", 0)
                            player["team_id"] = lobby.team_for(snapshot_player_id)
                            player["team_spawn_index"] = lobby.team_spawn_index(snapshot_player_id)
                            player["flagdown_progress"] = dict(events["flagdown_progress"])
                            player["active_mines"] = serialize_mines(
                                events, time.monotonic()
                            )
                            player["mine_blast_events"] = list(
                                events["mine_blast_events"]
                            )
                            player["mine_ack_id"] = (
                                player.get("mine_ack_id", 0)
                                if snapshot_player_id == player_id
                                else 0
                            )
                            player["stun_ms_remaining"] = max(
                                0,
                                round((player.get("stunned_until", 0.0) - time.monotonic()) * 1000),
                            )
                            player["hidden"] = player.get("hp", 0) <= 0
                            player["weather"] = lobby_state.get("weather")
                conn.sendall(pickle.dumps(snapshot))
                continue

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
                        last_sent_skill_event_ids[requested_mode] = (
                            match_events[requested_mode]["next_spectator_skill_event_id"] - 1
                        )
                        requested_name = str(client_data.get("name", "")).strip()
                        player = players[player_id]
                        player["name"] = (
                            requested_name or f"유저_{player_id}"
                        )[:16]
                        if previous_mode != requested_mode:
                            player.update({
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
                                "heal_token": 0,
                                "shield_active": False,
                                "shield_hp": 0,
                                "shield_token": 0,
                                "rune_alerts": [],
                                "stunned_until": 0.0,
                                "zone_outside_since": None,
                                "zone_damage_credit": 0.0,
                                "zone_last_tick": time.monotonic(),
                                "bullets": [],
                                "deathmatch_respawn_at": None,
                                "recent_spawn_points": [],
                                "spawn_history_initialized": False,
                                "kill_count": 0,
                                "flagdown_skill_rewards": [],
                                "flagdown_awarded_skills": [],
                                "next_flagdown_skill_reward_id": 1,
                                "next_flagdown_skill_reward_ms": FLAGDOWN_SKILL_REWARD_INTERVAL_MS,
                            })
                        if requested_mode in (GAME_MODE_DEATHMATCH, GAME_MODE_FLAGDOWN):
                            spawn_candidates = validated_spawn_tiles(
                                client_data.get("spawn_tiles"),
                                requested_mode,
                            )
                            if not spawn_candidates:
                                accepted = False
                                lobby.leave(player_id)
                            else:
                                if previous_mode != requested_mode:
                                    player["spawn_index"] = None
                                player["spawn_tiles"] = spawn_candidates
                                if requested_mode == GAME_MODE_DEATHMATCH:
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
                    if accepted and client_data.get("ready_on_join", False):
                        accepted = lobby.set_ready(player_id, True)
                    lobby_status = lobby.status(player_id, mode=requested_mode)
                    lobby_status["accepted"] = accepted
                    if accepted:
                        if requested_mode == GAME_MODE_DEATHMATCH:
                            lobby_status["spawn_index"] = players[player_id]["spawn_index"]
                        elif requested_mode == GAME_MODE_FLAGDOWN:
                            lobby_status["team_id"] = lobby.team_for(player_id)
                            lobby_status["team_spawn_index"] = lobby.team_spawn_index(player_id)
                            lobby_status["spawn_tile"] = lobby.team_spawn_tile(player_id)
                            lobby_status["spawn_index"] = spawn_candidates.index(
                                lobby_status["spawn_tile"]
                            )
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
                                if requested_mode in (GAME_MODE_DEATHMATCH, GAME_MODE_FLAGDOWN)
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
                            players[player_id]["deathmatch_respawn_at"] = None
                            lobby.leave(player_id)
                            response = {"type": "match_defeat", "mode": mode}
                    elif mode is not None:
                        lobby.leave(player_id)
                        response = {"type": "lobby_left", "mode": mode}
                    else:
                        response = lobby.status(player_id)
                    for pending_mode, pending_ids in tuple(result_pending_player_ids.items()):
                        pending_ids.discard(player_id)
                        if not pending_ids and pending_mode in completed_match_winner_ids:
                            lobby.finish_match(pending_mode)
                            completed_match_winner_ids.pop(pending_mode, None)
                            result_pending_player_ids.pop(pending_mode, None)
                            reset_match_events(pending_mode)
                    if mode is not None and not lobby.active_player_ids(mode):
                        completed_match_winner_ids.pop(mode, None)
                        result_pending_player_ids.pop(mode, None)
                        reset_match_events(mode)
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
                        if drop_type == "skill" and mode != GAME_MODE_DEATHMATCH:
                            continue
                        try:
                            drop_x = float(request["x"])
                            drop_y = float(request["y"])
                            warning_ms = int(request.get("warning_ms", 2200))
                            lifetime_ms = int(request.get("lifetime_ms", 30_000))
                        except (KeyError, TypeError, ValueError):
                            continue
                        map_width, map_height = mode_map_dimensions(mode)
                        if not (0 <= drop_x < map_width * 32 and 0 <= drop_y < map_height * 32):
                            continue
                        if len(events["supply_drops"]) >= 64:
                            continue
                        if supply_spawn_requires_leader(
                            drop_type, request.get("source")
                        ):
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

            # Update player state stored on the server.
            # Respawn modes keep position server-authoritative while the client is dead.
            # If another handler has already respawned this player, that player's next
            # packet can still contain hp=0 and the old death position. Do not let that
            # stale packet overwrite the fixed team/deathmatch respawn location.
            client_reports_alive = client_data.get("hp", PLAYER_MAX_HP) > 0
            can_accept_client_position = (
                mode not in (GAME_MODE_DEATHMATCH, GAME_MODE_FLAGDOWN)
                or (players[player_id]["hp"] > 0 and client_reports_alive)
            )
            if can_accept_client_position:
                players[player_id]["posX"] = client_data["posX"]
                players[player_id]["posY"] = client_data["posY"]
                if (
                    mode == GAME_MODE_DEATHMATCH
                    and not players[player_id]["spawn_history_initialized"]
                ):
                    players[player_id]["recent_spawn_points"].append((
                        int(players[player_id]["posX"] // 32),
                        int(players[player_id]["posY"] // 32),
                    ))
                    players[player_id]["spawn_history_initialized"] = True
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
                        map_width, map_height = mode_map_dimensions(mode)
                        if not (
                            0 <= player_x < map_width * 32
                            and 0 <= player_y < map_height * 32
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
            try:
                reported_shield_token = max(0, int(client_data.get("shield_token", 0)))
            except (TypeError, ValueError):
                reported_shield_token = players[player_id]["shield_token"]
            (
                players[player_id]["shield_token"],
                players[player_id]["shield_hp"],
            ) = apply_shield_activation(
                players[player_id]["shield_token"],
                players[player_id]["shield_hp"],
                reported_shield_token,
                players[player_id]["hp"],
                SHIELD_HP,
            )
            players[player_id]["shield_active"] = players[player_id]["shield_hp"] > 0
            heal_token = int(client_data.get("heal_token", 0))
            if heal_token != players[player_id]["heal_token"]:
                players[player_id]["heal_token"] = heal_token
                heal_amount = max(0, int(client_data.get("heal_amount", 0)))
                players[player_id]["hp"] = min(
                    PLAYER_MAX_HP,
                    players[player_id]["hp"] + heal_amount,
                )
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
            if mode == GAME_MODE_FLAGDOWN and lobby.started[mode]:
                reported_skills = client_data.get("owned_skills", [])
                if not isinstance(reported_skills, list):
                    reported_skills = []
                owned_skills = {
                    skill for skill in reported_skills
                    if isinstance(skill, str) and skill in FLAGDOWN_SKILL_NAMES
                }
                with player_lock:
                    acknowledge_flagdown_skill_rewards(
                        players[player_id],
                        client_data.get("flagdown_skill_reward_ack"),
                    )
                    update_flagdown_skill_rewards(
                        players[player_id],
                        lobby_state.get("elapsed_ms", 0),
                        owned_skills,
                        FLAGDOWN_SKILL_NAMES,
                    )
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
                    if previous_hp > 0 and players[player_id]["hp"] <= 0:
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

            mine_hits = []
            if mode is not None and lobby.started.get(mode, False):
                map_width, map_height = mode_map_dimensions(mode)
                with player_lock:
                    if players[player_id]["hp"] > 0:
                        players[player_id]["mine_ack_id"] = register_mine_placements(
                            events,
                            players[player_id],
                            player_id,
                            client_data.get("mine_placement_requests", []),
                            now_monotonic,
                            map_width * 32,
                            map_height * 32,
                            lobby.team_for(player_id),
                            MINE_ARM_DELAY_MS,
                            MINE_MAX_COUNT,
                        )
                    mine_hits = advance_mines(
                        events,
                        players,
                        lobby.active_player_ids(mode),
                        lobby.team_for,
                        mode,
                        now_monotonic,
                        MINE_TRIGGER_RADIUS + 18,
                        MINE_BLAST_RADIUS,
                        MINE_TRIGGER_DELAY_MS,
                        MINE_DAMAGE,
                    )

            suicide_detonated = False
            events["linked_clones"][:] = [
                clone for clone in events["linked_clones"]
                if now_monotonic - clone["created_at"]
                < SPIRIT_TRIAL_CLONE_LIFETIME_MS / 1000
            ]
            reported_hit_events = client_data.get("hit_events", [])
            if not isinstance(reported_hit_events, list):
                reported_hit_events = []
            for hit_event, server_mine_event in (
                [(event, True) for event in mine_hits]
                + [(event, False) for event in reported_hit_events]
            ):
                if not isinstance(hit_event, dict):
                    continue
                authorized_mine = False
                if server_mine_event:
                    auth_key = (
                        hit_event.get("_mine_authorization_id"),
                        hit_event.get("target_id"),
                    )
                    with player_lock:
                        authorized_owner = events["mine_hit_authorizations"].pop(
                            auth_key, None
                        )
                    authorized_mine = (
                        authorized_owner == hit_event.get("attacker_id")
                        and hit_event.get("skill_source") == "지뢰"
                    )
                    if not authorized_mine:
                        continue
                if (
                    mode in (GAME_MODE_DEATHMATCH, GAME_MODE_FLAGDOWN)
                    and players[player_id]["hp"] <= 0
                    and not authorized_mine
                ):
                    break
                attacker_id = hit_event.get("attacker_id", player_id)
                if (
                    not isinstance(attacker_id, str)
                    or (
                        attacker_id not in lobby.visible_player_ids(player_id)
                        and not (
                            authorized_mine
                            and attacker_id in players
                            and lobby.mode_for(attacker_id) == mode
                        )
                    )
                ):
                    continue
                source_bullet = None
                client_bullet_token = hit_event.get("client_bullet_token")
                token_bullet = None
                if isinstance(client_bullet_token, int) and not isinstance(
                    client_bullet_token, bool
                ):
                    token_bullet = events["client_bullet_tokens"].get(
                        (attacker_id, client_bullet_token)
                    )
                    if (
                        token_bullet is not None
                        and now_monotonic - token_bullet["created_at"] > 5000
                    ):
                        token_bullet = None

                if hit_event.get("weapon_id") == "spirit_trial":
                    if token_bullet is None or token_bullet["weapon_id"] != "spirit_trial":
                        continue
                    if attacker_id != player_id:
                        try:
                            spirit_bullet_event_id = int(
                                hit_event.get("source_bullet_event_id")
                            )
                        except (TypeError, ValueError):
                            continue
                        spirit_bullet_event = events["verified_bullet_events"].get(
                            spirit_bullet_event_id
                        )
                        if (
                            spirit_bullet_event is None
                            or spirit_bullet_event["owner_id"] != attacker_id
                            or spirit_bullet_event["weapon_id"] != "spirit_trial"
                            or now_monotonic - spirit_bullet_event["created_at"] > 5000
                        ):
                            continue
                    spirit_shot_key = (attacker_id, client_bullet_token)
                    if spirit_shot_key in events["consumed_spirit_shots"]:
                        continue
                    target_id = hit_event.get("target_id")
                    if (
                        not isinstance(target_id, str)
                        or target_id not in lobby.visible_player_ids(player_id)
                        or is_friendly_fire(mode, attacker_id, target_id, lobby)
                        or target_id == attacker_id
                    ):
                        continue
                    target = players.get(target_id)
                    if target is None or target["hp"] <= 0:
                        continue
                    try:
                        clone_x = float(hit_event["impact_x"])
                        clone_y = float(hit_event["impact_y"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    map_width, map_height = mode_map_dimensions(mode)
                    if (
                        not math.isfinite(clone_x)
                        or not math.isfinite(clone_y)
                        or not 0 <= clone_x < map_width * 32
                        or not 0 <= clone_y < map_height * 32
                        or math.hypot(
                            clone_x - (target["posX"] + 36),
                            clone_y - (target["posY"] + 36),
                        ) > 100
                    ):
                        continue
                    events["consumed_spirit_shots"].add(spirit_shot_key)
                    owner_clones = [
                        clone for clone in events["linked_clones"]
                        if clone["owner_id"] == attacker_id
                    ]
                    if len(owner_clones) >= 3:
                        oldest_clone = owner_clones[0]
                        events["linked_clones"].remove(oldest_clone)
                    events["linked_clones"].append({
                        "clone_id": events["next_clone_id"],
                        "owner_id": attacker_id,
                        "linked_player_id": target_id,
                        "x": clone_x,
                        "y": clone_y,
                        "hp": SPIRIT_TRIAL_CLONE_HP,
                        "max_hp": SPIRIT_TRIAL_CLONE_HP,
                        "created_at": now_monotonic,
                    })
                    events["next_clone_id"] += 1
                    continue

                if hit_event.get("target_kind") == "clone":
                    try:
                        clone_id = int(hit_event.get("clone_id"))
                    except (TypeError, ValueError):
                        continue
                    clone = next(
                        (
                            item for item in events["linked_clones"]
                            if item["clone_id"] == clone_id
                        ),
                        None,
                    )
                    if clone is None:
                        continue
                    source_bullet = None
                    source_bullet_event_id = hit_event.get(
                        "source_bullet_event_id"
                    )
                    if attacker_id != player_id:
                        try:
                            source_bullet_event_id = int(source_bullet_event_id)
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
                    if client_bullet_token is not None and token_bullet is None:
                        continue
                    hit_identity = (
                        source_bullet_event_id
                        if source_bullet_event_id is not None
                        else client_bullet_token
                    )
                    if hit_identity is not None:
                        clone_hit_key = (clone_id, attacker_id, hit_identity)
                        if clone_hit_key in events["processed_clone_hits"]:
                            continue
                        events["processed_clone_hits"].add(clone_hit_key)
                    try:
                        clone_damage = max(0, int(hit_event.get("damage", 0)))
                    except (TypeError, ValueError):
                        continue
                    if hit_event.get("hit_part") == "head":
                        clone_damage *= HEADSHOT_DAMAGE_MULTIPLIER
                    clone_damage = min(clone_damage, clone["hp"])
                    if clone_damage <= 0:
                        continue
                    clone["hp"] -= clone_damage
                    linked_target_id = clone["linked_player_id"]
                    linked_target = players.get(linked_target_id)
                    previous_linked_hp = (
                        linked_target["hp"] if linked_target is not None else 0
                    )
                    linked_damage = 0
                    linked_shield_damage = 0
                    if linked_target is not None and linked_target["hp"] > 0:
                        linked_shield_damage = min(
                            linked_target.get("shield_hp", 0), clone_damage
                        )
                        linked_target["shield_hp"] -= linked_shield_damage
                        linked_target["shield_active"] = linked_target["shield_hp"] > 0
                        linked_damage = min(
                            clone_damage - linked_shield_damage,
                            linked_target["hp"],
                        )
                        linked_target["hp"] -= linked_damage
                    hit_weapon_id = (
                        token_bullet["weapon_id"]
                        if token_bullet is not None
                        else source_bullet["weapon_id"]
                        if source_bullet is not None
                        else hit_event.get("weapon_id", DEFAULT_WEAPON_ID)
                    )
                    events["damage_events"].append({
                        "event_id": events["next_damage_event_id"],
                        "attacker_id": attacker_id,
                        "target_id": linked_target_id,
                        "damage": linked_damage,
                        "shield_damage": linked_shield_damage,
                        "hit_part": "body",
                        "stun_ms": 0,
                        "weapon_id": hit_weapon_id,
                        "clone_id": clone_id,
                        "clone_x": clone["x"],
                        "clone_y": clone["y"],
                        "clone_damage": clone_damage,
                        "clone_hp": clone["hp"],
                    })
                    events["next_damage_event_id"] += 1
                    if (
                        linked_target is not None
                        and previous_linked_hp > 0
                        and linked_target["hp"] <= 0
                    ):
                        if mode in (GAME_MODE_DEATHMATCH, GAME_MODE_FLAGDOWN):
                            linked_target["deathmatch_respawn_at"] = (
                                now_monotonic
                                + (
                                    FLAGDOWN_RESPAWN_MS
                                    if mode == GAME_MODE_FLAGDOWN
                                    else DEATHMATCH_RESPAWN_MS
                                ) / 1000
                            )
                        if (
                            mode in (
                                GAME_MODE_NORMAL,
                                GAME_MODE_DEATHMATCH,
                                GAME_MODE_FLAGDOWN,
                            )
                            and attacker_id != linked_target_id
                        ):
                            events["kill_scores"][attacker_id] = (
                                events["kill_scores"].get(attacker_id, 0) + 1
                            )
                        append_kill_event(
                            events,
                            attacker_id,
                            linked_target_id,
                            players[attacker_id].get("name", "플레이어"),
                            linked_target.get("name", "플레이어"),
                            hit_weapon_id,
                            "spirit_clone",
                        )
                    if clone["hp"] <= 0:
                        events["linked_clones"].remove(clone)
                    continue

                target_id = hit_event.get("target_id")
                if not isinstance(target_id, str) or target_id not in lobby.visible_player_ids(player_id):
                    continue
                target = players.get(target_id)
                if (
                    not target
                    or target["hp"] <= 0
                ):
                    continue
                attacker_id = hit_event.get("attacker_id", player_id)
                if (
                    not isinstance(attacker_id, str)
                    or attacker_id not in lobby.visible_player_ids(player_id)
                ):
                    continue
                if is_friendly_fire(mode, attacker_id, target_id, lobby):
                    continue
                if attacker_id != player_id and not authorized_mine:
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
                damage = max(0, int(hit_event.get("damage", 0)))
                hit_weapon_id = hit_event.get("weapon_id")
                if not isinstance(hit_weapon_id, str) or hit_weapon_id not in WEAPONS:
                    hit_weapon_id = players[attacker_id].get("weapon_id", DEFAULT_WEAPON_ID)
                if (
                    hit_event.get("hit_part") == "head"
                    and hit_weapon_id != "Revolver_golden"
                ):
                    damage *= HEADSHOT_DAMAGE_MULTIPLIER
                is_bat_hit = (
                    attacker_id == player_id
                    and hit_weapon_id == "bat"
                    and players[player_id].get("weapon_id") == "bat"
                )
                stun_ms = max(0, int(hit_event.get("stun_ms", 0)))
                previous_hp = target["hp"]
                if is_bat_hit:
                    damage = previous_hp + target.get("shield_hp", 0)
                else:
                    damage = min(damage, previous_hp + target.get("shield_hp", 0))
                shield_damage = min(target.get("shield_hp", 0), damage)
                target["shield_hp"] -= shield_damage
                target["shield_active"] = target["shield_hp"] > 0
                health_damage = min(damage - shield_damage, previous_hp)
                target["hp"] = previous_hp - health_damage
                damage = shield_damage + health_damage
                is_suicide = is_suicide_hit(
                    attacker_id,
                    target_id,
                    hit_event.get("skill_source"),
                )
                if is_suicide and previous_hp > 0:
                    suicide_detonated = True
                events["damage_events"].append({
                    "event_id": events["next_damage_event_id"],
                    "attacker_id": attacker_id,
                    "target_id": target_id,
                    "damage": damage,
                    "shield_damage": shield_damage,
                    "hit_part": hit_event.get("hit_part", "body"),
                    "stun_ms": stun_ms,
                    "weapon_id": hit_weapon_id,
                })
                events["next_damage_event_id"] += 1
                if (
                    previous_hp > 0
                    and target["hp"] <= 0
                ):
                    if mode in (GAME_MODE_DEATHMATCH, GAME_MODE_FLAGDOWN):
                        target["deathmatch_respawn_at"] = (
                            now_monotonic
                            + (
                                FLAGDOWN_RESPAWN_MS
                                if mode == GAME_MODE_FLAGDOWN
                                else DEATHMATCH_RESPAWN_MS
                            ) / 1000
                            + (
                                SUICIDE_RESPAWN_PENALTY_MS / 1000
                                if is_suicide
                                else 0
                            )
                        )
                    if (
                        mode in (
                            GAME_MODE_NORMAL,
                            GAME_MODE_DEATHMATCH,
                            GAME_MODE_FLAGDOWN,
                        )
                        and attacker_id != target_id
                    ):
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
                        source_bullet["weapon_id"] if source_bullet else hit_weapon_id,
                        "bat" if is_bat_hit else (
                            "self_inflicted" if is_suicide else "player"
                        ),
                        {
                            "x": target.get("posX", 0) + 36,
                            "y": target.get("posY", 0) + 36,
                            "direction_x": (
                                (target.get("posX", 0) - players[attacker_id].get("posX", 0))
                                if (target.get("posX", 0) != players[attacker_id].get("posX", 0))
                                or (target.get("posY", 0) != players[attacker_id].get("posY", 0))
                                else 1
                            ),
                            "direction_y": target.get("posY", 0) - players[attacker_id].get("posY", 0),
                        }
                        if is_bat_hit else None,
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
                    client_bullet_token = bullet_event.get("client_bullet_token")
                    if (
                        isinstance(client_bullet_token, int)
                        and not isinstance(client_bullet_token, bool)
                    ):
                        events["client_bullet_tokens"][(player_id, client_bullet_token)] = {
                            "weapon_id": bullet_event["weapon_id"],
                            "created_at": now_monotonic,
                        }
                    events["next_bullet_event_id"] += 1
                    events["bullet_events"].append(bullet_event)
                skill_events = client_data.get("spectator_skill_events", [])
                if isinstance(skill_events, list) and (
                    players[player_id]["hp"] > 0 or suicide_detonated
                ):
                    allowed_skills = {
                        "폭탄받아라!", "자폭", "매의 눈", "와드", "영혼탄환",
                        "보호막", "은신", "텔포", "기절탄", "플레어건",
                    }
                    for skill_event in skill_events[:8]:
                        if not isinstance(skill_event, dict):
                            continue
                        skill_name = skill_event.get("skill")
                        try:
                            skill_x = float(skill_event.get("x"))
                            skill_y = float(skill_event.get("y"))
                        except (TypeError, ValueError):
                            continue
                        if (
                            skill_name not in allowed_skills
                            or not math.isfinite(skill_x)
                            or not math.isfinite(skill_y)
                            or not 0 <= skill_x < mode_map_dimensions(mode)[0] * 32
                            or not 0 <= skill_y < mode_map_dimensions(mode)[1] * 32
                        ):
                            continue
                        events["spectator_skill_events"].append({
                            "event_id": events["next_spectator_skill_event_id"],
                            "player_id": player_id,
                            "skill": skill_name,
                            "x": skill_x,
                            "y": skill_y,
                        })
                        events["next_spectator_skill_event_id"] += 1
                    events["spectator_skill_events"][:] = events[
                        "spectator_skill_events"
                    ][-128:]
                events["verified_bullet_events"] = {
                    event_id: bullet_info
                    for event_id, bullet_info
                    in events["verified_bullet_events"].items()
                    if now_monotonic - bullet_info["created_at"] <= 5000
                }
                events["client_bullet_tokens"] = {
                    token_key: bullet_info
                    for token_key, bullet_info
                    in events["client_bullet_tokens"].items()
                    if now_monotonic - bullet_info["created_at"] <= 5000
                }

            # 4. 현재 접속한 모든 유저들의 데이터를 통째로 패킹해서 응답
            with player_lock:
                now_monotonic = time.monotonic()
                if mode in (GAME_MODE_DEATHMATCH, GAME_MODE_FLAGDOWN):
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
                            spawn_position = select_respawn_spawn(
                                mode,
                                respawn_id,
                                respawning_player.get("spawn_tiles", ()),
                                lobby.match_player_ids[mode],
                                players,
                                lobby,
                            )
                            if spawn_position is not None:
                                spawn_x, spawn_y = spawn_position
                                respawning_player["posX"] = spawn_x * 32
                                respawning_player["posY"] = spawn_y * 32
                                if mode == GAME_MODE_DEATHMATCH:
                                    recent_spawns = respawning_player[
                                        "recent_spawn_points"
                                    ]
                                    recent_spawns.append((spawn_x, spawn_y))
                                    del recent_spawns[:-3]
                                respawning_player["magazine_ammo"] = WEAPONS[
                                    respawning_player["weapon_id"]
                                ].magazine_size
                                respawning_player["hp"] = PLAYER_MAX_HP
                                respawning_player["shield_hp"] = 0
                                respawning_player["shield_active"] = False
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
                winner_ids = completed_match_winner_ids.get(mode)
                if (
                    winner_ids is None
                    and mode == GAME_MODE_FLAGDOWN
                    and lobby.started[mode]
                ):
                    previous_update = events["flagdown_updated_at"]
                    events["flagdown_updated_at"] = now_monotonic
                    capture_elapsed = (
                        min(0.25, max(0.0, now_monotonic - previous_update))
                        if previous_update is not None
                        else 0.0
                    )
                    map_width, map_height = mode_map_dimensions(mode)
                    center_x = map_width * 32 / 2
                    center_y = map_height * 32 / 2
                    present_teams = set()
                    active_match_ids = (
                        set(match_player_ids)
                        & lobby.active_player_ids(mode)
                    )
                    for active_id in active_match_ids:
                        candidate = players.get(active_id)
                        team_id = lobby.team_for(active_id)
                        if (
                            candidate is None
                            or candidate["hp"] <= 0
                            or team_id not in events["flagdown_progress"]
                        ):
                            continue
                        try:
                            player_x = float(candidate.get("posX", 0)) + 36
                            player_y = float(candidate.get("posY", 0)) + 36
                        except (TypeError, ValueError):
                            continue
                        if (
                            math.isfinite(player_x)
                            and math.isfinite(player_y)
                            and (player_x - center_x) ** 2 + (player_y - center_y) ** 2
                            <= FLAGDOWN_CAPTURE_RADIUS ** 2
                        ):
                            present_teams.add(team_id)
                    if len(present_teams) == 1 and capture_elapsed:
                        capturing_team = next(iter(present_teams))
                        events["flagdown_progress"][capturing_team] = min(
                            FLAGDOWN_CAPTURE_GOAL,
                            events["flagdown_progress"][capturing_team]
                            + capture_elapsed * FLAGDOWN_CAPTURE_RATE,
                        )
                    winning_team = next(
                        (
                            team_id
                            for team_id, progress in events["flagdown_progress"].items()
                            if progress >= FLAGDOWN_CAPTURE_GOAL
                        ),
                        None,
                    )
                    if winning_team is not None:
                        winner_ids = [
                            match_id
                            for match_id in match_player_ids
                            if lobby.team_for(match_id) == winning_team
                        ]
                        completed_match_winner_ids[mode] = winner_ids
                        result_pending_player_ids[mode] = (
                            active_match_ids & players.keys()
                        )
                    elif (
                        lobby_state.get("elapsed_ms", 0) >= FLAGDOWN_DURATION_MS
                    ):
                        active_match_ids = (
                            set(match_player_ids)
                            & lobby.active_player_ids(mode)
                            & players.keys()
                        )
                        blue_score = events["flagdown_progress"][0]
                        red_score = events["flagdown_progress"][1]
                        if math.isclose(blue_score, red_score, abs_tol=1e-6):
                            winner_ids = []
                        else:
                            winning_team = 0 if blue_score > red_score else 1
                            winner_ids = [
                                match_id
                                for match_id in match_player_ids
                                if lobby.team_for(match_id) == winning_team
                            ]
                        completed_match_winner_ids[mode] = winner_ids
                        result_pending_player_ids[mode] = active_match_ids
                if (
                    winner_ids is None
                    and mode == GAME_MODE_DEATHMATCH
                    and lobby.started[mode]
                    and lobby.status(player_id, mode).get("elapsed_ms", 0)
                    >= DEATHMATCH_DURATION_MS
                ):
                    active_match_ids = (
                        set(match_player_ids)
                        & lobby.active_player_ids(mode)
                        & players.keys()
                    )
                    scores = {
                        match_id: events["kill_scores"].get(match_id, 0)
                        for match_id in active_match_ids
                    }
                    highest_score = max(scores.values(), default=0)
                    winner_ids = [
                        match_id for match_id, score in scores.items()
                        if score == highest_score
                    ]
                    completed_match_winner_ids[mode] = winner_ids
                    result_pending_player_ids[mode] = active_match_ids
                active_match_player_ids = (
                    set(match_player_ids)
                    & lobby.active_player_ids(mode)
                    & players.keys()
                )
                last_match_player = get_last_match_player(
                    mode,
                    lobby.started[mode],
                    active_match_player_ids,
                )
                if winner_ids is None and last_match_player is not None:
                    winner_ids = [last_match_player]
                    completed_match_winner_ids[mode] = winner_ids
                    result_pending_player_ids[mode] = set(active_match_player_ids)
                if winner_ids is None and get_game_mode(mode).elimination and (
                    lobby.started[mode]
                        and len(match_player_ids) >= get_game_mode(mode).min_players
                        and len(alive_ids) == 1
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
            pending_skill_events = [
                event for event in events["spectator_skill_events"]
                if event["event_id"] > last_sent_skill_event_ids[mode]
            ]
            if pending_skill_events:
                last_sent_skill_event_ids[mode] = pending_skill_events[-1]["event_id"]
            for snapshot_player_id, player in snapshot.items():
                player["bullets"] = list(pending_bullets)
                player["flagdown_skill_rewards"] = (
                    list(player.get("flagdown_skill_rewards", []))
                    if snapshot_player_id == player_id
                    else []
                )
                player["spectator_skill_events"] = list(pending_skill_events)
                player["linked_clones"] = serialize_linked_clones(
                    events["linked_clones"], now_monotonic
                )
                player["active_mines"] = serialize_mines(events, now_monotonic)
                player["mine_blast_events"] = list(events["mine_blast_events"])
                player["mine_ack_id"] = (
                    player.get("mine_ack_id", 0)
                    if snapshot_player_id == player_id
                    else 0
                )
                player["destroyed_treasures"] = list(events["destroyed_treasures"])
                player["destroyed_furniture"] = list(events["destroyed_furniture"])
                player["rune_alerts"] = [
                    (alert[0], alert[1], max(0, round((alert[2] - now_monotonic) * 1000)))
                    for alert in events["rune_alerts"]
                ]
                player["winner_id"] = winner_ids[0] if winner_ids and len(winner_ids) == 1 else None
                player["winner_ids"] = list(winner_ids or [])
                player["match_draw"] = (
                    mode == GAME_MODE_FLAGDOWN
                    and mode in completed_match_winner_ids
                    and not winner_ids
                )
                player["kill_scores"] = dict(score_snapshot)
                player["kill_count"] = score_snapshot.get(snapshot_player_id, 0)
                player["match_elapsed_ms"] = lobby_state.get("elapsed_ms", 0)
                player["flagdown_remaining_ms"] = max(
                    0,
                    FLAGDOWN_DURATION_MS - lobby_state.get("elapsed_ms", 0),
                )
                player["team_id"] = lobby.team_for(snapshot_player_id)
                player["team_spawn_index"] = lobby.team_spawn_index(snapshot_player_id)
                player["flagdown_progress"] = dict(events["flagdown_progress"])
                respawn_at = player.get("deathmatch_respawn_at")
                player["respawn_ms_remaining"] = (
                    max(0, round((respawn_at - now_monotonic) * 1000))
                    if respawn_at is not None else 0
                )
                player["zone_elapsed_ms"] = lobby_state.get("elapsed_ms", 0)
                player["kill_events"] = list(events["kill_events"][-12:])
                player["damage_events"] = list(events["damage_events"][-32:])
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
                player["weather"] = lobby_state.get("weather")
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


def get_leaderboard_snapshot():
    with player_lock:
        game_modes = get_game_modes()
        started_modes = {
            mode for mode, started in lobby.started.items() if started
        }
        active_player_ids = {
            definition.mode_id: lobby.active_player_ids(definition.mode_id)
            for definition in game_modes
            if definition.mode_id in started_modes
        }
        return build_leaderboard_snapshot(
            game_modes,
            started_modes,
            active_player_ids,
            players,
            match_events,
        )


print("[서버 켜짐] 클라이언트 연결을 기다리는 중...")

try:
    leaderboard_api = LeaderboardHTTPServer(
        (bind_ip, LEADERBOARD_PORT),
        None,
        get_leaderboard_snapshot,
    )
except OSError as error:
    print(f"[랭킹 API 시작 실패] {bind_ip}:{LEADERBOARD_PORT}: {error}")
else:
    threading.Thread(
        target=leaderboard_api.serve_forever,
        daemon=True,
    ).start()
    print(
        f"[랭킹 API] LAN 전용 읽기 전용 주소: "
        f"http://{bind_ip}:{LEADERBOARD_PORT}/api/leaderboard"
    )

while True:
    conn, addr = server.accept()
    player_id = generate_player_id()
    current_count = update_player_count(1)
    print(f"[접속] 새로운 플레이어 (ID: {player_id})")
    print(f"[카운트] 현재 접속 인원: {current_count}")
    threading.Thread(target=handle_client, args=(conn, player_id), daemon=True).start()
