"""관전 상태와 관전자 전용 시각 이벤트를 관리합니다."""

import math

import pygame
from Config import FPS
from Weapon import DEFAULT_WEAPON_ID, WEAPONS


class SpectatorMode:
    def __init__(self):
        self.active = False
        self.selected_player_id = None
        self.dismissed = False
        self.bullets = {}
        self.skill_effects = []
        self.seen_bullet_ids = set()
        self.seen_skill_ids = set()

    def reset(self):
        self.active = False
        self.selected_player_id = None
        self.dismissed = False
        self.bullets.clear()
        self.skill_effects.clear()
        self.seen_bullet_ids.clear()
        self.seen_skill_ids.clear()

    def stop(self):
        self.active = False

    def toggle(self, players, match_result):
        if self.active and match_result == "defeat":
            self.dismissed = True
        self.active = not self.active
        if self.active:
            self.selected_player_id = next(
                (
                    player_id
                    for player_id, info in players.items()
                    if info.get("hp", 0) > 0
                ),
                None,
            )

    def handle_key(self, key, players, match_result):
        alive_players = [
            player_id
            for player_id, info in players.items()
            if info.get("hp", 0) > 0
        ]
        if key in (pygame.K_ESCAPE, pygame.K_TAB):
            if match_result == "defeat":
                self.dismissed = True
            self.active = False
        elif alive_players and key in (pygame.K_LEFT, pygame.K_RIGHT):
            try:
                selected_index = alive_players.index(self.selected_player_id)
            except ValueError:
                selected_index = 0
            direction = -1 if key == pygame.K_LEFT else 1
            self.selected_player_id = alive_players[
                (selected_index + direction) % len(alive_players)
            ]

    def start_after_defeat(self, elapsed, delay_ms, match_completed, players, local_player_id):
        if match_completed or self.dismissed or elapsed < delay_ms:
            return False
        alive_players = [
            player_id
            for player_id, info in players.items()
            if player_id != local_player_id and info.get("hp", 0) > 0
        ]
        self.selected_player_id = alive_players[0] if alive_players else None
        self.active = True
        return True

    def reconcile(self, players, local_player_id):
        if not self.active:
            return
        alive_players = [
            player_id
            for player_id, info in players.items()
            if player_id != local_player_id and info.get("hp", 0) > 0
        ]
        if self.selected_player_id not in alive_players:
            self.selected_player_id = alive_players[0] if alive_players else None

    def update_snapshot(self, players):
        now = pygame.time.get_ticks()
        for owner_id, player_info in players.items():
            for event in player_info.get("bullets", []):
                event_id = event.get("event_id")
                if event_id is None or event_id in self.seen_bullet_ids:
                    continue
                self.seen_bullet_ids.add(event_id)
                weapon_id = event.get("weapon_id", DEFAULT_WEAPON_ID)
                weapon = WEAPONS.get(weapon_id, WEAPONS[DEFAULT_WEAPON_ID])
                angle = math.radians(event.get("angle", 0.0))
                self.bullets[event_id] = {
                    "owner_id": event.get("owner_id", owner_id),
                    "x": event.get("x", 0),
                    "y": event.get("y", 0),
                    "angle": angle,
                    "speed": weapon.bullet_speed,
                    "stun_ms": event.get("stun_ms", 0),
                    "started_at": now,
                    "hold_ms": event.get("hold_ms", 45),
                }
            for event in player_info.get("spectator_skill_events", []):
                event_id = event.get("event_id")
                if event_id is None or event_id in self.seen_skill_ids:
                    continue
                self.seen_skill_ids.add(event_id)
                self.skill_effects.append({**event, "started_at": now})

        self.bullets = {
            event_id: bullet
            for event_id, bullet in self.bullets.items()
            if now - bullet["started_at"] <= 2500
        }
        self.skill_effects = [
            effect
            for effect in self.skill_effects
            if now - effect["started_at"] <= 1400
        ]

    def get_bullet_positions(self):
        now = pygame.time.get_ticks()
        positioned_bullets = []
        for bullet in self.bullets.values():
            elapsed_ms = max(0, now - bullet["started_at"] - bullet["hold_ms"])
            distance = elapsed_ms * FPS / 1000 * bullet["speed"]
            positioned_bullets.append({
                **bullet,
                "x": bullet["x"] + math.cos(bullet["angle"]) * distance,
                "y": bullet["y"] + math.sin(bullet["angle"]) * distance,
            })
        return positioned_bullets

    def get_skill_effects(self):
        now = pygame.time.get_ticks()
        return [
            {**effect, "age_ms": now - effect["started_at"]}
            for effect in self.skill_effects
        ]