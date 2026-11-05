import math


def register_mine_placements(
    events,
    player,
    owner_id,
    requests,
    now,
    map_width,
    map_height,
    team_id,
    arm_delay_ms,
    max_count,
):
    if not isinstance(requests, list):
        return player.get("last_mine_request_id", 0)

    last_request_id = player.get("last_mine_request_id", 0)
    mines = events["mines"]
    for request in requests[:max_count]:
        if not isinstance(request, dict):
            continue
        request_id = request.get("request_id")
        if (
            not isinstance(request_id, int)
            or isinstance(request_id, bool)
            or request_id <= last_request_id
        ):
            continue
        last_request_id = request_id
        player["last_mine_request_id"] = request_id
        try:
            x = float(request["x"])
            y = float(request["y"])
        except (KeyError, TypeError, ValueError):
            continue
        if (
            not math.isfinite(x)
            or not math.isfinite(y)
            or not 0 <= x < map_width
            or not 0 <= y < map_height
        ):
            continue

        owner_mines = [mine for mine in mines if mine["owner_id"] == owner_id]
        if len(owner_mines) >= max_count:
            oldest_mine = owner_mines[0]
            mines.remove(oldest_mine)

        mine_id = events["next_mine_id"]
        events["next_mine_id"] += 1
        mines.append({
            "mine_id": mine_id,
            "owner_id": owner_id,
            "team_id": team_id,
            "x": x,
            "y": y,
            "armed_at": now + arm_delay_ms / 1000,
            "detonates_at": None,
        })
    return player.get("last_mine_request_id", 0)


def advance_mines(
    events,
    players,
    active_player_ids,
    team_for,
    mode,
    now,
    trigger_radius,
    blast_radius,
    trigger_delay_ms,
    damage,
):
    active_player_ids = set(active_player_ids)
    hits = []
    live_players = [
        (player_id, players[player_id])
        for player_id in active_player_ids
        if player_id in players and players[player_id].get("hp", 0) > 0
    ]
    for mine in tuple(events["mines"]):
        if mine["owner_id"] not in active_player_ids or mine["owner_id"] not in players:
            events["mines"].remove(mine)
            continue
        if mine["detonates_at"] is None:
            if now < mine["armed_at"]:
                continue
            for target_id, target in live_players:
                if target_id == mine["owner_id"]:
                    continue
                if mode == "flagdown" and team_for(target_id) == mine["team_id"]:
                    continue
                target_x = target["posX"] + 36
                target_y = target["posY"] + 36
                if math.hypot(target_x - mine["x"], target_y - mine["y"]) <= trigger_radius:
                    mine["detonates_at"] = now + trigger_delay_ms / 1000
                    mine["triggered_at"] = now
                    break
        if mine["detonates_at"] is None or now < mine["detonates_at"]:
            continue

        events["mine_blast_events"].append({
            "mine_id": mine["mine_id"],
            "owner_id": mine["owner_id"],
            "x": mine["x"],
            "y": mine["y"],
            "radius": blast_radius,
        })
        for target_id, target in live_players:
            if target_id == mine["owner_id"]:
                continue
            if mode == "flagdown" and team_for(target_id) == mine["team_id"]:
                continue
            target_x = target["posX"] + 36
            target_y = target["posY"] + 36
            if math.hypot(target_x - mine["x"], target_y - mine["y"]) > blast_radius:
                continue
            auth_key = (mine["mine_id"], target_id)
            events["mine_hit_authorizations"][auth_key] = mine["owner_id"]
            hits.append({
                "target_id": target_id,
                "attacker_id": mine["owner_id"],
                "damage": damage,
                "hit_part": "body",
                "skill_source": "지뢰",
                "_mine_authorization_id": mine["mine_id"],
            })
        events["mines"].remove(mine)

    events["mine_blast_events"][:] = events["mine_blast_events"][-64:]
    return hits


def serialize_mines(events, now):
    return [
        {
            "mine_id": mine["mine_id"],
            "owner_id": mine["owner_id"],
            "x": mine["x"],
            "y": mine["y"],
            "armed_in_ms": max(0, round((mine["armed_at"] - now) * 1000)),
            "detonates_in_ms": (
                None
                if mine["detonates_at"] is None
                else max(0, round((mine["detonates_at"] - now) * 1000))
            ),
        }
        for mine in events["mines"]
    ]
