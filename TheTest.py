import pygame
from Config import *
from ImageLoad import *
import math
from TileGenerator import *
from Bullet import *
import Tool
import random
import os
import pickle
from PlayerClass import Player
from Tool_Cordinate import *
from SkillAndSlot import *
from Weapon import (
    MELEE_WEAPON_IDS,
    SpecialWeaponCrate,
    WeaponState,
    WEAPONS,
    WEAPON_KEYS,
)
from Effects import ParticleSystem
from MainScreen import MainScreenRenderer
from Settings import RESERVED_KEYS, get_key, key_bindings, save_settings, settings
from PracticeView import PracticeView
from MiniMap import MiniMap
from GameRendering import (
    create_bat_launch,
    get_bat_launch_frame,
    draw_ammo_status,
    draw_health_bar,
    draw_local_aim_ray,
    draw_player_hitboxes,
    draw_damage_numbers,
    draw_supply_drop,
    draw_quick_slot_cooldowns,
    draw_teleport_anchor,
    draw_visibility_geometry,
    draw_ward,
    draw_kill_feed,
    draw_skill_range,
    draw_stun_bolt,
    draw_stun_effect,
)
from GameAudio import load_effect_sound, play_effect_sound, set_effect_volume
from Zone import MagneticZone
from GameModes import get_game_mode, get_game_modes
from WorldEffects import RainWeather, register_weather, world_effects
from Animation import FrameAnimation
from NetworkClient import (
    default_player_name,
    generate_random_player_name,
    network,
    reconnect_to_server,
)

# 클라이언트는 입력과 화면을 조정하고, 경기의 공유 상태는 서버 응답으로 확정합니다.
pygame.init()
pygame.display.set_caption("전설적인 게임")
display = pygame.display.set_mode((ScreenX, ScreenY), 0, 32)
clock = pygame.time.Clock()
ScreenState = "NameInputView"
settings_key_waiting = None
settings_overlay_open = False
settings_dragging = None
spectator_mode = False
spectator_selected_player_id = None
spectator_dismissed = False
match_completed = False
active_world_weather = None
exit_confirm_return_state = "GameView"
selected_game_mode = GAME_MODE_NORMAL
local_match = False
main_weapon_id = DEFAULT_WEAPON_ID
player_name = generate_random_player_name()
# [커스텀 가능] 게임 전체에서 사용할 기본 폰트입니다. 서체와 크기를 여기서 조정합니다.
GuiFont = pygame.font.Font(os.path.join(os.path.dirname(os.path.abspath(__file__)
        ),"Font","HeirofLightRegular.ttf"
            ), 30)
KillFeedFont = pygame.font.Font(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "Font", "HeirofLightRegular.ttf"), 20
)
BannerFont = pygame.font.Font(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "Font", "HeirofLightRegular.ttf"), 54
)
RuneAlertFont = pygame.font.Font(None, 24)
_scaled_surface_cache = {}
HEAL_INVENTORY_PANEL_RECT = pygame.Rect(30, 220, 330, 112)
HEAL_ITEM_RECT = pygame.Rect(42, 236, 68, 68)


def _scale_cached(image, size, smooth=True):
    """애니메이션 자산의 같은 크기 변환을 재사용합니다."""
    key = (id(image), size, smooth)
    scaled = _scaled_surface_cache.get(key)
    if scaled is None:
        scaler = pygame.transform.smoothscale if smooth else pygame.transform.scale
        scaled = scaler(image, size)
        if len(_scaled_surface_cache) >= 96:
            _scaled_surface_cache.clear()
        _scaled_surface_cache[key] = scaled
    return scaled


def _draw_melee_weapon(surface, image, center, angle, zoom):
    display_size = (
        max(1, round(image.get_width() * zoom * 1.3)),
        max(1, round(image.get_height() * zoom * 1.3)),
    )
    scaled_image = _scale_cached(image, display_size)
    flipped_image = pygame.transform.flip(scaled_image, True, False)
    rotated_image = pygame.transform.rotate(flipped_image, -angle)
    forward_offset = 14 * zoom
    radians = math.radians(angle)
    weapon_center = (
        round(center[0] + math.cos(radians) * forward_offset),
        round(center[1] + math.sin(radians) * forward_offset + 10 * zoom),
    )
    surface.blit(rotated_image, rotated_image.get_rect(center=weapon_center))


def get_aim_mouse_position(camera_x=None, camera_y=None):
    """플레이어 화면 중심을 기준으로 감도 배율이 적용된 조준 좌표를 반환합니다."""
    if camera_x is None:
        camera_x = AimCameraPosX
    if camera_y is None:
        camera_y = AimCameraPosY
    mouse_x, mouse_y = pygame.mouse.get_pos()
    player_x, player_y = get_player_screen_center(
        my_player.X,
        my_player.Y,
        IML.Player.get_width(),
        IML.Player.get_height(),
        camera_x,
        camera_y,
        camera_zoom,
    )
    sensitivity = settings["mouse_sensitivity"]
    return (
        round(player_x + (mouse_x - player_x) * sensitivity),
        round(player_y + (mouse_y - player_y) * sensitivity),
    )


def _stun_shake_offset(now, phase=0):
    tick = now * 0.075 + phase
    return (
        round(math.sin(tick * 3.2) * 9),
        round(math.sin(tick * 5.1) * 3),
    )


def _cached_visibility_polygon(key, center_x, center_y, radius, **options):
    if len(key) > 2 and key[0] == "weapon" and key[2] == VISION_CIRCLE:
        snapped_x = round(center_x / 4) * 4
        snapped_y = round(center_y / 4) * 4
    else:
        snapped_x = round(center_x)
        snapped_y = round(center_y)
    cache_key = (key, snapped_x, snapped_y)
    polygon = visibility_polygon_cache.get(cache_key)
    if polygon is None:
        polygon = TileGene.get_visibility_polygon(
            snapped_x,
            snapped_y,
            radius,
            **options,
        )
        if len(visibility_polygon_cache) >= 64:
            visibility_polygon_cache.pop(next(iter(visibility_polygon_cache)))
        visibility_polygon_cache[cache_key] = polygon
    return polygon


def leave_lobby():
    """로비에서 나간 뒤 다음 경기에 사용할 클라이언트 상태를 정리합니다."""
    response = {}
    try:
        network.client.sendall(pickle.dumps({"type": "lobby_leave"}))
        response = pickle.loads(network.client.recv(NETWORK_BUFFER_SIZE))
        if response.get("type") == "match_cancelled":
            network.lobby_status["message"] = "플레이어가 나가 매치가 취소되었습니다."
    except (OSError, EOFError, pickle.PickleError):
        reconnect_to_server()
    if response.get("type") != "match_defeat":
        reset_match_state()
    network.lobby_status = {
        "count": 0,
        "max_players": MAX_PLAYERS,
        "mode": GAME_MODE_NORMAL,
        "started": False,
    }
    network.last_lobby_request_at = 0
    return response


random.seed(network.init_data["seed"])
IML = Imageload()
blade_animation = FrameAnimation(
    IML.GetBladeFrames(),
    max(1, MELEE_ATTACK_DURATION_MS // max(1, len(IML.GetBladeFrames()))),
    loop=False,
)
bat_animation = FrameAnimation(
    IML.GetBatFrames(),
    max(1, MELEE_ATTACK_DURATION_MS // max(1, len(IML.GetBatFrames()))),
    loop=False,
)
main_screen = MainScreenRenderer(display, IML.GetTitles(), GuiFont, (ScreenX, ScreenY))
practice_view = PracticeView(display, GuiFont, ScreenX)
set_ui_assets(IML.SkillWindow, IML.QuickSlot)
set_image_loader(IML)  # SkillAndSlot에 이미지 로더 전달
TileGene = TileGenerator()
# [커스텀 가능] 맵 가로/세로 타일 수입니다. 타일 크기와 곱해 전체 월드 크기가 결정됩니다.
TileGene.generate_map(MAP_WIDTH_TILES, MAP_HEIGHT_TILES, seed_value=network.init_data["seed"])
MiniMapFont = pygame.font.Font(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "Font", "HeirofLightRegular.ttf"),
    18,
)
MiniMapRenderer = MiniMap(TileGene, MINIMAP_SIZE, MINIMAP_MARGIN, MiniMapFont)
register_weather(GAME_MODE_NORMAL, RainWeather)
register_weather(GAME_MODE_DEATHMATCH, RainWeather)
register_weather(GAME_MODE_DEBUG, RainWeather)
MagneticZoneState = MagneticZone(MAP_WIDTH_TILES, MAP_HEIGHT_TILES, TileGene.tile_size)

# [커스텀 가능] HP 프레임의 화면 표시 크기입니다. 원본 비율을 유지해 한 번만 축소합니다.
HpBarFrame = pygame.transform.smoothscale(IML.HpBar, HP_FRAME_SIZE)

# 🕹️ [Player 클래스 인스턴스 생성 - 랜덤 스폰]
p_w = IML.Player.get_width()
p_h = IML.Player.get_height()
WEAPON_PREVIEW_GETTERS = (
    ("pistol", IML.GetPistol),
    ("sniper", IML.GetSniper),
    ("smg", IML.GetGigwan),
    ("shotgun", IML.GetShotGun),
    ("rifle", IML.GetLiple),
)

def get_fixed_spawn_tiles():
    """맵 전역의 안전 지점에서 서로 멀리 떨어진 스폰 좌표를 고릅니다."""
    def is_clear(x, y):
        return all(
            (tile := TileGene.get_tile_at(x + offset_x, y + offset_y)) is not None
            and tile.tile_type == 0
            for offset_y in range(3)
            for offset_x in range(3)
        )

    candidates = [
        (x, y)
        for y in range(SPAWN_MIN_Y, SPAWN_MAX_Y - 2)
        for x in range(SPAWN_MIN_X, SPAWN_MAX_X - 2)
        if is_clear(x, y)
    ]
    selected = []

    center_x, center_y = MAP_WIDTH_TILES // 2, MAP_HEIGHT_TILES // 2
    while candidates and len(selected) < MAX_PLAYERS:
        if not selected:
            choice = min(
                candidates,
                key=lambda point: ((point[0] - center_x) ** 2 + (point[1] - center_y) ** 2, point[1], point[0]),
            )
        else:
            choice = max(
                candidates,
                key=lambda point: (
                    min((point[0] - sx) ** 2 + (point[1] - sy) ** 2 for sx, sy in selected),
                    -((point[0] - center_x) ** 2 + (point[1] - center_y) ** 2),
                    -point[1],
                    -point[0],
                ),
            )
            if min((choice[0] - sx) ** 2 + (choice[1] - sy) ** 2 for sx, sy in selected) < 16:
                break
        selected.append(choice)
        candidates = [
            point for point in candidates
            if (point[0] - choice[0]) ** 2 + (point[1] - choice[1]) ** 2 >= 16
        ]
    return selected


spawn_tiles = get_fixed_spawn_tiles()
match_spawn_index = 0
spawn_tile_x, spawn_tile_y = spawn_tiles[match_spawn_index]
spawn_world_x = spawn_tile_x * TileGene.tile_size
spawn_world_y = spawn_tile_y * TileGene.tile_size

my_player = Player(spawn_world_x, spawn_world_y, (p_w, p_h), IML, TileGene)
my_player.image = IML.Player
print(f"🎮 플레이어가 ({spawn_tile_x}, {spawn_tile_y}) 타일에 스폰되었습니다.")

training_dummy = None
damage_numbers = []
easter_egg_found = False
easter_egg_flash_until = 0


def respawn_training_dummy():
    """연습모드 더미를 플레이어 근처의 이동 가능한 위치에 둡니다."""
    global training_dummy
    center_x, center_y = get_player_world_center(
        my_player.X, my_player.Y, IML.Player.get_width(), IML.Player.get_height()
    )
    candidates = ((220, 0), (-220, 0), (0, 220), (0, -220))
    for offset_x, offset_y in candidates:
        dummy_x = center_x + offset_x - IML.Player.get_width() / 2
        dummy_y = center_y + offset_y - IML.Player.get_height() / 2
        dummy_rect = pygame.Rect(round(dummy_x), round(dummy_y), p_w, p_h)
        if not TileGene.check_collision(dummy_rect):
            training_dummy = Player(dummy_x, dummy_y, (p_w, p_h), IML, TileGene)
            training_dummy.image = IML.Player
            training_dummy.MaxHp = TRAINING_DUMMY_MAX_HP
            training_dummy.Hp = TRAINING_DUMMY_MAX_HP
            training_dummy.respawn_at = 0
            return

# 보내는 데이터 - 멀티플레이 동기화용
# [커스텀 가능] 서버로 보낼 플레이어 동기화 데이터입니다.
send_data = {
    # 플레이어 정보
    "posX": 0,          # 플레이어 X 좌표
    "posY": 0,          # 플레이어 Y 좌표
    "hp": PLAYER_MAX_HP, # 플레이어 체력
    
    # 무기 정보
    "angle": 0.0,       # 무기(총) 각도
    "weapon_id": DEFAULT_WEAPON_ID,
    "magazine_ammo": WEAPONS[DEFAULT_WEAPON_ID].magazine_size,
    "reserve_ammo": WEAPONS[DEFAULT_WEAPON_ID].reserve_ammo,
    "wards": [],
    "destroyed_furniture": [],
    "rune_ping": None,
    "kill_count": 0,
    "revive_token": 0,
    "revive_request": False,
    "revive_armed": False,
    
    # 발사한 총알 정보 (여러 개 가능)
    "bullets": [],      # [{"x": x, "y": y, "angle": angle}, ...]
    "hit_events": [],   # [{"target_id": id, "damage": damage, "hit_part": part}, ...]
    "bush_leaf_requests": [],
}

CameraPosX = 0
CameraPosY = 0
AimCameraPosX = 0
AimCameraPosY = 0
camera_fov = max(1.0, min(CAMERA_FOV, CAMERA_FOV_MAX))
camera_zoom = 1.0 / camera_fov
lerp = 0.05

Weapon_Angle = 0
Weapon_Pos = (0, 0)

running = True
bullets = []
remote_bullets = []
processed_bullet_events = set()
processed_damage_event_ids = set()
processed_kill_event_ids = set()
bat_launch_animations = {}
skill_cooldowns = {}
vision_skill_until = 0
shield_until = 0
haste_until = 0
stealth_until = 0
stealth_token = 0
wards = []
active_rune_tile = None
rune_alerts = []
revive_token = 0
heal_token = 0
pending_heal_amount = 0
debug_mode = False
active_bombs = []
active_explosions = []
knife_attack_until = 0
hurt_flash_started_at = 0
supply_drops = []
pending_supply_spawn_requests = []
pending_supply_collect_ids = set()
processed_supply_collection_ids = set()
pending_bush_leaf_requests = []
processed_bush_leaf_event_ids = set()
bush_leaf_request_token = 0
next_supply_drop_at = pygame.time.get_ticks() + SUPPLY_DROP_INTERVAL_MS
next_unique_supply_drop_at = pygame.time.get_ticks() + UNIQUE_SUPPLY_INTERVAL_MS
announced_unique_supply_ids = set()
unique_supply_notice = ""
unique_supply_notice_until = 0
bush_entered_at = 0
next_bush_leaf_at = 0
pending_treasure_destroys = []
pending_furniture_destroys = []
pending_hit_events = []
screen_shake = 0
server_players = {}
kill_feed = []
match_result = None
result_started_at = 0
lobby_notice = ""
lobby_notice_until = 0
game_start_banner_until = 0
show_hitboxes = True
local_stun_until = 0
zone_elapsed_ms = 0
local_kill_count = 0
match_elapsed_ms = 0
respawn_ms_remaining = 0
particles = ParticleSystem()
last_effect_tick = pygame.time.get_ticks()
# 시야 밖을 검게 덮을 때 재사용하는 투명 레이어입니다.
vision_overlay = pygame.Surface((ScreenX, ScreenY), pygame.SRCALPHA)
base_vision_overlay = pygame.Surface((ScreenX, ScreenY), pygame.SRCALPHA)
result_overlays = {}
result_text_cache = {}
unique_supply_banner_cache = {}
game_start_banner = BannerFont.render("게임 시작!", True, (255, 225, 120))
SUPPLY_COLORS = {
    "heal": (100, 255, 130),
    "haste": (255, 240, 100),
    "shield": (100, 220, 255),
    "skill": (210, 150, 255),
    "special_weapon": (255, 215, 35),
    "flare_ammo": (255, 135, 65),
    "flare_skill": (200, 125, 255),
}
# 픽셀 위치와 정확한 방향이 바뀌면 시야 폴리곤을 다시 계산합니다.
visibility_polygon_cache = {}
mouse_fire_hold = False
aim_lock_until = 0
aim_locked_pos = None
weapon_fire_until = 0
weapon_smoke_until = 0
preserve_magazine_after_chest = False
teleport_anchor = None
teleport_anchor_expires_at = 0
teleport_placements_remaining = TELEPORT_MAX_PLACEMENTS
third_weapon_id = "flaregun"
special_weapon_crate = SpecialWeaponCrate()


def is_hidden_player(player_info):
    """사망 또는 서버가 숨김 처리한 플레이어를 판별합니다."""
    return player_info.get("hidden", False) or player_info.get("hp", 1) <= 0

def spawn_supply_drop(now):
    """매치 호스트가 고른 위치와 보상을 서버에 보급품 생성 요청으로 보냅니다."""
    if not server_players or min(server_players, key=str) != str(network.player_id):
        return
    if random.random() > SUPPLY_DROP_CHANCE:
        return
    drop_count = min(
        SUPPLY_DROP_BATCH_COUNT,
        SUPPLY_DROP_MAX - len(supply_drops) - len(pending_supply_spawn_requests),
    )
    if drop_count <= 0:
        return
    # 벽이나 집 안에 생성되면 플레이어가 접근할 수 없으므로
    # TileGenerator가 찾은 이동 가능한 타일의 중앙에 배치합니다.
    for _ in range(drop_count):
        spawn_tile = TileGene.find_safe_spawn(
            2,
            TileGene.map_width - 3,
            2,
            TileGene.map_height - 3,
            rng=random.SystemRandom(),
        )
        if not spawn_tile:
            break
        tile_x, tile_y = spawn_tile
        pending_supply_spawn_requests.append({
            "x": (tile_x + 0.5) * TileGene.tile_size,
            "y": (tile_y + 0.5) * TileGene.tile_size,
            "type": random.choice(SUPPLY_REWARD_TYPES),
            "warning_ms": SUPPLY_DROP_WARNING_MS,
            "lifetime_ms": SUPPLY_DROP_LIFETIME_MS,
        })


def spawn_unique_supply_drop(now):
    """주기적으로 유니크 보급품의 안전한 위치를 5초 전에 서버에 알립니다."""
    if not server_players or min(server_players, key=str) != str(network.player_id):
        return False
    spawn_tile = TileGene.find_safe_spawn(
        2,
        TileGene.map_width - 3,
        2,
        TileGene.map_height - 3,
        rng=random.SystemRandom(),
    )
    if not spawn_tile:
        raise RuntimeError("유니크 보급품을 배치할 안전한 위치를 찾지 못했습니다.")
    tile_x, tile_y = spawn_tile
    pending_supply_spawn_requests.append({
        "x": (tile_x + 0.5) * TileGene.tile_size,
        "y": (tile_y + 0.5) * TileGene.tile_size,
        "type": "special_weapon",
        "warning_ms": UNIQUE_SUPPLY_WARNING_MS,
        "lifetime_ms": UNIQUE_SUPPLY_WARNING_MS + SUPPLY_DROP_LIFETIME_MS,
    })
    return True


def get_unique_supply_countdown(now):
    """가장 가까운 유니크 보급의 경고 또는 다음 주기까지 남은 초를 계산합니다."""
    warning_drops = [
        supply for supply in supply_drops
        if supply.get("type") == "special_weapon" and now < supply["warning_until"]
    ]
    if warning_drops:
        remaining_ms = min(supply["warning_until"] - now for supply in warning_drops)
    else:
        remaining_ms = max(0, next_unique_supply_drop_at - now)
    return max(0, (round(remaining_ms) + 999) // 1000)


def launch_flare_supplies(center_x, center_y, now):
    """플레어 발사 지점 주변에 떨어질 보급품 세 개를 서버에 요청합니다."""
    del now
    offsets = (
        (TileGene.tile_size * 3, 0),
        (-round(TileGene.tile_size * 1.5), round(TileGene.tile_size * 2.6)),
        (-round(TileGene.tile_size * 1.5), -round(TileGene.tile_size * 2.6)),
    )
    placed_rects = []
    for index, (offset_x, offset_y) in enumerate(offsets):
        desired_x = center_x + offset_x
        desired_y = center_y + offset_y
        candidates = [(desired_x, desired_y)]
        for ring in range(1, 7):
            radius = ring * TileGene.tile_size // 2
            candidates.extend(
                (
                    desired_x + round(math.cos(angle) * radius),
                    desired_y + round(math.sin(angle) * radius),
                )
                for angle in (
                    0, math.pi / 4, math.pi / 2, 3 * math.pi / 4,
                    math.pi, 5 * math.pi / 4, 3 * math.pi / 2, 7 * math.pi / 4,
                )
            )
        drop_position = None
        for candidate_x, candidate_y in candidates:
            drop_rect = pygame.Rect(
                round(candidate_x - SUPPLY_DROP_RADIUS),
                round(candidate_y - SUPPLY_DROP_RADIUS),
                SUPPLY_DROP_RADIUS * 2,
                SUPPLY_DROP_RADIUS * 2,
            )
            if (
                not TileGene.check_collision(drop_rect)
                and not any(drop_rect.colliderect(rect) for rect in placed_rects)
            ):
                drop_position = (candidate_x, candidate_y)
                placed_rects.append(drop_rect)
                break
        if drop_position is None:
            drop_position = (desired_x, desired_y)
        pending_supply_spawn_requests.append({
            "x": drop_position[0],
            "y": drop_position[1],
            "type": "flare_skill" if index == FLARE_SUPPLY_DROP_COUNT - 1 else "flare_ammo",
            "warning_ms": SUPPLY_DROP_WARNING_MS + index * 250,
            "lifetime_ms": SUPPLY_DROP_LIFETIME_MS,
        })
    particles.ring(
        center_x, center_y, (255, 155, 70),
        count=36, radius=TileGene.tile_size * 2, lifetime=700, size=7,
    )
    particles.ring(
        center_x, center_y, (255, 230, 130),
        count=24, radius=TileGene.tile_size, lifetime=500, size=5,
    )


def apply_supply_reward(reward_type):
    """보급품 종류에 따라 회복, 스킬, 탄약 또는 특수 무기를 지급합니다."""
    # 보급품은 서버에 아이템 자체를 동기화하지 않고,
    # 획득한 클라이언트의 플레이어 상태에만 효과를 적용합니다.
    global healing_item_count, haste_until, shield_until, third_weapon_id
    center_x, center_y = get_player_world_center(
        my_player.X, my_player.Y, IML.Player.get_width(), IML.Player.get_height()
    )
    available = [
        name for name in SKILL_BOOK
        if name not in owned_skills
    ]
    if reward_type == "heal":
        healing_item_count += 1
        message = f"회복 아이템 획득: 보유 {healing_item_count}개"
        color = (100, 255, 130)
   
    elif reward_type == "flare_ammo":
        ammo_weapon_id = (
            main_weapon_id
            if weapon_state.weapon_id in MELEE_WEAPON_IDS
            else weapon_state.weapon_id
        )
        weapon_state.add_reserve_ammo(FLARE_SUPPLY_AMMO_PER_DROP, ammo_weapon_id)
        message = f"탄약 보급품 획득: 예비 탄약 +{FLARE_SUPPLY_AMMO_PER_DROP}"
        color = (255, 135, 65)
    elif reward_type == "flare_skill":
        ammo_weapon_id = (
            main_weapon_id
            if weapon_state.weapon_id in MELEE_WEAPON_IDS
            else weapon_state.weapon_id
        )
        weapon_state.add_reserve_ammo(FLARE_SUPPLY_AMMO_PER_DROP, ammo_weapon_id)
        if available and random.random() >= FLARE_SKILL_HEAL_CHANCE:
            obtained_skill = random.choice(available)
            add_skill_to_inventory(obtained_skill)
            message = (
                f"탄약 +{FLARE_SUPPLY_AMMO_PER_DROP}, "
                f"스킬 [{obtained_skill}] 획득"
            )
            color = (180, 120, 255)
        else:
            healing_item_count += 1
            message = f"탄약 +{FLARE_SUPPLY_AMMO_PER_DROP}, 회복 아이템 획득"
            color = (100, 255, 130)
    elif reward_type == "skill" and available:
        obtained_skill = random.choice(available)
        add_skill_to_inventory(obtained_skill)
        message = f"보급품 획득: [{obtained_skill}] 스킬을 얻었습니다."
        color = (180, 120, 255)
    elif reward_type == "special_weapon":
        weapon_id = special_weapon_crate.open()
        if weapon_id is None:
            raise RuntimeError("특수상자 무기 목록이 비어 있습니다.")
        third_weapon_id = weapon_id
        weapon_state.reset_weapon_ammo(weapon_id)
        message = f"특수 보급품 획득: [{WEAPONS[weapon_id].name}] 3번 슬롯에 저장"
        color = (255, 215, 35)
    else:
        message = "보급품 획득: 이미 모든 스킬을 보유하고 있습니다."
        color = (200, 200, 220)
    particles.emit(center_x, center_y, color, count=24, speed=80, lifetime=600, size=6)
    return message


def use_healing_item():
    global healing_item_count, heal_token, pending_heal_amount, system_message
    if healing_item_count <= 0:
        system_message = "보유한 회복 아이템이 없습니다."
        return
    missing_health = my_player.MaxHp - my_player.Hp - pending_heal_amount
    if missing_health <= 0:
        system_message = "회복 대기량을 포함하면 체력이 가득 찹니다."
        return
    heal_amount = min(SUPPLY_HEAL_AMOUNT, missing_health)
    healing_item_count -= 1
    heal_token += 1
    pending_heal_amount += heal_amount
    system_message = f"회복 아이템 사용: 체력 {heal_amount} 회복"


def draw_healing_inventory(surface):
    if not healing_inventory_open:
        return
    pygame.draw.rect(surface, (20, 28, 32), HEAL_INVENTORY_PANEL_RECT, border_radius=4)
    pygame.draw.rect(surface, (100, 220, 145), HEAL_INVENTORY_PANEL_RECT, 2, border_radius=4)
    pygame.draw.rect(surface, (42, 62, 48), HEAL_ITEM_RECT, border_radius=4)
    pygame.draw.rect(surface, (130, 235, 155), HEAL_ITEM_RECT, 2, border_radius=4)
    pygame.draw.rect(surface, (225, 245, 225), (HEAL_ITEM_RECT.x + 28, HEAL_ITEM_RECT.y + 12, 12, 44))
    pygame.draw.rect(surface, (225, 245, 225), (HEAL_ITEM_RECT.x + 12, HEAL_ITEM_RECT.y + 28, 44, 12))
    title = GuiFont.render("회복 아이템", True, (225, 245, 225))
    count = GuiFont.render(f"x {healing_item_count}", True, (150, 255, 170))
    hint = GuiFont.render("클릭 또는 H 사용", True, (190, 205, 195))
    surface.blit(title, (HEAL_ITEM_RECT.right + 12, HEAL_ITEM_RECT.y - 2))
    surface.blit(count, (HEAL_ITEM_RECT.right + 12, HEAL_ITEM_RECT.y + 28))
    surface.blit(hint, (HEAL_ITEM_RECT.right + 12, HEAL_ITEM_RECT.y + 54))


def collect_treasure(tile_position, from_bullet=False):
    global preserve_magazine_after_chest, system_message
    if not tile_position:
        return False
    if not TileGene.destroy_treasure(*tile_position):
        return False

    pending_treasure_destroys.append(tile_position)
    play_effect_sound(chest_sound, "chest_open.wav")
    available = [
        name for name in SKILL_BOOK
        if name not in owned_skills
    ]
    chest_label = "보물상자:" if from_bullet else "보물상자 획득:"
    if random.random() < CHEST_SKILL_REWARD_CHANCE and available:
        obtained_skill = random.choice(available)
        add_skill_to_inventory(obtained_skill)
        system_message = f"{chest_label} [{obtained_skill}] 스킬을 얻었습니다."
    else:
        ammo_weapon_id = (
            main_weapon_id
            if weapon_state.weapon_id in MELEE_WEAPON_IDS
            else weapon_state.weapon_id
        )
        weapon_config = WEAPONS[ammo_weapon_id]
        weapon_state.refill_magazine(ammo_weapon_id)
        weapon_state.add_reserve_ammo(
            weapon_config.magazine_size,
            ammo_weapon_id,
        )
        weapon_state.reloading = False
        preserve_magazine_after_chest = True
        system_message = (
            f"{chest_label} 탄창 회복, 예비 탄약 +{weapon_config.magazine_size}"
        )
    return True


def use_revive_skill():
    """퀵슬롯에 장착된 부활의 차 스킬을 사망 순간 한 번 소모합니다."""
    global revive_token, system_message, screen_shake
    revive_slot = next(
        (slot for slot in quick_slots if slot.assigned_skill == "부활의 차"),
        None,
    )
    if revive_slot is None or "부활의 차" not in owned_skills:
        return False
    owned_skills.remove("부활의 차")
    for slot in quick_slots:
        if slot.assigned_skill == "부활의 차":
            slot.assigned_skill = None
    refresh_skill_inventory()
    revive_token += 1
    send_data["revive_request"] = True
    my_player.Hp = max(1, round(my_player.MaxHp * REVIVE_HP_RATIO))
    particles.emit(
        my_player.X + my_player.rect.width / 2,
        my_player.Y + my_player.rect.height / 2,
        (255, 220, 120),
        count=36,
        speed=110,
        lifetime=900,
        size=6,
    )
    particles.ring(
        my_player.X + my_player.rect.width / 2,
        my_player.Y + my_player.rect.height / 2,
        (255, 245, 180),
        count=48,
        radius=95,
        lifetime=1100,
        size=5,
    )
    particles.ring(
        my_player.X + my_player.rect.width / 2,
        my_player.Y + my_player.rect.height / 2,
        (255, 190, 100),
        count=28,
        radius=52,
        lifetime=700,
        size=4,
    )
    screen_shake = min(SCREEN_SHAKE_MAX, screen_shake + 5)
    system_message = "부활의 차 스킬이 발동했습니다."
    return True


skill_sounds = {
    "폭탄받아라!": load_effect_sound("skill_bomb.wav"),
    "매의 눈": load_effect_sound("skill_vision.wav"),
    "보호막": load_effect_sound("skill_shield.wav"),
    "은신": load_effect_sound("skill_stealth.wav"),
    "텔포": load_effect_sound("skill_teleport.wav")
}
chest_sound = load_effect_sound("chest_open.wav")

# 무기 설정을 기본값으로 사용하고, 스킬이 잠시 시야 모양만 덮어씁니다.
vision_shapes = (VISION_CIRCLE, VISION_CONE, VISION_RECTANGLE, VISION_LINE)
vision_shape_index = 0

inventory_open = False
healing_inventory_open = False
healing_item_count = 0
weapon_state = WeaponState()
vision_shape_override = None


def reset_match_state(regenerate_world=False, independent_world=False, world_seed=None):
    """새 경기에 들어갈 때 이전 경기의 클라이언트 상태를 초기화합니다."""
    global match_result, result_started_at, system_message, revive_token, heal_token, active_rune_tile, last_effect_tick, easter_egg_found, easter_egg_flash_until
    global pending_heal_amount, vision_skill_until, shield_until, haste_until
    global stealth_until, stealth_token, teleport_anchor, teleport_anchor_expires_at
    global teleport_placements_remaining, third_weapon_id, special_weapon_crate
    global training_dummy, preserve_magazine_after_chest
    global local_stun_until, zone_elapsed_ms, next_supply_drop_at
    global CameraPosX, CameraPosY, AimCameraPosX, AimCameraPosY
    global camera_fov, camera_zoom
    global Weapon_Angle, Weapon_Pos, screen_shake, knife_attack_until
    global hurt_flash_started_at
    global bush_entered_at, next_bush_leaf_at
    global weapon_fire_until, weapon_smoke_until, aim_lock_until, aim_locked_pos
    global game_start_banner_until
    global vision_shape_override, vision_shape_index, inventory_open, healing_inventory_open
    global healing_item_count, mouse_fire_hold
    global settings_overlay_open, settings_key_waiting, settings_dragging
    global spectator_mode, spectator_selected_player_id
    global spectator_dismissed
    global match_completed, active_world_weather
    global announced_unique_supply_ids
    global local_kill_count, match_elapsed_ms, respawn_ms_remaining
    global bush_leaf_request_token
    global next_unique_supply_drop_at, unique_supply_notice, unique_supply_notice_until
    global spawn_tiles, spawn_tile_x, spawn_tile_y
    if regenerate_world:
        world_seed = (
            random.SystemRandom().getrandbits(32)
            if independent_world
            else (
                world_seed
                if world_seed is not None
                else network.init_data["seed"]
            )
        )
        TileGene.generate_map(
            MAP_WIDTH_TILES,
            MAP_HEIGHT_TILES,
            seed_value=world_seed,
        )
        spawn_tiles = get_fixed_spawn_tiles()
    for collection in (
        bullets, remote_bullets, kill_feed, active_bombs, active_explosions,
        supply_drops, pending_treasure_destroys, pending_furniture_destroys,
        pending_hit_events, wards, rune_alerts, damage_numbers,
    ):
        collection.clear()
    pending_supply_spawn_requests.clear()
    pending_supply_collect_ids.clear()
    pending_bush_leaf_requests.clear()
    processed_supply_collection_ids.clear()
    processed_bush_leaf_event_ids.clear()
    bush_leaf_request_token = 0
    processed_bullet_events.clear()
    processed_damage_event_ids.clear()
    processed_kill_event_ids.clear()
    bat_launch_animations.clear()
    particles.particles.clear()
    server_players.clear()
    skill_cooldowns.clear()
    clear_selected_skill()
    owned_skills.clear()
    for slot in quick_slots:
        slot.assigned_skill = None
    refresh_skill_inventory()
    revive_token = heal_token = pending_heal_amount = 0
    healing_item_count = 0
    vision_skill_until = shield_until = haste_until = stealth_until = 0
    stealth_token = 0
    active_rune_tile = None
    teleport_anchor = None
    teleport_anchor_expires_at = 0
    teleport_placements_remaining = TELEPORT_MAX_PLACEMENTS
    third_weapon_id = "flaregun"
    special_weapon_crate = SpecialWeaponCrate()
    training_dummy = None
    preserve_magazine_after_chest = False
    local_stun_until = 0
    zone_elapsed_ms = 0
    next_supply_drop_at = pygame.time.get_ticks() + SUPPLY_DROP_INTERVAL_MS
    next_unique_supply_drop_at = pygame.time.get_ticks() + UNIQUE_SUPPLY_INTERVAL_MS
    announced_unique_supply_ids.clear()
    unique_supply_notice = ""
    unique_supply_notice_until = 0
    last_effect_tick = pygame.time.get_ticks()
    match_result = None
    result_started_at = 0
    local_kill_count = 0
    match_elapsed_ms = 0
    respawn_ms_remaining = 0
    send_data["kill_count"] = 0
    game_start_banner_until = 0
    settings_overlay_open = False
    settings_key_waiting = None
    settings_dragging = None
    spectator_mode = False
    spectator_selected_player_id = None
    spectator_dismissed = False
    match_completed = False
    active_world_weather = None
    system_message = ""
    weapon_state.reset(main_weapon_id)
    weapon_state.reset_weapon_ammo("flaregun")
    CameraPosX = CameraPosY = AimCameraPosX = AimCameraPosY = 0
    camera_fov = CAMERA_FOV
    camera_zoom = 1.0 / camera_fov
    Weapon_Angle = 0
    Weapon_Pos = (0, 0)
    screen_shake = 0
    knife_attack_until = 0
    hurt_flash_started_at = 0
    bush_entered_at = 0
    next_bush_leaf_at = 0
    weapon_fire_until = 0
    weapon_smoke_until = 0
    aim_lock_until = 0
    aim_locked_pos = None
    easter_egg_found = False
    easter_egg_flash_until = 0
    vision_shape_index = 0
    vision_shape_override = None
    inventory_open = False
    healing_inventory_open = False
    mouse_fire_hold = False
    visibility_polygon_cache.clear()
    my_player.Hp = my_player.MaxHp
    my_player.is_dashing = False
    spawn_tile_x, spawn_tile_y = spawn_tiles[match_spawn_index % len(spawn_tiles)]
    my_player.X = spawn_tile_x * TileGene.tile_size
    my_player.Y = spawn_tile_y * TileGene.tile_size
    my_player.rect.topleft = (round(my_player.X), round(my_player.Y))
    my_player._update_hitboxes()
    my_player.is_dashing = False
    my_player.dash_duration = PLAYER_DASH_DURATION_MS
    my_player.dash_end_time = 0
    my_player.last_dash_time = -my_player.dash_cooldown
    my_player.normal_speed = PLAYER_NORMAL_SPEED
    my_player.sprint_speed = PLAYER_SPRINT_SPEED
    my_player.dash_speed = PLAYER_DASH_SPEED
    send_data.update({
        "posX": my_player.X,
        "posY": my_player.Y,
        "hp": my_player.MaxHp,
        "angle": 0.0,
        "weapon_id": weapon_state.weapon_id,
        "magazine_ammo": weapon_state.magazine_ammo,
        "reserve_ammo": weapon_state.reserve_ammo,
        "wards": [],
        "destroyed_treasures": [],
        "destroyed_furniture": [],
        "rune_ping": None,
        "revive_token": 0,
        "revive_request": False,
        "revive_armed": False,
        "heal_token": 0,
        "heal_amount": 0,
        "shield_active": False,
        "stealth": False,
        "in_bush": False,
        "stealth_token": 0,
        "bullets": [],
        "hit_events": [],
        "supply_spawn_requests": [],
        "supply_collect_ids": [],
            "bush_leaf_requests": [],
    })

def MainView():
    global running, ScreenState
    for weapon_id, get_preview_image in WEAPON_PREVIEW_GETTERS:
        if weapon_state.weapon_id == weapon_id:
            preview_image = get_preview_image()
            break
    button_rects = main_screen.draw_main(weapon_state.config.name, preview_image)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
            elif event.key == pygame.K_F10:
                start_practice_match()
            elif event.key == pygame.K_SPACE:
                ScreenState = "NameInputView"
            elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6):
                if event.key == pygame.K_6:
                    select_weapon(random.choice(WEAPON_KEYS[:-1]))
                    continue
                select_weapon(dict(zip(
                    (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5),
                    WEAPON_KEYS[:-1],
                ))[event.key])
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if button_rects["name"].collidepoint(event.pos):
                ScreenState = "NameInputView"
                continue
            if button_rects["profile"].collidepoint(event.pos):
                ScreenState = "ModeSelectView"
            elif button_rects["settings"].collidepoint(event.pos):
                ScreenState = "SettingsView"


def SettingsView():
    global running, ScreenState, settings_key_waiting
    buttons = main_screen.draw_settings(settings, key_bindings, settings_key_waiting)

    def update_sensitivity(mouse_x):
        track = buttons["sensitivity"]
        progress = min(1.0, max(0.0, (mouse_x - track.left - 12) / (track.width - 24)))
        settings["mouse_sensitivity"] = round(0.25 + progress * 1.75, 2)

    def update_volume(mouse_x):
        track = buttons["volume"]
        progress = min(1.0, max(0.0, (mouse_x - track.left - 12) / (track.width - 24)))
        settings["sound_volume"] = round(progress, 2)
        set_effect_volume(settings["sound_volume"])

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN and settings_key_waiting:
            if event.key == pygame.K_ESCAPE:
                settings_key_waiting = None
                continue
            if event.key in RESERVED_KEYS:
                continue
            if event.key in key_bindings.values() and key_bindings[settings_key_waiting] != event.key:
                system_message = "이미 다른 기능에 지정된 키입니다."
                continue
            key_bindings[settings_key_waiting] = event.key
            settings_key_waiting = None
            save_settings()
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            ScreenState = "MainView"
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if buttons["back"].collidepoint(event.pos):
                settings_key_waiting = None
                ScreenState = "MainView"
            elif buttons["sensitivity"].collidepoint(event.pos):
                update_sensitivity(event.pos[0])
                save_settings()
            elif buttons["volume"].collidepoint(event.pos):
                update_volume(event.pos[0])
                save_settings()
            elif buttons["owned_only"].collidepoint(event.pos):
                settings["owned_skills_only"] = not settings["owned_skills_only"]
                refresh_skill_inventory()
                save_settings()
            else:
                settings_key_waiting = next(
                    (
                        action
                        for action, rect in buttons["keys"].items()
                        if rect.collidepoint(event.pos)
                    ),
                    None,
                )
        elif event.type == pygame.MOUSEMOTION and pygame.mouse.get_pressed()[0]:
            if buttons["sensitivity"].collidepoint(event.pos):
                update_sensitivity(event.pos[0])
            elif buttons["volume"].collidepoint(event.pos):
                update_volume(event.pos[0])
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            save_settings()


def begin_lobby_join(mode):
    global ScreenState, selected_game_mode, debug_mode, local_match
    selected_game_mode = mode
    debug_mode = mode == GAME_MODE_DEBUG
    local_match = False
    network.lobby_status = {
        "count": 0,
        "max_players": MAX_PLAYERS,
        "mode": mode,
        "started": False,
        "accepted": False,
        "confirmed": False,
    }
    network.last_lobby_request_at = 0
    ScreenState = "LoadingView"


def start_practice_match():
    global ScreenState, selected_game_mode, debug_mode, local_match
    global game_start_banner_until, active_world_weather
    reset_match_state(regenerate_world=True, independent_world=True)
    debug_mode = True
    local_match = True
    selected_game_mode = GAME_MODE_DEBUG
    world_effects.activate(
        GAME_MODE_DEBUG,
        (MAP_WIDTH_TILES * TileGene.tile_size, MAP_HEIGHT_TILES * TileGene.tile_size),
        force=True,
        weather="rain",
    )
    active_world_weather = "rain"
    owned_skills.update(SKILL_BOOK)
    refresh_skill_inventory()
    game_start_banner_until = pygame.time.get_ticks() + 2000
    ScreenState = "PracticeView"


def ModeSelectView():
    global running, ScreenState
    button_rects = main_screen.draw_mode_select()
    if pygame.time.get_ticks() < lobby_notice_until:
        notice = GuiFont.render(lobby_notice, True, (255, 220, 140))
        display.blit(notice, notice.get_rect(center=(ScreenX // 2, ScreenY - 72)))

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                pygame.key.stop_text_input()
                ScreenState = "MainView"
            elif event.key == pygame.K_F10:
                begin_lobby_join(GAME_MODE_NORMAL)
            elif event.key == pygame.K_1:
                begin_lobby_join(GAME_MODE_NORMAL)
            elif event.key == pygame.K_2:
                begin_lobby_join(GAME_MODE_DEBUG)
            elif event.key == pygame.K_3:
                begin_lobby_join(GAME_MODE_DEATHMATCH)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            selected_mode = next(
                (
                    mode.mode_id
                    for mode in get_game_modes()
                    if button_rects[mode.mode_id].collidepoint(event.pos)
                ),
                None,
            )
            if selected_mode == GAME_MODE_DEBUG:
                start_practice_match()
            elif selected_mode is not None:
                begin_lobby_join(selected_mode)
            elif button_rects["back"].collidepoint(event.pos):
                ScreenState = "MainView"


def NameInputView():
    global running, ScreenState, player_name
    pygame.key.start_text_input()
    main_screen.draw_name_input(player_name, default_player_name())
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.TEXTINPUT:
            player_name = (player_name + event.text)[:16]
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                pygame.key.stop_text_input()
                ScreenState = "MainView"
            elif event.key == pygame.K_BACKSPACE:
                player_name = player_name[:-1]
            elif event.key == pygame.K_r:
                player_name = generate_random_player_name()
            elif event.key == pygame.K_RETURN:
                player_name = player_name.strip() or generate_random_player_name()
                pygame.key.stop_text_input()
                ScreenState = "MainView"


def LoadingView():
    global running, ScreenState, game_start_banner_until, debug_mode
    global local_match, selected_game_mode
    global lobby_notice, lobby_notice_until
    global next_unique_supply_drop_at, unique_supply_notice, unique_supply_notice_until
    global match_spawn_index, spawn_tiles, active_world_weather
    debug_mode = selected_game_mode == GAME_MODE_DEBUG
    if debug_mode:
        owned_skills.update(SKILL_BOOK)
        refresh_skill_inventory()
    now = pygame.time.get_ticks()
    if now - network.last_lobby_request_at >= 100:
        try:
            network.client.sendall(pickle.dumps({
                "type": "lobby_join",
                "mode": selected_game_mode,
                "debug_enabled": debug_mode,
                "name": player_name.strip() or default_player_name(),
                "spawn_tiles": spawn_tiles if selected_game_mode == GAME_MODE_DEATHMATCH else [],
            }))
            response = pickle.loads(network.client.recv(4096))
            if response.get("type") == "lobby_status":
                network.lobby_status = response
                match_seed = response.get("world_seed")
                if (
                    response.get("accepted")
                    and isinstance(match_seed, int)
                    and match_seed != getattr(LoadingView, "_loaded_world_seed", None)
                ):
                    TileGene.generate_map(
                        MAP_WIDTH_TILES,
                        MAP_HEIGHT_TILES,
                        seed_value=match_seed,
                    )
                    spawn_tiles = get_fixed_spawn_tiles()
                    LoadingView._loaded_world_seed = match_seed
                if response.get("accepted"):
                    match_spawn_index = response.get("spawn_index", 0)
            elif response.get("type") == "match_cancelled":
                selected_game_mode = GAME_MODE_NORMAL
                local_match = False
                debug_mode = False
                reset_match_state()
                lobby_notice = "다른 플레이어가 나가 매치가 취소되었습니다."
                lobby_notice_until = pygame.time.get_ticks() + 5000
                ScreenState = "ModeSelectView"
                return
        except (OSError, EOFError, pickle.PickleError, KeyError):
            reconnect_to_server()
            network.last_lobby_request_at = 0
        network.last_lobby_request_at = now

    main_screen.draw_loading(
        network.lobby_status,
        selected_game_mode,
        MAX_PLAYERS,
    )

    if network.lobby_status.get("started") and network.lobby_status.get("accepted", True):
        match_seed = network.lobby_status.get("world_seed")
        reset_match_state(regenerate_world=True, world_seed=match_seed)
        world_effects.activate(
            selected_game_mode,
            (MAP_WIDTH_TILES * TileGene.tile_size, MAP_HEIGHT_TILES * TileGene.tile_size),
            force=True,
            weather=network.lobby_status.get("weather"),
        )
        active_world_weather = network.lobby_status.get("weather")
        if debug_mode:
            owned_skills.update(SKILL_BOOK)
            refresh_skill_inventory()
        game_start_banner_until = pygame.time.get_ticks() + 2000
        ScreenState = "GameView"
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                leave_lobby()
                ScreenState = "ModeSelectView"
            elif event.key == pygame.K_SPACE and not network.lobby_status.get("started"):
                network.client.sendall(pickle.dumps({
                    "type": "lobby_ready",
                    "ready": not network.lobby_status.get("confirmed", False),
                }))
                response = pickle.loads(network.client.recv(NETWORK_BUFFER_SIZE))
                if response.get("type") == "lobby_status":
                    network.lobby_status = response


def show_victory():
    """승리 결과를 기록하고 승리 화면으로 전환합니다."""
    global match_result, result_started_at, ScreenState
    global match_completed, spectator_mode
    match_completed = True
    spectator_mode = False
    if match_result != "victory":
        match_result = "victory"
        result_started_at = pygame.time.get_ticks()
    ScreenState = "Victory"


def show_defeat():
    """패배 결과를 기록하고 패배 화면으로 전환합니다."""
    global match_result, result_started_at, ScreenState, spectator_mode
    if match_completed:
        spectator_mode = False
    if match_result != "defeat":
        match_result = "defeat"
        result_started_at = pygame.time.get_ticks()
    ScreenState = "GameOver"


def GameOverView():
    global result_started_at, spectator_mode, spectator_selected_player_id
    global ScreenState
    if not result_started_at:
        result_started_at = pygame.time.get_ticks()
    elapsed = pygame.time.get_ticks() - result_started_at
    _draw_result_screen("패배", (220, 50, 50), elapsed)

    for event in pygame.event.get():
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                requeue_after_match()
            elif event.key == pygame.K_ESCAPE:
                request_game_exit()

    if (
        not match_completed
        and not spectator_dismissed
        and elapsed >= DEFEAT_SPECTATOR_DELAY_MS
    ):
        alive_players = [
            player_id
            for player_id, info in server_players.items()
            if player_id != network.player_id and info.get("hp", 0) > 0
        ]
        spectator_selected_player_id = alive_players[0] if alive_players else None
        spectator_mode = True
        ScreenState = "GameView"


def VictoryView():
    global result_started_at
    if not result_started_at:
        result_started_at = pygame.time.get_ticks()
    _draw_result_screen("승리", (255, 220, 80), pygame.time.get_ticks() - result_started_at)

    for event in pygame.event.get():
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                requeue_after_match()
            elif event.key == pygame.K_ESCAPE:
                request_game_exit()


def ExitConfirmView():
    global running, ScreenState
    display.fill((8, 12, 20))
    title = GuiFont.render("정말 나가시겠습니까?", True, (245, 245, 235))
    display.blit(title, title.get_rect(center=(ScreenX // 2, ScreenY // 2 - 70)))
    yes_rect = pygame.Rect(0, 0, 180, 64)
    no_rect = pygame.Rect(0, 0, 180, 64)
    yes_rect.center = (ScreenX // 2 - 105, ScreenY // 2 + 35)
    no_rect.center = (ScreenX // 2 + 105, ScreenY // 2 + 35)
    for rect, label, color in (
        (yes_rect, "나가기", (205, 74, 74)),
        (no_rect, "계속하기", (50, 130, 110)),
    ):
        pygame.draw.rect(display, color, rect, border_radius=6)
        pygame.draw.rect(display, (235, 235, 225), rect, 2, border_radius=6)
        text = GuiFont.render(label, True, (255, 255, 255))
        display.blit(text, text.get_rect(center=rect.center))

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_y, pygame.K_RETURN, pygame.K_SPACE):
                leave_game_to_main()
            elif event.key in (pygame.K_n, pygame.K_ESCAPE):
                ScreenState = exit_confirm_return_state
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if yes_rect.collidepoint(event.pos):
                leave_game_to_main()
            elif no_rect.collidepoint(event.pos):
                ScreenState = exit_confirm_return_state


def _draw_result_screen(title_text, color, elapsed):
    pulse = 1.0 + 0.06 * math.sin(elapsed * 0.006)
    fade = min(210, 80 + elapsed // 8)
    overlay = result_overlays.get(color)
    if overlay is None:
        overlay = pygame.Surface((ScreenX, ScreenY), pygame.SRCALPHA)
        result_overlays[color] = overlay
    overlay.fill((*color, fade))
    display.blit(overlay, (0, 0))
    pygame.draw.circle(
        display,
        (*color, 80),
        (ScreenX // 2, ScreenY // 2 - 50),
        max(40, round(150 * pulse)),
        5,
    )
    title = result_text_cache.get(title_text)
    if title is None:
        title = GuiFont.render(title_text, True, (255, 255, 255))
        result_text_cache[title_text] = title
    title = pygame.transform.smoothscale(
        title,
        (max(1, round(title.get_width() * pulse)), max(1, round(title.get_height() * pulse))),
    )
    display.blit(title, title.get_rect(center=(ScreenX // 2, ScreenY // 2 - 60)))
    is_deathmatch_result = selected_game_mode == GAME_MODE_DEATHMATCH
    if is_deathmatch_result:
        score_table = next(
            (info.get("kill_scores", {}) for info in server_players.values() if info.get("kill_scores") is not None),
            {},
        )
        rows = sorted(
            (
                (player_id, int(score_table.get(player_id, info.get("kill_count", 0))), info.get("name", "플레이어"))
                for player_id, info in server_players.items()
            ),
            key=lambda row: (-row[1], str(row[0])),
        )
        winner_ids = next(
            (info.get("winner_ids", []) for info in server_players.values() if info.get("winner_ids")),
            [],
        )
        table_left = ScreenX // 2 - 310
        header_y = ScreenY // 2 + 16
        for label, x in (("순위", table_left + 34), ("닉네임", table_left + 150), ("킬", table_left + 545)):
            header = KillFeedFont.render(label, True, (255, 235, 160))
            display.blit(header, (x, header_y - header.get_height() // 2))
        previous_score = None
        displayed_rank = 0
        for index, (player_id, score, name) in enumerate(rows[:MAX_PLAYERS]):
            if score != previous_score:
                displayed_rank = index + 1
                previous_score = score
            row_y = ScreenY // 2 + 48 + index * 31
            row_rect = pygame.Rect(table_left, row_y - 13, 620, 28)
            local_row = str(player_id) == str(network.player_id)
            winner_row = str(player_id) in {str(winner_id) for winner_id in winner_ids}
            row_color = (
                (90, 70, 25, 210) if local_row
                else (20, 40, 36, 170) if winner_row
                else (12, 20, 28, 135)
            )
            row_surface = pygame.Surface(row_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(row_surface, row_color, row_surface.get_rect(), border_radius=4)
            display.blit(row_surface, row_rect)
            text_color = (255, 245, 190) if local_row or winner_row else (245, 245, 245)
            rank_text = KillFeedFont.render(f"{displayed_rank:>2}", True, text_color)
            name_text = KillFeedFont.render(str(name), True, text_color)
            score_text = KillFeedFont.render(str(score), True, text_color)
            display.blit(rank_text, (row_rect.left + 34, row_y - rank_text.get_height() // 2))
            display.blit(name_text, (row_rect.left + 150, row_y - name_text.get_height() // 2))
            display.blit(score_text, (row_rect.right - 75, row_y - score_text.get_height() // 2))

    guide_text = "Space: 다시 대기열 참가   ESC: 메인 메뉴"
    guide = result_text_cache.get(guide_text)
    if guide is None:
        guide = GuiFont.render(guide_text, True, (255, 255, 255))
        result_text_cache[guide_text] = guide
    guide_y = ScreenY - 36 if is_deathmatch_result else ScreenY // 2 + 70
    display.blit(guide, guide.get_rect(center=(ScreenX // 2, guide_y)))


def handle_quit(_event, _mouse_pos):
    global running
    if ScreenState == "GameView" and not local_match:
        request_game_exit()
        return
    running = False


def break_stealth_on_attack():
    global stealth_until
    if stealth_until > pygame.time.get_ticks():
        stealth_until = 0


def _finish_teleport_cycle(now):
    global teleport_placements_remaining
    skill_cooldowns["텔포"] = now + TELEPORT_COOLDOWN_MS
    teleport_placements_remaining = 0


def activate_quick_slot(key, reinstall=False):
    global system_message, vision_shape_override, vision_skill_until, shield_until, stealth_until, stealth_token, teleport_anchor, teleport_anchor_expires_at, teleport_placements_remaining, screen_shake
    slot_actions = {get_key(f"slot_{name.lower()}"): name for name in ("Q", "E", "T")}
    slot_name = slot_actions.get(key)
    slot = next((slot for slot in quick_slots if slot.key_name == slot_name), None)
    key_name = slot_name or pygame.key.name(key).upper()
    if not slot or not slot.assigned_skill:
        system_message = f"[{key_name}] 슬롯이 비어있습니다."
        return

    skill_name = slot.assigned_skill
    now = pygame.time.get_ticks()
    if skill_name == "부활의 차":
        if (
            selected_game_mode == GAME_MODE_DEATHMATCH
            and not local_match
        ):
            if now < skill_cooldowns.get(skill_name, 0):
                remain = (skill_cooldowns[skill_name] - now) / 1000
                system_message = f"부활의 차 재사용 대기: {remain:.1f}초"
                return
            center_x, center_y = get_player_world_center(
                my_player.X, my_player.Y, IML.Player.get_width(), IML.Player.get_height()
            )
            target_x, target_y = screen_to_world(
                *get_aim_mouse_position(AimCameraPosX, AimCameraPosY),
                AimCameraPosX, AimCameraPosY, camera_zoom,
            )
            angle = math.atan2(target_y - center_y, target_x - center_x)
            soul_bolt = Bullet(
                6,
                damage=REVIVE_ATTACK_DAMAGE,
                owner_id=network.player_id,
                weapon_id="pistol",
            )
            soul_bolt.launch(
                center_x,
                center_y,
                center_x + math.cos(angle) * BULLET_TARGET_DISTANCE,
                center_y + math.sin(angle) * BULLET_TARGET_DISTANCE,
                speed=WEAPONS["pistol"].bullet_speed,
            )
            soul_bolt.just_fired = True
            bullets.append(soul_bolt)
            skill_cooldowns[skill_name] = now + REVIVE_ATTACK_COOLDOWN_MS
            break_stealth_on_attack()
            particles.emit(
                center_x + math.cos(angle) * 38,
                center_y + math.sin(angle) * 38,
                (255, 220, 120),
                count=28,
                speed=125,
                lifetime=650,
                size=6,
            )
            particles.ring(center_x, center_y, (255, 235, 155), count=26, radius=48, lifetime=500, size=4)
            system_message = f"영혼 탄환 발사! {REVIVE_ATTACK_DAMAGE} 피해 · 10초 쿨다운"
            return
        system_message = "부활의 차는 장착 중 사망하면 자동 발동합니다."
        return
    deathmatch_teleport = (
        skill_name == "텔포"
        and selected_game_mode == GAME_MODE_DEATHMATCH
        and not local_match
    )
    if (
        skill_name == "텔포"
        and not deathmatch_teleport
        and teleport_anchor is None
        and now >= skill_cooldowns.get(skill_name, 0)
        and teleport_placements_remaining == 0
    ):
        teleport_placements_remaining = TELEPORT_MAX_PLACEMENTS
    if (
        skill_name == "텔포"
        and (deathmatch_teleport or teleport_anchor is None)
        and now < skill_cooldowns.get(skill_name, 0)
    ):
        remain = (skill_cooldowns[skill_name] - now) / 1000
        system_message = f"텔포 재사용 대기: {remain:.1f}초"
        return
    if (
        skill_name != "텔포"
        and now < skill_cooldowns.get(skill_name, 0)
    ):
        remain = (skill_cooldowns[skill_name] - now) / 1000
        system_message = f"{skill_name} 재사용 대기: {remain:.1f}초"
        return

    if skill_name != "텔포":
        cooldown = STEALTH_COOLDOWN_MS if skill_name == "은신" else SKILL_COOLDOWN_MS
        skill_cooldowns[skill_name] = now + cooldown
    play_effect_sound(skill_sounds.get(skill_name), skill_name)
    if skill_name == "기절탄":
        if not fire_stun_bullet():
            skill_cooldowns.pop(skill_name, None)
        return
    if skill_name == "폭탄받아라!":
        target_x, target_y = screen_to_world(*get_aim_mouse_position(CameraPosX, CameraPosY), CameraPosX, CameraPosY, camera_zoom)
        player_x, player_y = get_player_world_center(
            my_player.X, my_player.Y, IML.Player.get_width(), IML.Player.get_height()
        )
        vision = weapon_state.config
        weapon_visible = TileGene.is_point_visible_from(
            player_x,
            player_y,
            target_x,
            target_y,
            vision.vision_radius,
            vision_shape=vision_shape_override or vision.vision_shape,
            direction_angle=Weapon_Angle,
            fov_angle=vision.vision_fov,
            vision_width=vision.vision_width,
        )
        base_visible = TileGene.is_point_visible_from(
            player_x, player_y, target_x, target_y,
            PLAYER_BASE_VISION_RADIUS,
            vision_shape=VISION_CIRCLE,
        )
        ward_visible = any(
            TileGene.is_point_visible_from(
                ward_x, ward_y, target_x, target_y, WARD_VISION_RADIUS,
                vision_shape=VISION_CIRCLE,
            )
            for ward_x, ward_y in wards
        )
        if not (weapon_visible or base_visible or ward_visible):
            skill_cooldowns.pop(skill_name, None)
            system_message = "밝은 시야 안에만 폭탄을 던질 수 있습니다."
            return
        break_stealth_on_attack()
        active_bombs.append({"x": target_x, "y": target_y, "explode_at": now + BOMB_DELAY_MS})
        particles.emit(target_x, target_y, (255, 190, 40), count=18, speed=55, lifetime=500, size=6)
        particles.ring(target_x, target_y, (255, 220, 80), radius=35, lifetime=450)
        system_message = "폭탄을 설치했습니다."
    elif skill_name == "매의 눈":
        vision_shape_override = VISION_CIRCLE
        vision_skill_until = now + VISION_DURATION_MS
        vision_center_x, vision_center_y = get_player_world_center(
            my_player.X, my_player.Y, IML.Player.get_width(), IML.Player.get_height()
        )
        particles.ring(
            vision_center_x,
            vision_center_y,
            (120, 220, 255), count=40, radius=140, lifetime=900, size=5,
        )
        particles.ring(
            vision_center_x,
            vision_center_y,
            (190, 245, 255), count=28, radius=80, lifetime=700, size=4,
        )
        particles.emit(
            vision_center_x,
            vision_center_y,
            (150, 225, 255),
            count=26,
            speed=95,
            lifetime=1000,
            size=4,
            gravity=-30,
        )
        system_message = "3초 동안 최대 사거리의 360도 시야를 확보합니다."
    elif skill_name == "보호막":
        shield_until = now + SHIELD_DURATION_MS
        my_player.is_dashing = False
        my_player.is_moving = False
        particles.ring(
            my_player.X + my_player.rect.width / 2,
            my_player.Y + my_player.rect.height / 2,
            (100, 220, 255), count=28, radius=55, lifetime=700, size=5,
        )
        particles.ring(
            my_player.X + my_player.rect.width / 2,
            my_player.Y + my_player.rect.height / 2,
            (190, 250, 255), count=36, radius=78, lifetime=900, size=4,
        )
        particles.emit(
            my_player.X + my_player.rect.width / 2,
            my_player.Y + my_player.rect.height / 2,
            (100, 220, 255),
            count=20,
            speed=75,
            lifetime=800,
            size=4,
        )
        system_message = "3초 동안 피해를 받지 않지만 움직일 수 없습니다."
    elif skill_name == "은신":
        stealth_until = now + STEALTH_DURATION_MS
        stealth_token += 1
        particles.emit(
            my_player.X + my_player.rect.width / 2,
            my_player.Y + my_player.rect.height / 2,
            (180, 190, 255),
            count=24,
            speed=70,
            lifetime=650,
            size=5,
        )
        particles.ring(
            my_player.X + my_player.rect.width / 2,
            my_player.Y + my_player.rect.height / 2,
            (210, 220, 255), count=32, radius=72, lifetime=800, size=4,
        )
        particles.emit(
            my_player.X + my_player.rect.width / 2,
            my_player.Y + my_player.rect.height / 2,
            (225, 235, 255), count=18, speed=115, lifetime=900, size=3, gravity=-35,
        )
        particles.ring(
            my_player.X + my_player.rect.width / 2,
            my_player.Y + my_player.rect.height / 2,
            (170, 205, 255), count=44, radius=92, lifetime=950, size=4,
        )
        system_message = "4.5초 동안 적에게 완전히 보이지 않습니다."
    elif skill_name == "와드":
        target_x, target_y = screen_to_world(*get_aim_mouse_position(CameraPosX, CameraPosY), CameraPosX, CameraPosY, camera_zoom)
        target_rect = pygame.Rect(0, 0, 16, 16)
        target_rect.center = (round(target_x), round(target_y))
        if TileGene.check_collision(target_rect):
            skill_cooldowns.pop(skill_name, None)
            system_message = "벽 안에는 와드를 설치할 수 없습니다."
            return
        wards.append((target_x, target_y))
        if len(wards) > WARD_MAX_COUNT:
            wards.pop(0)
        particles.ring(target_x, target_y, (120, 240, 255), count=18, radius=28, lifetime=650, size=4)
        system_message = f"와드를 설치했습니다. 현재 {len(wards)}/{WARD_MAX_COUNT}개"
    elif deathmatch_teleport:
        if now < shield_until:
            system_message = "보호막이 유지되는 동안에는 순간이동할 수 없습니다."
            return
        target_x, target_y = screen_to_world(
            *get_aim_mouse_position(CameraPosX, CameraPosY), CameraPosX, CameraPosY, camera_zoom
        )
        destination = my_player.rect.copy()
        destination.center = (round(target_x), round(target_y))
        # 순간이동 경로는 벽을 무시하고, 착지 지점만 안전한 바닥인지 검사합니다.
        if TileGene.check_collision(destination):
            system_message = "벽 안이나 맵 밖에는 착지할 수 없습니다."
            return
        old_x = my_player.X + my_player.rect.width / 2
        old_y = my_player.Y + my_player.rect.height / 2
        my_player.X = target_x - my_player.rect.width / 2
        my_player.Y = target_y - my_player.rect.height / 2
        my_player.rect.topleft = (round(my_player.X), round(my_player.Y))
        my_player._update_hitboxes()
        particles.emit(
            old_x, old_y, (180, 255, 180),
            count=30, speed=110, lifetime=650, size=5,
        )
        particles.ring(
            old_x, old_y, (180, 255, 180),
            count=22, radius=42, lifetime=500, size=4,
        )
        particles.emit(
            target_x, target_y, (180, 255, 180),
            count=36, speed=120, lifetime=750, size=5,
        )
        particles.ring(
            target_x, target_y, (210, 255, 210),
            count=28, radius=52, lifetime=650, size=4,
        )
        skill_cooldowns["텔포"] = now + TELEPORT_COOLDOWN_MS
        system_message = (
            f"데스매치 순간이동: 지정한 위치로 이동했습니다. "
            f"{TELEPORT_COOLDOWN_MS / 1000:g}초 후 다시 사용할 수 있습니다."
        )
    elif skill_name == "텔포":
        if teleport_anchor is None or reinstall:
            if teleport_placements_remaining <= 0:
                system_message = "텔포 설치 횟수를 모두 사용했습니다."
                return
            target_x, target_y = get_player_world_center(
                my_player.X, my_player.Y, IML.Player.get_width(), IML.Player.get_height()
            )
            target_rect = my_player.rect.copy()
            target_rect.center = (round(target_x), round(target_y))
            if TileGene.check_collision(target_rect):
                system_message = "벽 안에는 텔포석상을 설치할 수 없습니다."
                return
            teleport_anchor = (target_x, target_y)
            teleport_anchor_expires_at = now + TELEPORT_DURATION_MS
            teleport_placements_remaining -= 1
            particles.emit(target_x, target_y, (180, 255, 180), count=30, speed=90, lifetime=700, size=6)
            particles.ring(target_x, target_y, (180, 255, 180), count=20, radius=38, lifetime=900, size=5)
            system_message = (
                f"텔포석상을 설치했습니다. 남은 설치 횟수: {teleport_placements_remaining}"
                + (" (Shift+슬롯키로 재설치)" if teleport_placements_remaining else "")
            )
        else:
            old_x = my_player.X + my_player.rect.width / 2
            old_y = my_player.Y + my_player.rect.height / 2
            my_player.X = teleport_anchor[0] - my_player.rect.width / 2
            my_player.Y = teleport_anchor[1] - my_player.rect.height / 2
            my_player.rect.topleft = (round(my_player.X), round(my_player.Y))
            my_player._update_hitboxes()
            particles.emit(old_x, old_y, (180, 255, 180), count=24, speed=80, lifetime=600, size=5)
            particles.emit(teleport_anchor[0], teleport_anchor[1], (180, 255, 180), count=30, speed=90, lifetime=700, size=6)
            teleport_anchor = None
            teleport_anchor_expires_at = 0
            if teleport_placements_remaining <= 0:
                _finish_teleport_cycle(now)
                cooldown_message = f"{TELEPORT_COOLDOWN_MS / 1000:g}초 후 다시 사용할 수 있습니다."
            else:
                cooldown_message = f"남은 설치 횟수: {teleport_placements_remaining}"
            system_message = f"텔레포트했습니다. {cooldown_message}"
def select_weapon(weapon_id):
    global system_message, vision_shape_override, main_weapon_id
    global weapon_fire_until, weapon_smoke_until, knife_attack_until, screen_shake
    if ScreenState not in ("GameView", "PracticeView"):
        main_weapon_id = weapon_id
    elif not debug_mode and weapon_id not in (main_weapon_id, "knife", third_weapon_id):
        system_message = "게임 중에는 선택한 총과 3번 슬롯 무기만 사용할 수 있습니다."
        return
    if weapon_state.select(weapon_id):
        vision_shape_override = None
        visibility_polygon_cache.clear()
        weapon_fire_until = 0
        weapon_smoke_until = 0
        knife_attack_until = 0
        screen_shake = 0
        system_message = f"무기 변경: {weapon_state.config.name}"


def reload_weapon():
    global system_message
    if weapon_state.is_reloading_now():
        system_message = "이미 재장전 중입니다."
        return
    if weapon_state.config.projectile and weapon_state.magazine_ammo >= weapon_state.config.magazine_size:
        system_message = "탄창이 이미 가득 찼습니다."
        return
    if weapon_state.config.projectile and weapon_state.reserve_ammo <= 0:
        system_message = "예비 탄약이 없습니다."
        return

    if weapon_state.start_reload():
        system_message = f"{weapon_state.config.name} 재장전 중..."
    else:
        system_message = "재장전할 탄환이 없습니다."


def activate_skill_or_reload(key):
    slot_actions = {get_key(f"slot_{name.lower()}"): name for name in ("Q", "E", "T")}
    slot_name = slot_actions.get(key)
    slot = next((slot for slot in quick_slots if slot.key_name == slot_name), None)
    if slot and slot.assigned_skill:
        activate_quick_slot(key)
    else:
        reload_weapon()


def remove_ward_at_cursor():
    """마우스 주변의 자기 와드 하나를 제거합니다."""
    global system_message
    target_x, target_y = screen_to_world(
        *get_aim_mouse_position(CameraPosX, CameraPosY), CameraPosX, CameraPosY, camera_zoom
    )
    max_distance = TileGene.tile_size * 1.5
    nearest_index = None
    nearest_distance = max_distance
    for index, (ward_x, ward_y) in enumerate(wards):
        distance = math.hypot(target_x - ward_x, target_y - ward_y)
        if distance <= nearest_distance:
            nearest_index = index
            nearest_distance = distance
    if nearest_index is None:
        system_message = "마우스 주변에 제거할 와드가 없습니다."
        return
    wards.pop(nearest_index)
    system_message = "와드를 제거했습니다."


def handle_key_event(event, _mouse_pos):
    global inventory_open, debug_mode, system_message, show_hitboxes
    global healing_inventory_open
    if (
        my_player.Hp <= 0
        and selected_game_mode == GAME_MODE_DEATHMATCH
        and event.key != pygame.K_ESCAPE
    ):
        return
    weapon_id = None
    if event.key == pygame.K_1:
        weapon_id = main_weapon_id
    elif event.key == pygame.K_2:
        weapon_id = "knife"
    elif event.key == pygame.K_3 and ScreenState in ("GameView", "PracticeView"):
        if third_weapon_id:
            select_weapon(third_weapon_id)
        else:
            system_message = "노란 특수상자를 열어 3번 무기를 획득하세요."
        return
    elif ScreenState not in ("GameView", "PracticeView"):
        weapon_id = dict(zip(
            (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5),
            WEAPON_KEYS[:-1],
        )).get(event.key)
    if weapon_id:
        select_weapon(weapon_id)
        return

    if event.key == pygame.K_F10:
        if selected_game_mode == GAME_MODE_NORMAL:
            debug_mode = False
            system_message = "일반전에서는 디버그 모드를 사용할 수 없습니다."
            return
        debug_mode = not debug_mode
        if debug_mode:
            owned_skills.update(SKILL_BOOK)
            refresh_skill_inventory()
            system_message = "디버그 모드: 모든 스킬 사용 가능"
        else:
            system_message = "디버그 모드 해제"
        return

    if event.key == pygame.K_F9:
        show_hitboxes = not show_hitboxes
        system_message = f"히트박스 표시: {'켜짐' if show_hitboxes else '꺼짐'}"
        return

    if event.key == get_key("healing_inventory"):
        healing_inventory_open = not healing_inventory_open
        if healing_inventory_open:
            inventory_open = False
            clear_selected_skill()
        return

    slot_key_names = {
        get_key("slot_q"): "Q",
        get_key("slot_e"): "E",
        get_key("slot_t"): "T",
    }
    if inventory_open and event.key in slot_key_names:
        skill_name, assigned = bind_selected_skill(slot_key_names[event.key])
        if skill_name is not None:
            system_message = (
                f"[{skill_name}] 스킬을 [{slot_key_names[event.key]}] 슬롯에 장착했습니다."
                if assigned else f"[{skill_name}]은 이미 다른 퀵슬롯에 장착되어 있습니다."
            )
            return

    key_actions = {
        pygame.K_ESCAPE: lambda _key: request_game_exit(),
        get_key("skill_inventory"): lambda _key: toggle_inventory(),
        get_key("use_healing"): lambda _key: use_healing_item(),
        pygame.K_v: lambda _key: cycle_vision_shape(),
        pygame.K_q: lambda _key: activate_quick_slot(
            _key, reinstall=bool(event.mod & pygame.KMOD_SHIFT)
        ),
        pygame.K_e: lambda _key: activate_quick_slot(
            _key, reinstall=bool(event.mod & pygame.KMOD_SHIFT)
        ),
        pygame.K_t: lambda _key: activate_quick_slot(
            _key, reinstall=bool(event.mod & pygame.KMOD_SHIFT)
        ),
        get_key("reload"): lambda _key: reload_weapon(),
        pygame.K_f: lambda _key: activate_skill_or_reload(_key),
        pygame.K_x: lambda _key: remove_ward_at_cursor(),
    }
    key_actions.get(event.key, activate_quick_slot)(event.key)


def leave_game_to_main():
    """현재 게임과 로비 상태를 정리하고 메인 화면으로 돌아갑니다."""
    global ScreenState, local_match, debug_mode, selected_game_mode
    if not local_match:
        response = leave_lobby()
        if response.get("type") == "match_defeat":
            show_defeat()
            return
    else:
        reset_match_state()
    local_match = False
    debug_mode = False
    selected_game_mode = GAME_MODE_NORMAL
    ScreenState = "MainView"


def return_to_normal_lobby():
    global ScreenState, local_match, debug_mode, selected_game_mode
    leave_lobby()
    local_match = False
    debug_mode = False
    selected_game_mode = GAME_MODE_NORMAL
    network.last_lobby_request_at = 0
    ScreenState = "LoadingView"


def requeue_after_match():
    """경기 상태를 초기화하고 같은 모드의 로비 대기열로 다시 보냅니다."""
    if local_match:
        start_practice_match()
        return
    selected_mode = selected_game_mode
    leave_lobby()
    begin_lobby_join(selected_mode)


def request_game_exit():
    global ScreenState, exit_confirm_return_state
    if local_match:
        leave_game_to_main()
        return
    exit_confirm_return_state = ScreenState
    ScreenState = "ExitConfirmView"


def toggle_inventory():
    global inventory_open, healing_inventory_open
    inventory_open = not inventory_open
    if inventory_open:
        healing_inventory_open = False
    else:
        clear_selected_skill()


def cycle_vision_shape():
    """V 키로 현재 시야 모양을 순서대로 변경합니다."""
    global vision_shape_index, vision_shape_override, system_message
    if ScreenState in ("GameView", "PracticeView") and not debug_mode:
        system_message = "시야 변경은 디버그 모드에서만 사용할 수 있습니다."
        return
    vision_shape_index = (vision_shape_index + 1) % len(vision_shapes)
    vision_shape_override = vision_shapes[vision_shape_index]
    shape_name = vision_shape_override
    system_message = f"시야 모양: {shape_name}" 


def fire_knife():
    """칼과 배트로 근거리 범위 내의 적과 보물상자를 공격합니다."""
    global screen_shake, system_message, knife_attack_until
    config = weapon_state.config
    attack_started_at = pygame.time.get_ticks()
    knife_attack_until = attack_started_at + MELEE_ATTACK_DURATION_MS
    animation = bat_animation if weapon_state.weapon_id == "bat" else blade_animation
    animation.start(attack_started_at)

    center_x, center_y = get_player_world_center(
        my_player.X,
        my_player.Y,
        IML.Player.get_width(),
        IML.Player.get_height(),
    )

    knife_range = MELEE_RANGE

    treasure_rect = pygame.Rect(
        center_x - knife_range,
        center_y - knife_range,
        knife_range * 2,
        knife_range * 2,
    )
    nearby_treasure = TileGene.treasure_at(treasure_rect)
    if nearby_treasure:
        collect_treasure(nearby_treasure)

    attacked_count = 0
    for p_id, p_info in server_players.items():
        if str(p_id) == str(network.player_id) or is_hidden_player(p_info):
            continue

        enemy_center_x = p_info["posX"] + IML.Player.get_width() / 2
        enemy_center_y = p_info["posY"] + IML.Player.get_height() / 2

        distance_squared = (center_x - enemy_center_x) ** 2 + (center_y - enemy_center_y) ** 2
        if distance_squared <= knife_range ** 2:
            attacked_count += 1
            pending_hit_events.append({
                "target_id": p_id,
                "attacker_id": network.player_id,
                "damage": config.damage,
                "hit_part": "body",
                "weapon_id": weapon_state.weapon_id,
            })

    start_x = max(0, int((center_x - knife_range) // TileGene.tile_size))
    end_x = min(TileGene.map_width - 1, int((center_x + knife_range) // TileGene.tile_size))
    start_y = max(0, int((center_y - knife_range) // TileGene.tile_size))
    end_y = min(TileGene.map_height - 1, int((center_y + knife_range) // TileGene.tile_size))
    destroyed_furniture_count = 0
    for tile_y in range(start_y, end_y + 1):
        for tile_x in range(start_x, end_x + 1):
            tile_center = (
                (tile_x + 0.5) * TileGene.tile_size,
                (tile_y + 0.5) * TileGene.tile_size,
            )
            if (center_x - tile_center[0]) ** 2 + (center_y - tile_center[1]) ** 2 > knife_range ** 2:
                continue
            if TileGene.destroy_furniture(tile_x, tile_y, rebuild_surface=False):
                pending_furniture_destroys.append((tile_x, tile_y))
                destroyed_furniture_count += 1
    if destroyed_furniture_count:
        TileGene.refresh_world_surface(pending_furniture_destroys)

    if debug_mode and training_dummy is not None and training_dummy.Hp > 0:
        dummy_center_x = training_dummy.rect.centerx
        dummy_center_y = training_dummy.rect.centery
        if (center_x - dummy_center_x) ** 2 + (center_y - dummy_center_y) ** 2 <= knife_range ** 2:
            previous_hp = training_dummy.Hp
            training_dummy.Hp = max(0, training_dummy.Hp - int(config.damage))
            dealt_damage = previous_hp - training_dummy.Hp
            damage_numbers.append({
                "x": dummy_center_x,
                "y": training_dummy.rect.top,
                "damage": dealt_damage,
                "color": (255, 255, 255),
                "started_at": pygame.time.get_ticks(),
                "lifetime": DAMAGE_TEXT_LIFETIME_MS,
            })
            if training_dummy.Hp <= 0:
                training_dummy.respawn_at = pygame.time.get_ticks() + TRAINING_DUMMY_RESPAWN_MS
            attacked_count += 1

    weapon_state.consume_round()
    screen_shake = min(SCREEN_SHAKE_MAX, screen_shake + MELEE_SHAKE)

    if attacked_count > 0:
        particles.emit(center_x, center_y, (255, 80, 80), count=18, speed=100, lifetime=400, size=5)
        system_message = f"{config.name} 공격! {config.damage} 데미지 × {attacked_count}명"
        if destroyed_furniture_count:
            system_message += f", 가구 {destroyed_furniture_count}개 파괴"
    else:
        system_message = f"{config.name} 휘둘렀습니다. (데미지: {config.damage})"
        if destroyed_furniture_count:
            system_message += f" 가구 {destroyed_furniture_count}개 파괴"


def fire_stun_bullet():
    global system_message
    if not weapon_state.can_fire():
        system_message = "기절탄을 발사할 수 없습니다."
        return False
    break_stealth_on_attack()
    center_x, center_y = get_player_world_center(
        my_player.X, my_player.Y, IML.Player.get_width(), IML.Player.get_height()
    )
    mouse_x, mouse_y = get_aim_mouse_position(AimCameraPosX, AimCameraPosY)
    target_world_x, target_world_y = screen_to_world(
        mouse_x, mouse_y, AimCameraPosX, AimCameraPosY, camera_zoom
    )
    player_screen = get_player_screen_center(
        my_player.X, my_player.Y, IML.Player.get_width(), IML.Player.get_height(),
        CameraPosX, CameraPosY, camera_zoom,
    )
    angle = math.atan2(target_world_y - center_y, target_world_x - center_x)
    bullet = Bullet(4, damage=DEFAULT_BULLET_DAMAGE, owner_id=network.player_id, weapon_id=weapon_state.weapon_id, stun_ms=STUN_DURATION_MS)
    bullet.launch(
        center_x, center_y,
        center_x + math.cos(angle) * BULLET_TARGET_DISTANCE,
        center_y + math.sin(angle) * BULLET_TARGET_DISTANCE,
        speed=weapon_state.config.bullet_speed,
        hold_ms=0,
    )
    bullet.just_fired = True
    bullets.append(bullet)
    muzzle_x = center_x + math.cos(angle) * 38
    muzzle_y = center_y + math.sin(angle) * 38
    particles.emit(
        muzzle_x,
        muzzle_y,
        (110, 225, 255),
        count=28,
        speed=135,
        lifetime=520,
        size=5,
        gravity=-12,
    )
    particles.ring(
        muzzle_x,
        muzzle_y,
        (195, 250, 255),
        count=24,
        radius=42,
        lifetime=480,
        size=4,
    )
    weapon_state.consume_round()
    system_message = "기절탄을 발사했습니다."
    return True


def fire_bullet():
    global system_message, third_weapon_id
    global weapon_fire_until, weapon_smoke_until
    if my_player.Hp <= 0:
        return
    config = weapon_state.config

    if weapon_state.is_reloading_now():
        system_message = "재장전 중입니다."
        return

    if weapon_state.weapon_id == "flaregun":
        if not weapon_state.can_fire():
            system_message = "플레어건은 이미 사용했습니다."
            return
        break_stealth_on_attack()
        target_x, target_y = screen_to_world(
            *get_aim_mouse_position(AimCameraPosX, AimCameraPosY), AimCameraPosX, AimCameraPosY, camera_zoom
        )
        launch_flare_supplies(target_x, target_y, pygame.time.get_ticks())
        weapon_state.consume_round()
        third_weapon_id = None
        animation_started_at = pygame.time.get_ticks()
        weapon_fire_until = animation_started_at + WEAPON_FIRE_ANIMATION_MS
        weapon_smoke_until = animation_started_at + WEAPON_SMOKE_ANIMATION_MS
        particles.emit(
            my_player.X + my_player.rect.width / 2,
            my_player.Y + my_player.rect.height / 2,
            (255, 115, 55),
            count=18,
            speed=95,
            lifetime=500,
            size=6,
        )
        select_weapon(main_weapon_id)
        system_message = "플레어 발사! 지정 위치에 보급품이 떨어집니다."
        return
    
    # 근접 무기는 투사체 발사 대신 공통 공격 처리를 사용합니다.
    if not config.projectile:
        if not weapon_state.can_fire():
            system_message = f"{config.name} 공격은 아직 준비 중입니다."
            return
        break_stealth_on_attack()
        fire_knife()
        return
    
    if not weapon_state.can_fire():
        if config.projectile and weapon_state.magazine_ammo == 0:
            reload_weapon()
        return
    break_stealth_on_attack()

    center_x, center_y = get_player_world_center(
        my_player.X,
        my_player.Y,
        IML.Player.get_width(),
        IML.Player.get_height(),
    )
    current_mouse_pos = get_aim_mouse_position(AimCameraPosX, AimCameraPosY)
    player_screen_center = get_player_screen_center(
        my_player.X,
        my_player.Y,
        IML.Player.get_width(),
        IML.Player.get_height(),
        AimCameraPosX,
        AimCameraPosY,
        camera_zoom,
    )
    target_world_x, target_world_y = screen_to_world(
        current_mouse_pos[0], current_mouse_pos[1], AimCameraPosX, AimCameraPosY, camera_zoom
    )
    base_angle = math.atan2(target_world_y - center_y, target_world_x - center_x)
    muzzle_x = center_x + math.cos(base_angle) * 40
    muzzle_y = center_y + math.sin(base_angle) * 40
    weapon_state.consume_round()
    animation_started_at = pygame.time.get_ticks()
    weapon_fire_until = animation_started_at + WEAPON_FIRE_ANIMATION_MS
    weapon_smoke_until = animation_started_at + WEAPON_SMOKE_ANIMATION_MS
    particles.emit(muzzle_x, muzzle_y, (255, 220, 100), count=10, speed=70, lifetime=220, size=4)

    for _ in range(config.pellets):
        shot_angle = base_angle + math.radians(random.uniform(-config.spread_degrees, config.spread_degrees))
        bullet_size_Up = config.bullet_size
        if weapon_state.weapon_id == "sniper":
            bullet_size_Up = config.bullet_size * 1.5
        else:
            bullet_size_Up = config.bullet_size
            # 총알 발사\
        new_bullet = Bullet(
            bullet_size_Up,
            damage=config.damage,
            owner_id=network.player_id,
            weapon_id=weapon_state.weapon_id,
        )
        new_bullet.launch(
            muzzle_x,
            muzzle_y,
            muzzle_x + math.cos(shot_angle) * BULLET_TARGET_DISTANCE,
            muzzle_y + math.sin(shot_angle) * BULLET_TARGET_DISTANCE,
            speed=config.bullet_speed,
            hold_ms=0,
        )
        new_bullet.just_fired = True
        new_bullet.life_time = config.bullet_lifetime
        bullets.append(new_bullet)

    if config.projectile and weapon_state.magazine_ammo == 0:
        reload_weapon()



def handle_mouse_down(event, mouse_pos):
    global mouse_fire_hold, system_message
    if event.button != 1:
        return
    if inventory_open:
        skill_name = select_skill_at(mouse_pos)
        if skill_name:
            system_message = f"[{skill_name}] 선택됨. Q, E 또는 T를 눌러 슬롯을 지정하세요."
        else:
            system_message = "보유 스킬 아이콘을 선택하세요."
        return
    if healing_inventory_open and HEAL_ITEM_RECT.collidepoint(mouse_pos):
        use_healing_item()
        return
    mouse_fire_hold = weapon_state.config.automatic
    fire_bullet()


def handle_mouse_up(event, mouse_pos):
    global mouse_fire_hold
    if event.button != 1:
        mouse_fire_hold = False
        return
    mouse_fire_hold = False


def handle_settings_overlay_event(event):
    global running, settings_key_waiting, settings_overlay_open, settings_dragging
    global system_message
    buttons = main_screen.draw_settings(
        settings, key_bindings, settings_key_waiting, overlay=True
    )
    if event.type == pygame.QUIT:
        running = False
    elif event.type == pygame.KEYDOWN:
        if settings_key_waiting:
            if event.key == pygame.K_ESCAPE:
                settings_key_waiting = None
            elif event.key not in RESERVED_KEYS:
                if (
                    event.key in key_bindings.values()
                    and key_bindings[settings_key_waiting] != event.key
                ):
                    system_message = "이미 다른 기능에 지정된 키입니다."
                else:
                    key_bindings[settings_key_waiting] = event.key
                    settings_key_waiting = None
                    save_settings()
        elif event.key in (pygame.K_ESCAPE, pygame.K_F1):
            settings_overlay_open = False
            save_settings()
    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        if buttons["back"].collidepoint(event.pos):
            settings_overlay_open = False
            settings_key_waiting = None
            settings_dragging = None
            save_settings()
        elif buttons["sensitivity"].collidepoint(event.pos):
            settings_dragging = "sensitivity"
            track = buttons["sensitivity"]
            progress = min(
                1.0,
                max(0.0, (event.pos[0] - track.left - 12) / (track.width - 24)),
            )
            settings["mouse_sensitivity"] = round(0.25 + progress * 1.75, 2)
        elif buttons["volume"].collidepoint(event.pos):
            settings_dragging = "volume"
            track = buttons["volume"]
            progress = min(
                1.0,
                max(0.0, (event.pos[0] - track.left - 12) / (track.width - 24)),
            )
            settings["sound_volume"] = round(progress, 2)
            set_effect_volume(settings["sound_volume"])
        elif buttons["owned_only"].collidepoint(event.pos):
            settings["owned_skills_only"] = not settings["owned_skills_only"]
            refresh_skill_inventory()
            save_settings()
        else:
            settings_key_waiting = next(
                (
                    action
                    for action, rect in buttons["keys"].items()
                    if rect.collidepoint(event.pos)
                ),
                None,
            )
    elif event.type == pygame.MOUSEMOTION and settings_dragging:
        track = buttons[settings_dragging]
        progress = min(
            1.0,
            max(0.0, (event.pos[0] - track.left - 12) / (track.width - 24)),
        )
        if settings_dragging == "sensitivity":
            settings["mouse_sensitivity"] = round(0.25 + progress * 1.75, 2)
        else:
            settings["sound_volume"] = round(progress, 2)
            set_effect_volume(settings["sound_volume"])
    elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
        settings_dragging = None
        save_settings()


def handle_game_events():
    global settings_overlay_open, settings_key_waiting, spectator_mode
    global spectator_selected_player_id, mouse_fire_hold
    global spectator_dismissed
    mouse_pos = pygame.mouse.get_pos()
    event_handlers = {
        pygame.QUIT: handle_quit,
        pygame.KEYDOWN: handle_key_event,
        pygame.MOUSEBUTTONDOWN: handle_mouse_down,
        pygame.MOUSEBUTTONUP: handle_mouse_up,
    }
    for event in pygame.event.get():
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F1:
            settings_overlay_open = not settings_overlay_open
            settings_key_waiting = None
            mouse_fire_hold = False
            continue
        if settings_overlay_open:
            handle_settings_overlay_event(event)
            continue
        if (
            event.type == pygame.KEYDOWN
            and event.key == pygame.K_TAB
            and not match_completed
        ):
            if spectator_mode and match_result == "defeat":
                spectator_dismissed = True
            spectator_mode = not spectator_mode
            mouse_fire_hold = False
            if spectator_mode:
                spectator_selected_player_id = next(
                    (
                        player_id
                        for player_id, info in server_players.items()
                        if info.get("hp", 0) > 0
                    ),
                    None,
                )
            continue
        if spectator_mode:
            if event.type == pygame.QUIT:
                handle_quit(event, mouse_pos)
            elif event.type == pygame.KEYDOWN:
                alive_players = [
                    player_id
                    for player_id, info in server_players.items()
                    if info.get("hp", 0) > 0
                ]
                if event.key == pygame.K_ESCAPE or event.key == pygame.K_TAB:
                    if match_result == "defeat":
                        spectator_dismissed = True
                    spectator_mode = False
                elif alive_players and event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    try:
                        selected_index = alive_players.index(spectator_selected_player_id)
                    except ValueError:
                        selected_index = 0
                    direction = -1 if event.key == pygame.K_LEFT else 1
                    spectator_selected_player_id = alive_players[
                        (selected_index + direction) % len(alive_players)
                    ]
            continue
        handler = event_handlers.get(event.type)
        if handler:
            handler(event, mouse_pos)


def GameFrame(practice_mode: bool = False):
    global ScreenState, CameraPosX, CameraPosY, AimCameraPosX, AimCameraPosY, Weapon_Angle, Weapon_Pos, match_result, local_stun_until, zone_elapsed_ms
    global screen_shake, server_players, bullets, remote_bullets, MousePos, system_message, kill_feed
    global vision_shape_override, vision_skill_until, local_match
    global active_bombs, active_explosions, supply_drops, next_supply_drop_at, pending_heal_amount, active_rune_tile, rune_alerts
    global last_effect_tick, preserve_magazine_after_chest
    global teleport_anchor, teleport_anchor_expires_at
    global damage_numbers, easter_egg_found, easter_egg_flash_until
    global local_kill_count, match_elapsed_ms, respawn_ms_remaining
    global hurt_flash_started_at
    global bush_entered_at, next_bush_leaf_at
    global bush_leaf_request_token
    global next_unique_supply_drop_at
    global selected_game_mode, debug_mode
    global lobby_notice, lobby_notice_until
    global unique_supply_notice, unique_supply_notice_until
    global active_world_weather, match_completed, spectator_mode

    is_practice_mode = bool(practice_mode or local_match)
    MousePos = pygame.mouse.get_pos()
    deathmatch = selected_game_mode == GAME_MODE_DEATHMATCH and not is_practice_mode
    if my_player.Hp <= 0 and not deathmatch and not use_revive_skill():
        if not spectator_mode or match_result != "defeat":
            show_defeat()
            return
    now = pygame.time.get_ticks()
    revived_after_server_update = False
    if (is_practice_mode or debug_mode) and training_dummy is None:
        respawn_training_dummy()
    # 연습 프레임은 서버 스냅샷을 읽지 않고 로컬 플레이 상태만 사용합니다.
    frame_server_players = {} if is_practice_mode else server_players
    damage_numbers = [
        number for number in damage_numbers
        if now - number["started_at"] < number["lifetime"]
    ]
    if teleport_anchor is not None and now >= teleport_anchor_expires_at:
        teleport_anchor = None
        teleport_anchor_expires_at = 0
        if teleport_placements_remaining <= 0:
            _finish_teleport_cycle(now)
            system_message = (
                f"텔포석상이 사라졌습니다. {TELEPORT_COOLDOWN_MS / 1000:g}초 후 다시 사용할 수 있습니다."
            )
        else:
            system_message = (
                f"텔포석상이 사라졌습니다. 남은 설치 횟수: {teleport_placements_remaining}"
            )
    handle_game_events()

    if my_player.Hp > 0 and mouse_fire_hold and weapon_state.config.automatic and weapon_state.can_fire():
        fire_bullet()

    Weapon_Pos = pygame.mouse.get_pos()

    haste_bonus = (
        PLAYER_HASTE_SPEED - PLAYER_NORMAL_SPEED if now < haste_until else 0
    )
    # 근접 무기의 추가 속도는 특수 이동인 대시에만 적용합니다.
    # 평상시 걷기와 Shift 달리기는 무기 종류와 무관하게 같은 속도를 유지합니다.
    knife_dash_bonus = (
        KNIFE_DASH_SPEED_BONUS
        if weapon_state.weapon_id in MELEE_WEAPON_IDS
        else 0
    )
    my_player.normal_speed = PLAYER_NORMAL_SPEED + haste_bonus
    my_player.sprint_speed = PLAYER_SPRINT_SPEED + haste_bonus
    my_player.dash_speed = PLAYER_DASH_SPEED + haste_bonus + knife_dash_bonus
    # 근접 무기 대시는 추가 속도만 적용하며, 지속 시간은 기본 대시와 같습니다.
    if my_player.Hp > 0 and now >= local_stun_until and now >= shield_until:
        my_player.dash_duration = PLAYER_DASH_DURATION_MS + (
            KNIFE_DASH_DURATION_BONUS_MS
            if weapon_state.weapon_id in MELEE_WEAPON_IDS
            else 0
        )
        dash_requested = (
            weapon_state.weapon_id in MELEE_WEAPON_IDS
            and pygame.mouse.get_pressed(3)[2]
        )
        my_player.handle_input(dash_requested)
    elif now < shield_until:
        my_player.is_dashing = False
        my_player.is_moving = False
    weapon_state.update_reload()

    current_tile = (
        int((my_player.X + my_player.rect.width / 2) // TileGene.tile_size),
        int((my_player.Y + my_player.rect.height / 2) // TileGene.tile_size),
    )
    rune_tile = next(
        (
            (current_tile[0] + offset_x, current_tile[1] + offset_y)
            for offset_x, offset_y in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1))
            if abs(offset_x) + abs(offset_y) <= RUNE_TRIGGER_TILE_RANGE
            and TileGene.get_tile_at(current_tile[0] + offset_x, current_tile[1] + offset_y)
            and TileGene.get_tile_at(current_tile[0] + offset_x, current_tile[1] + offset_y).tile_type == 5
        ),
        None,
    )
    send_data["rune_ping"] = None
    if rune_tile is not None:
        if active_rune_tile != rune_tile:
            send_data["rune_ping"] = (
                (rune_tile[0] + 0.5) * TileGene.tile_size,
                (rune_tile[1] + 0.5) * TileGene.tile_size,
            )
            active_rune_tile = rune_tile
    else:
        active_rune_tile = None

    effect_delta = max(0, now - last_effect_tick)
    last_effect_tick = now
    particles.update(effect_delta)
    if my_player.is_dashing:
        particles.emit(
            my_player.X + my_player.rect.width / 2,
            my_player.Y + my_player.rect.height / 2,
            (255, 255, 180), count=2, speed=35, lifetime=180, size=4,
        )
    if vision_skill_until and now >= vision_skill_until:
        vision_skill_until = 0
        vision_shape_override = None
    player_center_x, player_center_y = get_player_world_center(
        my_player.X, my_player.Y, IML.Player.get_width(), IML.Player.get_height()
    )
    if now >= next_supply_drop_at:
        spawn_supply_drop(now)
        next_supply_drop_at = now + SUPPLY_DROP_INTERVAL_MS
    if (
        not is_practice_mode
        and selected_game_mode != GAME_MODE_DEBUG
        and now >= next_unique_supply_drop_at - UNIQUE_SUPPLY_WARNING_MS
    ):
        spawn_unique_supply_drop(now)
        next_unique_supply_drop_at += UNIQUE_SUPPLY_INTERVAL_MS

    player_rect = my_player.rect
    collect_treasure(TileGene.treasure_at(player_rect))
    remaining_supply_drops = []
    for supply in supply_drops:
        supply_rect = pygame.Rect(
            round(supply["x"] - SUPPLY_DROP_RADIUS),
            round(supply["y"] - SUPPLY_DROP_RADIUS),
            SUPPLY_DROP_RADIUS * 2,
            SUPPLY_DROP_RADIUS * 2,
        )
        if now < supply["warning_until"]:
            remaining_supply_drops.append(supply)
            continue
        if player_rect.colliderect(supply_rect):
            pending_supply_collect_ids.add(supply["id"])
        remaining_supply_drops.append(supply)
    supply_drops = remaining_supply_drops

    pending_bombs = []
    for bomb in active_bombs:
        if now < bomb["explode_at"]:
            pending_bombs.append(bomb)
            continue
        active_explosions.append({
            "x": bomb["x"], "y": bomb["y"],
            "started_at": now, "until": now + EXPLOSION_DURATION_MS,
            "animation": FrameAnimation(
                IML.GetExplosionFrames(),
                max(1, EXPLOSION_DURATION_MS // max(1, len(IML.GetExplosionFrames()))),
                loop=False,
            ),
        })
        particles.emit(
            bomb["x"], bomb["y"], (255, 100, 30),
            count=45, speed=180, lifetime=700, size=8, gravity=90,
        )
        particles.ring(
            bomb["x"], bomb["y"], (255, 220, 80),
            count=24, radius=BOMB_RADIUS, lifetime=500, size=6,
        )
        screen_shake = min(SCREEN_SHAKE_MAX, screen_shake + 8)
        for p_id, p_info in frame_server_players.items():
            if is_hidden_player(p_info):
                continue
            player_center_x = p_info["posX"] + IML.Player.get_width() / 2
            player_center_y = p_info["posY"] + IML.Player.get_height() / 2
            distance = math.hypot(player_center_x - bomb["x"], player_center_y - bomb["y"])
            if distance <= BOMB_RADIUS:
                pending_hit_events.append({
                    "target_id": p_id,
                    "damage": BOMB_DAMAGE,
                    "hit_part": "body",
                    "attacker_id": network.player_id,
                    "weapon_id": weapon_state.weapon_id,
                })
        if (is_practice_mode or debug_mode) and training_dummy is not None and training_dummy.Hp > 0:
            dummy_center_x = training_dummy.rect.centerx
            dummy_center_y = training_dummy.rect.centery
            if math.hypot(dummy_center_x - bomb["x"], dummy_center_y - bomb["y"]) <= BOMB_RADIUS:
                previous_hp = training_dummy.Hp
                training_dummy.Hp = max(0, training_dummy.Hp - BOMB_DAMAGE)
                damage_numbers.append({
                    "x": dummy_center_x,
                    "y": training_dummy.rect.top,
                    "damage": previous_hp - training_dummy.Hp,
                    "color": (255, 255, 255),
                    "started_at": now,
                    "lifetime": DAMAGE_TEXT_LIFETIME_MS,
                })
                if training_dummy.Hp <= 0:
                    training_dummy.respawn_at = now + TRAINING_DUMMY_RESPAWN_MS
    active_bombs = pending_bombs
    active_explosions = [explosion for explosion in active_explosions if now < explosion["until"]]

    # ★ [정리] 서버 데이터 동기화 - 필요한 움직임 데이터만 전송
    send_data["posX"] = my_player.X
    send_data["posY"] = my_player.Y
    send_data["hp"] = my_player.Hp
    send_data["kill_count"] = local_kill_count
    send_data["angle"] = Weapon_Angle
    send_data["weapon_id"] = weapon_state.weapon_id
    send_data["magazine_ammo"] = weapon_state.magazine_ammo
    send_data["reserve_ammo"] = weapon_state.reserve_ammo
    player_world_x, player_world_y = get_player_world_center(
        my_player.X,
        my_player.Y,
        IML.Player.get_width(),
        IML.Player.get_height(),
    )
    # 스킬 은신과 지형 은폐를 분리해 서버가 각각의 상태를 전달합니다.
    in_bush = TileGene.is_in_bush(player_world_x, player_world_y)
    if in_bush:
        if not bush_entered_at:
            bush_entered_at = now
            next_bush_leaf_at = now + BUSH_LEAF_DELAY_MS
        elif now >= next_bush_leaf_at:
            bush_leaf_request_token += 1
            if is_practice_mode:
                particles.leaves(my_player.rect.centerx, my_player.rect.bottom - 8)
            else:
                pending_bush_leaf_requests.append({
                    "token": bush_leaf_request_token,
                })
            next_bush_leaf_at = now + BUSH_LEAF_INTERVAL_MS
    else:
        bush_entered_at = 0
        next_bush_leaf_at = 0
    send_data["stealth"] = now < stealth_until
    send_data["in_bush"] = in_bush
    send_data["stealth_token"] = stealth_token
    send_data["wards"] = list(wards)
    send_data["destroyed_treasures"] = list(pending_treasure_destroys)
    send_data["destroyed_furniture"] = list(pending_furniture_destroys)
    send_data["revive_token"] = revive_token
    send_data["heal_token"] = heal_token
    send_data["heal_amount"] = pending_heal_amount
    send_data["shield_active"] = shield_until > now
    send_data["revive_armed"] = any(
        slot.assigned_skill == "부활의 차"
        for slot in quick_slots
    )
    send_data["hit_events"] = list(pending_hit_events) if my_player.Hp > 0 else []
    send_data["supply_spawn_requests"] = list(pending_supply_spawn_requests)
    send_data["supply_collect_ids"] = list(pending_supply_collect_ids)
    send_data["bush_leaf_requests"] = list(pending_bush_leaf_requests)
    
    # ★ [정리] 총알 정보 - 이번 프레임에서 새로 발사된 총알만 전송
    send_data["bullets"] = [
        {
            "x": bullet.x,
            "y": bullet.y,
            "angle": bullet.angle,
            "weapon_id": bullet.weapon_id,
            "damage": bullet.damage,
            "stun_ms": bullet.stun_ms,
            "hold_ms": 0,
        }
        for bullet in bullets
        if hasattr(bullet, 'just_fired') and bullet.just_fired
    ]
    # 이미 전송된 총알 마크 해제
    for bullet in bullets:
        if hasattr(bullet, 'just_fired'):
            bullet.just_fired = False

    try:
        server_raw = None
        if not is_practice_mode:
            network.client.sendall(pickle.dumps(send_data))
            server_raw = network.client.recv(NETWORK_BUFFER_SIZE)
            if not server_raw:
                raise ConnectionError("서버가 동기화 연결을 종료했습니다.")
        if server_raw:
            server_response = pickle.loads(server_raw)
            if server_response.get("type") == "match_cancelled":
                selected_game_mode = GAME_MODE_NORMAL
                local_match = False
                debug_mode = False
                reset_match_state()
                lobby_notice = "다른 플레이어가 나가 매치가 취소되었습니다."
                lobby_notice_until = pygame.time.get_ticks() + 5000
                ScreenState = "ModeSelectView"
                return
            server_players = server_response
            pending_bush_leaf_requests.clear()
            own_snapshot = server_players.get(network.player_id)
            if spectator_mode:
                alive_players = [
                    player_id
                    for player_id, info in server_players.items()
                    if player_id != network.player_id and info.get("hp", 0) > 0
                ]
                if spectator_selected_player_id not in alive_players:
                    spectator_selected_player_id = (
                        alive_players[0] if alive_players else None
                    )
            if own_snapshot:
                server_weather = own_snapshot.get("weather")
                if (
                    server_weather in ("rain", "snow")
                    and server_weather != active_world_weather
                ):
                    world_effects.activate(
                        selected_game_mode,
                        (
                            MAP_WIDTH_TILES * TileGene.tile_size,
                            MAP_HEIGHT_TILES * TileGene.tile_size,
                        ),
                        force=True,
                        weather=server_weather,
                    )
                    active_world_weather = server_weather
            event_snapshot = own_snapshot or {}
            for leaf_event in event_snapshot.get("bush_leaf_events", []):
                event_id = leaf_event.get("event_id")
                if event_id is None or event_id in processed_bush_leaf_event_ids:
                    continue
                processed_bush_leaf_event_ids.add(event_id)
                particles.leaves(
                    leaf_event.get("x", 0),
                    leaf_event.get("y", 0),
                    count=12,
                    seed=leaf_event.get("seed"),
                )
            for kill_event in event_snapshot.get("kill_events", []):
                event_id = kill_event.get("event_id")
                if event_id is None or event_id in processed_kill_event_ids:
                    continue
                processed_kill_event_ids.add(event_id)
                kill_feed.append({
                    **kill_event,
                    "started_at": now,
                })
                if kill_event.get("cause") == "bat":
                    launch = create_bat_launch(
                        kill_event,
                        MAP_WIDTH_TILES * TileGene.tile_size,
                        MAP_HEIGHT_TILES * TileGene.tile_size,
                        now,
                    )
                    if launch is not None:
                        bat_launch_animations[str(kill_event.get("target_id"))] = launch
            kill_feed = [event for event in kill_feed if now - event["started_at"] < 5000][-5:]
            for damage_event in event_snapshot.get("damage_events", []):
                event_id = damage_event.get("event_id")
                if event_id in processed_damage_event_ids:
                    continue
                processed_damage_event_ids.add(event_id)
                target_id = damage_event.get("target_id")
                target = server_players.get(target_id)
                if target is None and str(target_id) == str(network.player_id):
                    target = {
                        "posX": my_player.X,
                        "posY": my_player.Y,
                    }
                if target is not None:
                    damage_x = target.get("posX", my_player.X) + my_player.rect.width / 2
                    damage_y = target.get("posY", my_player.Y) + my_player.rect.height / 2
                    damage_numbers.append({
                        "x": damage_x,
                        "y": target.get("posY", my_player.Y),
                        "damage": damage_event.get("damage", 0),
                        "color": (255, 235, 100) if damage_event.get("hit_part") == "head" else (255, 255, 255),
                        "started_at": now,
                        "lifetime": DAMAGE_TEXT_LIFETIME_MS,
                    })
                    if damage_event.get("stun_ms", 0) > 0:
                        particles.emit(
                            damage_x,
                            damage_y,
                            (90, 210, 255),
                            count=36,
                            speed=125,
                            lifetime=760,
                            size=5,
                            gravity=-20,
                        )
                        particles.emit(
                            damage_x,
                            damage_y,
                            (230, 255, 255),
                            count=18,
                            speed=85,
                            lifetime=420,
                            size=3,
                        )
                        particles.ring(
                            damage_x,
                            damage_y,
                            (180, 245, 255),
                            count=32,
                            radius=55,
                            lifetime=800,
                            size=4,
                        )
                if str(target_id) == str(network.player_id):
                    hurt_flash_started_at = now
                    screen_shake = min(SCREEN_SHAKE_MAX, screen_shake + 7)
                    particles.emit(
                        my_player.rect.centerx,
                        my_player.rect.centery,
                        (255, 75, 75),
                        count=16,
                        speed=100,
                        lifetime=420,
                        size=5,
                    )
            synchronized_treasures = {
                tuple(treasure) for treasure in event_snapshot.get("destroyed_treasures", [])
            }
            synchronized_furniture = {
                tuple(furniture) for furniture in event_snapshot.get("destroyed_furniture", [])
            }
            synchronized_rune_alerts = []
            if own_snapshot:
                synchronized_rune_alerts = own_snapshot.get("rune_alerts", [])
                synchronized_supply_drops = []
                for supply in own_snapshot.get("supply_drops", []):
                    warning_remaining_ms = supply.get("warning_remaining_ms", 0)
                    if (
                        supply.get("type") == "special_weapon"
                        and warning_remaining_ms <= 0
                        and supply.get("id") not in announced_unique_supply_ids
                    ):
                        announced_unique_supply_ids.add(supply.get("id"))
                        unique_supply_notice = "유니크 보급품이 맵에 떨어졌습니다!"
                        unique_supply_notice_until = now + 3500
                    synchronized_supply_drops.append({
                        **supply,
                        "fall_started_at": now - (
                            supply.get("warning_duration_ms", SUPPLY_DROP_WARNING_MS)
                            - warning_remaining_ms
                        ),
                        "warning_until": now + warning_remaining_ms,
                        "expires_at": now + supply.get("expires_remaining_ms", 0),
                    })
                supply_drops = synchronized_supply_drops
                pending_supply_spawn_requests.clear()
                pending_supply_collect_ids.clear()
                for collection_event in own_snapshot.get(
                    "supply_collection_events", []
                ):
                    event_id = collection_event.get("event_id")
                    if event_id in processed_supply_collection_ids:
                        continue
                    processed_supply_collection_ids.add(event_id)
                    if str(collection_event.get("player_id")) == str(network.player_id):
                        system_message = apply_supply_reward(
                            collection_event.get("type")
                        )
            for tile_x, tile_y in synchronized_treasures:
                TileGene.destroy_treasure(tile_x, tile_y)
            synchronized_furniture_changes = []
            for tile_x, tile_y in synchronized_furniture:
                if TileGene.destroy_furniture(tile_x, tile_y, rebuild_surface=False):
                    synchronized_furniture_changes.append((tile_x, tile_y))
            if synchronized_furniture_changes:
                TileGene.refresh_world_surface(synchronized_furniture_changes)
            rune_alerts = synchronized_rune_alerts
            pending_treasure_destroys.clear()
            pending_furniture_destroys.clear()
            pending_hit_events.clear()
            pending_heal_amount = 0
            send_data["revive_request"] = False
            zone_elapsed_ms = max(
                zone_elapsed_ms,
                max(0, int(server_players.get(network.player_id, {}).get("zone_elapsed_ms", 0))),
            )
            if own_snapshot:
                score_snapshot = own_snapshot.get("kill_scores", {})
                local_kill_count = int(
                    own_snapshot.get(
                        "kill_count",
                        score_snapshot.get(network.player_id, local_kill_count),
                    )
                )
                match_elapsed_ms = int(own_snapshot.get("match_elapsed_ms", match_elapsed_ms))
                respawn_ms_remaining = int(own_snapshot.get("respawn_ms_remaining", 0))
                was_dead = my_player.Hp <= 0
                my_player.Hp = own_snapshot.get("hp", my_player.Hp)
                if deathmatch and was_dead and my_player.Hp > 0:
                    my_player.X = own_snapshot.get("posX", my_player.X)
                    my_player.Y = own_snapshot.get("posY", my_player.Y)
                    my_player.rect.topleft = (round(my_player.X), round(my_player.Y))
                    my_player._update_hitboxes()
                    for respawn_weapon_id in (
                        main_weapon_id,
                        "knife",
                        third_weapon_id,
                    ):
                        if respawn_weapon_id:
                            weapon_state.refill_magazine(respawn_weapon_id)
                local_stun_until = now + own_snapshot.get("stun_ms_remaining", 0)
                weapon_id = own_snapshot.get("weapon_id", weapon_state.weapon_id)
                if weapon_id == weapon_state.weapon_id:
                    if preserve_magazine_after_chest:
                        preserve_magazine_after_chest = False
                    elif not weapon_state.is_reloading_now():
                        weapon_state.magazine_ammo = own_snapshot.get(
                            "magazine_ammo", weapon_state.magazine_ammo
                        )
                        weapon_state.reserve_ammo = own_snapshot.get(
                            "reserve_ammo", weapon_state.reserve_ammo
                        )
                if my_player.Hp <= 0 and not deathmatch:
                    revived_after_server_update = use_revive_skill()
            own_winner_ids = own_snapshot.get("winner_ids", []) if own_snapshot else []
            if own_winner_ids and not revived_after_server_update:
                match_completed = True
                spectator_mode = False
                if str(network.player_id) in {str(winner_id) for winner_id in own_winner_ids}:
                    show_victory()
                else:
                    show_defeat()
                return
            # ★ [정리] 서버에서 받은 플레이어 데이터 구조:
            # server_players[id] = {
            #     "posX": x,          # 상대 플레이어 위치
            #     "posY": y,
            #     "angle": angle,     # 상대 플레이어 무기 각도
            #     "hp": hp,           # 상대 플레이어 체력
            #     "bullets": [...]    # 상대가 발사한 총알들
            # }
    except (OSError, EOFError, pickle.PickleError, KeyError) as e:
        print(f"네트워크 통신 오류: {e}")
        if reconnect_to_server():
            reset_match_state()
            local_match = False
            network.last_lobby_request_at = 0
            ScreenState = "LoadingView"
            return


    # 온라인은 이번 프레임의 서버 스냅샷, 연습은 빈 원격 상태만 사용합니다.
    frame_server_players = {} if is_practice_mode else server_players

    # 카메라 이동
    player_center_x, player_center_y = get_player_world_center(my_player.X, my_player.Y, IML.Player.get_width(), IML.Player.get_height())
    target_camera_x, target_camera_y = get_camera_target(player_center_x, player_center_y, ScreenX, ScreenY, camera_zoom)
    CameraPosX += (target_camera_x - CameraPosX) * lerp
    CameraPosY += (target_camera_y - CameraPosY) * lerp
    AimCameraPosX, AimCameraPosY = CameraPosX, CameraPosY

    if screen_shake > 0:
        CameraPosX += random.randint(-screen_shake, screen_shake)
        CameraPosY += random.randint(-screen_shake, screen_shake)
        screen_shake -= 1

    CameraPosX, CameraPosY = TileGene.clamp_camera(
        CameraPosX, CameraPosY, ScreenX, ScreenY, camera_zoom
    )

    player_screen_x, player_screen_y = world_to_screen(my_player.X, my_player.Y, CameraPosX, CameraPosY, camera_zoom)
    player_center_screen_x, player_center_screen_y = get_player_screen_center(my_player.X, my_player.Y, IML.Player.get_width(), IML.Player.get_height(), CameraPosX, CameraPosY, camera_zoom)

    aim_player_center = get_player_screen_center(
        my_player.X,
        my_player.Y,
        IML.Player.get_width(),
        IML.Player.get_height(),
        AimCameraPosX,
        AimCameraPosY,
        camera_zoom,
    )
    Weapon_Angle = Tool.GetAtn2Angle_Degrees(aim_player_center, Weapon_Pos)
    if weapon_state.weapon_id == "pistol" and now < weapon_fire_until and IML.GetPistolFire():
        weapon_image = IML.GetPistolFire()
    elif weapon_state.weapon_id == "pistol" and now < weapon_smoke_until and IML.GetPistolSmoke():
        weapon_image = IML.GetPistolSmoke()
    else:
        weapon_image = IML.GetWeaponImage(weapon_state.weapon_id)
    weapon_image = weapon_image or IML.GetShotGun()
    if weapon_state.weapon_id == "pistol":
        weapon_image = pygame.transform.flip(weapon_image, True, False)
    shotgun_image = weapon_image if camera_zoom == 1.0 else pygame.transform.smoothscale(
        weapon_image, (round(weapon_image.get_width() * camera_zoom), round(weapon_image.get_height() * camera_zoom))
    )
    rotated_shotgun = pygame.transform.rotate(shotgun_image, -Weapon_Angle)
    Shotgun_rect = rotated_shotgun.get_rect()
    Shotgun_rect.center = (player_center_screen_x, player_center_screen_y)
    # 무기의 시야 설정과 일시적인 스킬 오버라이드를 합칩니다.
    current_vision = weapon_state.config
    current_vision_shape = vision_shape_override or current_vision.vision_shape
    current_vision_radius = (
        VISION_SKILL_RADIUS
        if vision_shape_override == VISION_CIRCLE
        else current_vision.vision_radius
    )
    current_vision_width = current_vision.vision_width
    if current_vision_shape == VISION_RECTANGLE:
        current_vision_radius = max(current_vision_radius, 900)
        current_vision_width = max(current_vision_width, 420)
    # 같은 프레임에서 같은 대상은 한 번만 벽 가림을 계산합니다.
    visibility_cache = {}

    def is_visible(point_x, point_y, fov_bonus=0):
        """다른 플레이어가 현재 시야 안에 있는지 확인합니다."""
        point = (point_x, point_y, fov_bonus)
        if point not in visibility_cache:
            visible_from_player = TileGene.is_point_visible_from(
                player_world_x,
                player_world_y,
                point_x,
                point_y,
                current_vision_radius,
                vision_shape=current_vision_shape,
                direction_angle=Weapon_Angle,
                fov_angle=current_vision.vision_fov + fov_bonus,
                vision_width=current_vision_width,
            )
            visible_from_base_vision = TileGene.is_point_visible_from(
                player_world_x,
                player_world_y,
                point_x,
                point_y,
                PLAYER_BASE_VISION_RADIUS,
                vision_shape=VISION_CIRCLE,
            )
            visible_from_ward = any(
                TileGene.is_point_visible_from(
                    ward_x,
                    ward_y,
                    point_x,
                    point_y,
                    WARD_VISION_RADIUS,
                    vision_shape=VISION_CIRCLE,
                )
                for ward_x, ward_y in wards
            )
            visibility_cache[point] = (
                visible_from_player or visible_from_base_vision or visible_from_ward
            )
        return visibility_cache[point]

    # ------------------ [게임 월드 그리기] ------------------
    display.fill((0, 0, 200))
    TileGene.draw(display, CameraPosX, CameraPosY, camera_zoom)
    zone_enabled = not is_practice_mode and get_game_mode(selected_game_mode).zone_enabled
    if zone_enabled:
        MagneticZoneState.draw(display, CameraPosX, CameraPosY, camera_zoom, zone_elapsed_ms)
    world_effects.update(effect_delta, (TileGene.map_width * TileGene.tile_size, TileGene.map_height * TileGene.tile_size))
    world_effects.draw(display, CameraPosX, CameraPosY, camera_zoom)

    player_world_x, player_world_y = get_player_world_center(my_player.X, my_player.Y, IML.Player.get_width(), IML.Player.get_height())
    if vision_skill_until > now:
        vision_screen_x, vision_screen_y = world_to_screen(
            player_world_x, player_world_y, CameraPosX, CameraPosY, camera_zoom
        )
        vision_screen_radius = max(1, round(VISION_SKILL_RADIUS * camera_zoom))
        pygame.draw.circle(
            display,
            (100, 210, 255),
            (round(vision_screen_x), round(vision_screen_y)),
            vision_screen_radius,
            max(1, round(2 * camera_zoom)),
        )
    if (is_practice_mode or debug_mode) and not easter_egg_found:
        map_center_x = TileGene.map_width * TileGene.tile_size / 2
        map_center_y = TileGene.map_height * TileGene.tile_size / 2
        if math.hypot(player_world_x - map_center_x, player_world_y - map_center_y) <= EASTER_EGG_DISTANCE:
            easter_egg_found = True
            easter_egg_flash_until = now + 3500
            system_message = "이스터에그 발견: 숨겨진 샌즈의 안식처"
            particles.ring(map_center_x, map_center_y, (100, 220, 255), count=36, radius=80, lifetime=1200, size=5)

    for bullet in bullets:
        bullet.update()

        if bullet.is_active:
            destructible = TileGene.destructible_collision(bullet.collision_rect)
            if destructible:
                tile_x, tile_y, tile_type = destructible
                if TileGene.destroy_furniture(tile_x, tile_y):
                    pending_furniture_destroys.append((tile_x, tile_y))
                    particles.emit(bullet.x, bullet.y, (180, 135, 90), count=20, speed=90, lifetime=500, size=5)
                bullet.is_active = False
                continue
            if TileGene.segment_wall_collision(
                bullet.previous_x, bullet.previous_y, bullet.x, bullet.y
            ):
                bullet.is_active = False
                continue
            treasure_position = TileGene.treasure_at(bullet.rect)
            if treasure_position:
                collect_treasure(treasure_position, from_bullet=True)
                bullet.is_active = False
                continue
            for p_id, p_info in frame_server_players.items():
                if str(p_id) == str(network.player_id) or is_hidden_player(p_info):
                    continue
                head, body = Player.hitboxes_for_position(
                    p_info["posX"], p_info["posY"], IML.Player.get_width(), IML.Player.get_height()
                )
                if head.colliderect(bullet.rect) or body.colliderect(bullet.rect):
                    hit_part = "head" if head.colliderect(bullet.rect) else "body"
                    pending_hit_events.append({
                        "target_id": p_id,
                        "attacker_id": bullet.owner_id,
                        "damage": bullet.damage,
                        "hit_part": hit_part,
                        "stun_ms": bullet.stun_ms,
                        "weapon_id": bullet.weapon_id,
                    })
                    bullet.is_active = False
                    impact_color = (100, 225, 255) if bullet.stun_ms else (255, 70, 70)
                    particles.emit(
                        bullet.x, bullet.y, impact_color,
                        count=12, speed=65, lifetime=350, size=4,
                    )
                    if bullet.stun_ms:
                        particles.ring(
                            bullet.x, bullet.y, (160, 240, 255),
                            count=20, radius=38, lifetime=650, size=4,
                        )
                    break
            if bullet.is_active and (is_practice_mode or debug_mode) and training_dummy is not None:
                previous_hp = training_dummy.Hp
                hit_part = training_dummy.check_bullet_hit(bullet.rect, bullet.damage)
                if hit_part:
                    dealt_damage = previous_hp - training_dummy.Hp
                    damage_numbers.append({
                        "x": training_dummy.rect.centerx,
                        "y": training_dummy.rect.top,
                        "damage": dealt_damage,
                        "color": (255, 235, 100) if hit_part == "head" else (255, 255, 255),
                        "started_at": now,
                        "lifetime": DAMAGE_TEXT_LIFETIME_MS,
                    })
                    particles.emit(bullet.x, bullet.y, (255, 210, 70), count=12, speed=65, lifetime=350, size=4)
                    bullet.is_active = False
                    if training_dummy.Hp <= 0:
                        training_dummy.respawn_at = now + TRAINING_DUMMY_RESPAWN_MS
                    break
    bullets = [b for b in bullets if b.is_active]
    if (is_practice_mode or debug_mode) and training_dummy is not None and training_dummy.Hp <= 0 and now >= training_dummy.respawn_at:
        respawn_training_dummy()

    # 서버 스냅샷에는 같은 발사 이벤트가 모든 플레이어 항목에 포함될 수
    # 있으므로 event_id 기준으로 한 번만 생성합니다.
    for p_info in frame_server_players.values():
        # 부쉬에 숨은 플레이어의 발사 이벤트는 기존처럼 다른 플레이어에게 노출하지 않습니다.
        if is_hidden_player(p_info) or p_info.get("stealth", False) or p_info.get("in_bush", False):
            continue
        for bullet_info in p_info.get("bullets", []):
            event_id = bullet_info.get("event_id")
            if event_id in processed_bullet_events:
                continue
            processed_bullet_events.add(event_id)
            if bullet_info.get("owner_id") == network.player_id:
                continue
            weapon_id = bullet_info.get("weapon_id", DEFAULT_WEAPON_ID)
            config = WEAPONS.get(weapon_id, WEAPONS[DEFAULT_WEAPON_ID])
            enemy_bullet = Bullet(
                config.bullet_size,
                damage=bullet_info.get("damage", config.damage),
                owner_id=bullet_info.get("owner_id"),
                weapon_id=weapon_id,
                stun_ms=bullet_info.get("stun_ms", 0),
            )
            angle = math.radians(bullet_info.get("angle", 0.0))
            enemy_bullet.launch(
                bullet_info["x"], bullet_info["y"],
                bullet_info["x"] + math.cos(angle) * BULLET_TARGET_DISTANCE,
                bullet_info["y"] + math.sin(angle) * BULLET_TARGET_DISTANCE,
                speed=config.bullet_speed,
                hold_ms=bullet_info.get("hold_ms", 45),
            )
            enemy_bullet.source_bullet_event_id = event_id
            remote_bullets.append(enemy_bullet)

    for bullet in remote_bullets:
        bullet.update()
        if bullet.is_active:
            destructible = TileGene.destructible_collision(bullet.collision_rect)
            if destructible:
                tile_x, tile_y, tile_type = destructible
                if TileGene.destroy_furniture(tile_x, tile_y):
                    pending_furniture_destroys.append((tile_x, tile_y))
                    particles.emit(bullet.x, bullet.y, (180, 135, 90), count=20, speed=90, lifetime=500, size=5)
                    bullet.is_active = False
        if bullet.is_active and TileGene.segment_wall_collision(
            bullet.previous_x, bullet.previous_y, bullet.x, bullet.y
        ):
            bullet.is_active = False
        if bullet.is_active and shield_until <= pygame.time.get_ticks():
            if my_player.head_hitbox.colliderect(bullet.rect):
                hit_part = "head"
            elif my_player.body_hitbox.colliderect(bullet.rect):
                hit_part = "body"
            else:
                hit_part = None
            if hit_part:
                pending_hit_events.append({
                    "target_id": network.player_id,
                    "attacker_id": bullet.owner_id,
                    "damage": bullet.damage,
                    "hit_part": hit_part,
                    "stun_ms": bullet.stun_ms,
                    "weapon_id": bullet.weapon_id,
                    "source_bullet_event_id": getattr(
                        bullet, "source_bullet_event_id", None
                    ),
                })
                bullet.is_active = False
    remote_bullets = [b for b in remote_bullets if b.is_active]

    if my_player.Hp <= 0 and not deathmatch and not use_revive_skill():
        if not spectator_mode or match_result != "defeat":
            show_defeat()
            return

    visible_player_ids = set()
    # 다른 플레이어 그리기
    remote_players = {} if is_practice_mode else frame_server_players
    hawk_vision_active = vision_skill_until > now
    for p_id, p_info in remote_players.items():
        if str(p_id) == str(network.player_id) or is_hidden_player(p_info):
            continue

        other_world_x, other_world_y = get_player_world_center(
            p_info["posX"],
            p_info["posY"],
            IML.Player.get_width(),
            IML.Player.get_height(),
        )
        target_in_bush = p_info.get("in_bush", False)
        close_to_bush = math.hypot(
            other_world_x - player_world_x,
            other_world_y - player_world_y,
        ) <= MAP_BUSH_VISIBLE_DISTANCE
        # 스킬 은신은 관찰자의 위치와 무관하게 유지합니다.
        if p_info.get("stealth", False):
            continue
        # 부쉬 은폐는 관찰자도 부쉬 안에 있을 때만 해제됩니다.
        if target_in_bush and not in_bush and not hawk_vision_active:
            continue

        bush_fov_bonus = (
            BUSH_VISION_FOV_BONUS
            if target_in_bush and close_to_bush
            else 0
        )
        if not is_visible(other_world_x, other_world_y, bush_fov_bonus):
            continue
        visible_player_ids.add(p_id)

        other_screen_x, other_screen_y = world_to_screen(p_info["posX"], p_info["posY"], CameraPosX, CameraPosY, camera_zoom)
        stun_offset_x, stun_offset_y = (
            _stun_shake_offset(now, sum(map(ord, str(p_id))) % 100)
            if p_info.get("stun_ms_remaining", 0) > 0
            else (0, 0)
        )
        other_image = IML.Player if camera_zoom == 1.0 else pygame.transform.scale(
            IML.Player, (round(IML.Player.get_width() * camera_zoom), round(IML.Player.get_height() * camera_zoom))
        )
        display.blit(
            other_image,
            (other_screen_x + stun_offset_x, other_screen_y + stun_offset_y),
        )

        other_center_x, other_center_y = get_player_screen_center(p_info["posX"], p_info["posY"], IML.Player.get_width(), IML.Player.get_height(), CameraPosX, CameraPosY, camera_zoom)
        other_center_x += stun_offset_x
        other_center_y += stun_offset_y
        server_weapon_id = p_info.get("weapon_id", DEFAULT_WEAPON_ID)
        if server_weapon_id in MELEE_WEAPON_IDS:
            melee_frames = (
                IML.GetBatFrames()
                if server_weapon_id == "bat"
                else IML.GetBladeFrames()
            )
            other_weapon_image = (
                melee_frames[0]
                if melee_frames
                else IML.GetWeaponImage(server_weapon_id)
            )
            if other_weapon_image is not None:
                _draw_melee_weapon(
                    display,
                    other_weapon_image,
                    (other_center_x, other_center_y),
                    p_info["angle"],
                    camera_zoom,
                )
        else:
            other_weapon_image = IML.GetWeaponImage(server_weapon_id)
            if other_weapon_image is not None:
                if server_weapon_id == "pistol":
                    other_weapon_image = pygame.transform.flip(
                        other_weapon_image, True, False
                    )
                other_gun = other_weapon_image if camera_zoom == 1.0 else pygame.transform.scale(
                    other_weapon_image, (round(other_weapon_image.get_width() * camera_zoom), round(other_weapon_image.get_height() * camera_zoom))
                )
                other_rotated_gun = pygame.transform.rotate(other_gun, -p_info["angle"])
                other_gun_rect = other_rotated_gun.get_rect()
                other_gun_rect.center = (other_center_x, other_center_y)
                display.blit(other_rotated_gun, other_gun_rect)
        other_name = GuiFont.render(str(p_info.get("name", f"P{p_id}")), True, (255, 230, 160))
        display.blit(
            other_name,
            other_name.get_rect(
                midbottom=(
                    round(other_center_x),
                    round(other_screen_y + stun_offset_y - 6),
                )
            ),
        )

    if debug_mode:
        practice_view.draw_training_dummy(
            training_dummy, CameraPosX, CameraPosY, camera_zoom
        )

    # 내 캐릭터 및 무기 그리기
    local_stun_offset_x, local_stun_offset_y = (
        _stun_shake_offset(now)
        if now < local_stun_until
        else (0, 0)
    )
    if my_player.Hp > 0 and (now < stealth_until or in_bush):
        stealth_image = my_player.get_display_image().copy()
        stealth_image.set_alpha(75 if now < stealth_until else 145)
        display.blit(
            stealth_image,
            ((my_player.rect.x - CameraPosX) * camera_zoom + local_stun_offset_x,
             (my_player.rect.y - CameraPosY) * camera_zoom + local_stun_offset_y),
        )
    elif my_player.Hp > 0:
        my_player.draw(
            display,
            CameraPosX,
            CameraPosY,
            camera_zoom,
            local_stun_offset_x,
            local_stun_offset_y,
        )
        if weapon_state.weapon_id in MELEE_WEAPON_IDS:
            is_bat = weapon_state.weapon_id == "bat"
            melee_frames = IML.GetBatFrames() if is_bat else IML.GetBladeFrames()
            melee_animation = bat_animation if is_bat else blade_animation
            melee_image = (
                melee_animation.frame_at(now)
                if knife_attack_until > now and melee_frames
                else (melee_frames[0] if melee_frames else IML.GetWeaponImage(weapon_state.weapon_id))
            )
            if melee_image is not None:
                _draw_melee_weapon(
                    display,
                    melee_image,
                    (
                        player_center_screen_x + local_stun_offset_x,
                        player_center_screen_y + local_stun_offset_y,
                    ),
                    Weapon_Angle,
                    camera_zoom,
                )
        else:
            display.blit(
                rotated_shotgun,
                Shotgun_rect.move(local_stun_offset_x, local_stun_offset_y),
            )



    
    # 기본 시야는 무기 시야와 구분되는 어두운 청색 영역으로 표시합니다.
    base_overlay = base_vision_overlay
    base_overlay.fill((8, 24, 42, PLAYER_BASE_VISION_ALPHA))
    base_vision_polygon = _cached_visibility_polygon(
        ("base", PLAYER_BASE_VISION_RADIUS),
        player_world_x,
        player_world_y,
        PLAYER_BASE_VISION_RADIUS,
        vision_shape=VISION_CIRCLE,
    )
    if base_vision_polygon:
        draw_visibility_geometry(
            base_overlay,
            base_vision_polygon,
            CameraPosX,
            CameraPosY,
            camera_zoom,
        )
    display.blit(base_overlay, (0, 0))

    # 화면 전체를 어둡게 한 뒤, 아래에서 무기 시야 폴리곤만 투명하게 뚫습니다.
    dark_overlay = vision_overlay
    # 완전한 검정이 아니라 뒤의 맵이 살짝 보이는 반투명 검정입니다.
    dark_overlay.fill((0, 0, 0, VISION_OVERLAY_ALPHA))

    # 맵 바깥은 월드 타일이 없으므로 항상 검게 처리합니다.
    map_screen_left = -CameraPosX * camera_zoom
    map_screen_top = -CameraPosY * camera_zoom
    map_screen_right = (TileGene.map_width * TileGene.tile_size - CameraPosX) * camera_zoom
    map_screen_bottom = (TileGene.map_height * TileGene.tile_size - CameraPosY) * camera_zoom
    pygame.draw.rect(dark_overlay, (0, 0, 0, 255), (0, 0, ScreenX, max(0, map_screen_top)))
    pygame.draw.rect(dark_overlay, (0, 0, 0, 255), (0, min(ScreenY, map_screen_bottom), ScreenX, max(0, ScreenY - map_screen_bottom)))
    pygame.draw.rect(dark_overlay, (0, 0, 0, 255), (0, 0, max(0, map_screen_left), ScreenY))
    pygame.draw.rect(dark_overlay, (0, 0, 0, 255), (min(ScreenX, map_screen_right), 0, max(0, ScreenX - map_screen_right), ScreenY))

    # 기본 시야는 무기 시야 밖에서도 밝은 원형 영역으로 유지합니다.
    if base_vision_polygon:
        draw_visibility_geometry(
            dark_overlay,
            base_vision_polygon,
            CameraPosX,
            CameraPosY,
            camera_zoom,
        )

    # 픽셀 위치와 정확한 조준 방향을 사용해 그림자가 움직임을 따라가게 합니다.
    vision_angle = (
        None
        if current_vision_shape == VISION_CIRCLE
        else round(Weapon_Angle)
    )
    polygon_cache_key = (
        "weapon",
        vision_angle,
        current_vision_shape,
        current_vision_radius,
        current_vision.vision_fov,
        current_vision_width,
    )
    visibility_polygon = _cached_visibility_polygon(
        polygon_cache_key,
        player_world_x,
        player_world_y,
        current_vision_radius,
        vision_shape=current_vision_shape,
        direction_angle=vision_angle or 0,
        fov_angle=current_vision.vision_fov,
        vision_width=current_vision_width,
        ray_samples=24 if current_vision_shape == VISION_CIRCLE else None,
    )
    if visibility_polygon:
        # 월드 폴리곤을 현재 카메라 좌표로 변환해 어두운 레이어를 뚫습니다.
        draw_visibility_geometry(dark_overlay, visibility_polygon, CameraPosX, CameraPosY, camera_zoom)

    for ward_x, ward_y in wards:
        ward_key = (
            "ward",
            round(ward_x / 8),
            round(ward_y / 8),
            WARD_VISION_RADIUS,
        )
        if ward_key not in visibility_polygon_cache:
            visibility_polygon_cache[ward_key] = TileGene.get_visibility_polygon(
                ward_x,
                ward_y,
                WARD_VISION_RADIUS,
                vision_shape=VISION_CIRCLE,
            )
        draw_visibility_geometry(
            dark_overlay,
            visibility_polygon_cache[ward_key],
            CameraPosX,
            CameraPosY,
            camera_zoom,
        )

    display.blit(dark_overlay, (0, 0))

    for target_id, launch in list(bat_launch_animations.items()):
        center_x, center_y, rotation, alpha, finished = get_bat_launch_frame(launch, now)
        if finished:
            bat_launch_animations.pop(target_id, None)
            continue
        screen_x, screen_y = world_to_screen(center_x, center_y, CameraPosX, CameraPosY, camera_zoom)
        sprite = IML.Player.copy()
        sprite.set_alpha(alpha)
        if camera_zoom != 1.0:
            sprite = pygame.transform.scale(
                sprite,
                (
                    max(1, round(sprite.get_width() * camera_zoom)),
                    max(1, round(sprite.get_height() * camera_zoom)),
                ),
            )
        sprite = pygame.transform.rotate(sprite, rotation)
        sprite_rect = sprite.get_rect(center=(round(screen_x), round(screen_y)))
        if sprite_rect.colliderect(display.get_rect()):
            display.blit(sprite, sprite_rect)

    for p_id, p_info in frame_server_players.items():
        if p_id not in visible_player_ids or p_info.get("stun_ms_remaining", 0) <= 0:
            continue
        stunned_center = get_player_screen_center(
            p_info["posX"], p_info["posY"],
            IML.Player.get_width(), IML.Player.get_height(),
            CameraPosX, CameraPosY, camera_zoom,
        )
        stun_offset_x, stun_offset_y = _stun_shake_offset(
            now, sum(map(ord, str(p_id))) % 100
        )
        draw_stun_effect(
            display,
            stunned_center[0] + stun_offset_x,
            stunned_center[1] + stun_offset_y,
            camera_zoom,
            now,
        )

    # 시야 오버레이 위에 로컬 플레이어를 다시 그려 기본 시야에서도 항상 보이게 합니다.
    if my_player.Hp > 0 and (now < stealth_until or in_bush):
        visible_player_image = my_player.get_display_image().copy()
        visible_player_image.set_alpha(75 if now < stealth_until else 145)
        if camera_zoom != 1.0:
            visible_player_image = pygame.transform.scale(
                visible_player_image,
                (
                    max(1, round(visible_player_image.get_width() * camera_zoom)),
                    max(1, round(visible_player_image.get_height() * camera_zoom)),
                ),
            )
        display.blit(
            visible_player_image,
            (
                round((my_player.rect.x - CameraPosX) * camera_zoom + local_stun_offset_x),
                round((my_player.rect.y - CameraPosY) * camera_zoom + local_stun_offset_y),
            ),
        )
    elif my_player.Hp > 0:
        my_player.draw(
            display,
            CameraPosX,
            CameraPosY,
            camera_zoom,
            local_stun_offset_x,
            local_stun_offset_y,
        )

    if my_player.Hp > 0 and weapon_state.weapon_id != "knife":
        display.blit(
            rotated_shotgun,
            Shotgun_rect.move(local_stun_offset_x, local_stun_offset_y),
        )
    if my_player.Hp > 0:
        local_name = GuiFont.render(player_name or "플레이어", True, (255, 230, 160))
        display.blit(
            local_name,
            local_name.get_rect(
                midbottom=(
                    round(player_center_screen_x + local_stun_offset_x),
                    round(player_screen_y + local_stun_offset_y - 6),
                )
            ),
        )
    if now < local_stun_until:
        draw_stun_effect(
            display,
            player_center_screen_x + local_stun_offset_x,
            player_center_screen_y + local_stun_offset_y,
            camera_zoom,
            now,
        )

    for alert_x, alert_y, remaining_ms in rune_alerts:
        alert_screen_x, alert_screen_y = world_to_screen(
            alert_x, alert_y, CameraPosX, CameraPosY, camera_zoom
        )
        pulse = 28 + round(8 * math.sin(now * 0.02))
        pygame.draw.circle(
            display,
            (255, 225, 100),
            (round(alert_screen_x), round(alert_screen_y)),
            max(10, round(pulse * camera_zoom)),
            3,
        )
        pygame.draw.line(
            display,
            (255, 235, 130),
            (round(alert_screen_x), max(0, round(alert_screen_y - 150 * camera_zoom))),
            (round(alert_screen_x), round(alert_screen_y)),
            2,
        )
        alert_text = RuneAlertFont.render("발광 룬", True, (255, 235, 130))
        display.blit(
            alert_text,
            alert_text.get_rect(
                center=(round(alert_screen_x), max(16, round(alert_screen_y - 165 * camera_zoom)))
            ),
        )

    # 조준선은 로컬 화면에만 그리므로 다른 플레이어에게 동기화되지 않습니다.
    draw_local_aim_ray(
        display,
        player_center_screen_x,
        player_center_screen_y,
        Weapon_Angle,
        CameraPosX,
        CameraPosY,
        camera_zoom,
        TileGene,
        BULLET_TARGET_DISTANCE,
    )

    # 시야 밖에 있어도 총알은 항상 보이도록 최종 레이어에서 다시 그립니다.
    for bullet in bullets:
        bullet.draw(display, CameraPosX, CameraPosY, camera_zoom, force_visible=True)
        if bullet.is_active and bullet.stun_ms:
            bolt_screen = world_to_screen(
                bullet.x + bullet.rect.width / 2,
                bullet.y + bullet.rect.height / 2,
                CameraPosX,
                CameraPosY,
                camera_zoom,
            )
            draw_stun_bolt(
                display, *bolt_screen, bullet.angle, camera_zoom, now
            )

    for bullet in remote_bullets:
        bullet.draw(display, CameraPosX, CameraPosY, camera_zoom, force_visible=True)
        if bullet.is_active and bullet.stun_ms:
            bolt_screen = world_to_screen(
                bullet.x + bullet.rect.width / 2,
                bullet.y + bullet.rect.height / 2,
                CameraPosX,
                CameraPosY,
                camera_zoom,
            )
            draw_stun_bolt(
                display, *bolt_screen, bullet.angle, camera_zoom, now
            )

    if show_hitboxes:
        draw_player_hitboxes(
            display,
            my_player.head_hitbox,
            my_player.body_hitbox,
            CameraPosX,
            CameraPosY,
            camera_zoom,
        )
        for p_id in visible_player_ids:
            p_info = frame_server_players.get(p_id)
            if not p_info:
                continue
            head, body = Player.hitboxes_for_position(
                p_info["posX"],
                p_info["posY"],
                IML.Player.get_width(),
                IML.Player.get_height(),
            )
            draw_player_hitboxes(
                display,
                head,
                body,
                CameraPosX,
                CameraPosY,
                camera_zoom,
            )
        if is_practice_mode or debug_mode:
            practice_view.draw_training_dummy_hitboxes(
                training_dummy, CameraPosX, CameraPosY, camera_zoom
            )

    # 폭탄과 폭발 범위는 시야 효과 위에 표시합니다.
    for supply in supply_drops:
        draw_supply_drop(display, supply, CameraPosX, CameraPosY, camera_zoom, SUPPLY_COLORS, now)

    for bomb in active_bombs:
        bomb_screen = world_to_screen(bomb["x"], bomb["y"], CameraPosX, CameraPosY, camera_zoom)
        remaining_ratio = max(0.0, (bomb["explode_at"] - now) / BOMB_DELAY_MS)
        pulse = 1.0 + 0.06 * math.sin(now * 0.025)
        draw_skill_range(
            display,
            bomb["x"],
            bomb["y"],
            BOMB_RADIUS,
            CameraPosX,
            CameraPosY,
            camera_zoom,
            (255, 150, 35),
            pulse,
        )
        pygame.draw.arc(
            display,
            (255, 245, 180),
            pygame.Rect(
                round(bomb_screen[0] - 20 * camera_zoom),
                round(bomb_screen[1] - 20 * camera_zoom),
                max(1, round(40 * camera_zoom)),
                max(1, round(40 * camera_zoom)),
            ),
            -math.pi / 2,
            -math.pi / 2 + math.tau * (1 - remaining_ratio),
            max(2, round(3 * camera_zoom)),
        )
        pygame.draw.circle(display, (255, 170, 40), (round(bomb_screen[0]), round(bomb_screen[1])),
                           max(5, round(12 * camera_zoom)), 3)
    for explosion in active_explosions:
        explosion_screen = world_to_screen(
            explosion["x"], explosion["y"], CameraPosX, CameraPosY, camera_zoom
        )
        progress = (now - explosion["started_at"]) / EXPLOSION_DURATION_MS
        draw_skill_range(
            display,
            explosion["x"],
            explosion["y"],
            BOMB_RADIUS * min(1.0, max(0.15, progress)),
            CameraPosX,
            CameraPosY,
            camera_zoom,
            (255, 105, 35),
        )
        if IML.GetExplosionFrames():
            explosion["animation"].start(explosion["started_at"])
            explosion_image = explosion["animation"].frame_at(now)
            explosion_image = pygame.transform.smoothscale(
                explosion_image,
                (max(1, round(explosion_image.get_width() * camera_zoom)), max(1, round(explosion_image.get_height() * camera_zoom))),
            )
            display.blit(explosion_image, explosion_image.get_rect(center=(round(explosion_screen[0]), round(explosion_screen[1]))))
        else:
            pygame.draw.circle(
                display, (255, 80, 20),
                (round(explosion_screen[0]), round(explosion_screen[1])),
                max(10, round(120 * camera_zoom)), 5,
            )

    particles.draw(display, CameraPosX, CameraPosY, camera_zoom)
    draw_damage_numbers(display, damage_numbers, CameraPosX, CameraPosY, camera_zoom, GuiFont, now)

    if easter_egg_found and now < easter_egg_flash_until:
        egg_text = GuiFont.render("THE SECRET IS WATCHING", True, (120, 230, 255))
        display.blit(egg_text, egg_text.get_rect(center=(ScreenX // 2, 120)))

    if teleport_anchor is not None:
        draw_teleport_anchor(
            display,
            *teleport_anchor,
            CameraPosX,
            CameraPosY,
            camera_zoom,
            IML.TpStatue,
        )

    for ward_x, ward_y in wards:
        draw_skill_range(
            display,
            ward_x,
            ward_y,
            WARD_VISION_RADIUS,
            CameraPosX,
            CameraPosY,
            camera_zoom,
            (80, 220, 255),
        )
        draw_ward(
            display, ward_x, ward_y, CameraPosX, CameraPosY, camera_zoom,
            IML.GetWardImage(),
        )
    for player_id, player_info in frame_server_players.items():
        if str(player_id) == str(network.player_id) or is_hidden_player(player_info):
            continue
        for ward_x, ward_y in player_info.get("wards", []):
            if TileGene.is_point_visible_from(
                player_world_x,
                player_world_y,
                ward_x,
                ward_y,
                current_vision_radius,
                vision_shape=current_vision_shape,
                direction_angle=Weapon_Angle,
                fov_angle=current_vision.vision_fov,
                vision_width=current_vision_width,
            ):
                draw_ward(
                    display, ward_x, ward_y, CameraPosX, CameraPosY, camera_zoom,
                    IML.GetWardImage(),
                )

    if my_player.Hp > 0 and shield_until > pygame.time.get_ticks():
        shield_center = get_player_screen_center(
            my_player.X, my_player.Y, IML.Player.get_width(), IML.Player.get_height(),
            CameraPosX, CameraPosY, camera_zoom
        )
        # Protect.png 이미지가 있으면 반투명으로 표시
        if IML.Protect:
            protect_size = max(50, int(90 * camera_zoom))
            protect_scaled = _scale_cached(
                IML.Protect, (protect_size, protect_size), smooth=False
            )
            protect_scaled.set_alpha(SHIELD_ALPHA)
            protect_rect = protect_scaled.get_rect(center=shield_center)
            display.blit(protect_scaled, protect_rect)
        else:
            # Protect.png가 없으면 파란 원으로 표시
            pygame.draw.circle(display, (100, 220, 255),
                               (round(shield_center[0]), round(shield_center[1])),
                               max(20, round(45 * camera_zoom)), 4)

    # =================================================================
    # 📊 고정 UI 그리기 영역 (시야 레이어보다 위에 그려야 선명하게 보입니다)
    # =================================================================
    MiniMapRenderer.draw(
        display,
        (
            my_player.X + my_player.rect.width / 2,
            my_player.Y + my_player.rect.height / 2,
        ),
        frame_server_players,
        network.player_id,
        training_dummy if is_practice_mode or debug_mode else None,
        rune_alerts,
        MagneticZoneState if zone_enabled else None,
        zone_elapsed_ms,
        supply_drops,
        (
            get_unique_supply_countdown(now)
            if not is_practice_mode and selected_game_mode != GAME_MODE_DEBUG
            else None
        ),
    )
    kill_feed = [
        event for event in kill_feed
        if now - event.get("started_at", now) < 5000
    ][-5:]
    draw_kill_feed(
        display,
        kill_feed,
        KillFeedFont,
        IML.GetKillLog(),
        IML.GetWeaponImage,
        network.player_id,
        player_name,
    )
    if deathmatch:
        remaining_ms = max(0, DEATHMATCH_DURATION_MS - match_elapsed_ms)
        timer_text = KillFeedFont.render(
            f"데스매치  {remaining_ms // 60000:02d}:{(remaining_ms // 1000) % 60:02d}",
            True,
            (255, 235, 160),
        )
        display.blit(timer_text, timer_text.get_rect(midtop=(ScreenX // 2, 20)))
        score_text = KillFeedFont.render(f"내 킬 수: {local_kill_count}", True, (255, 255, 255))
        display.blit(score_text, score_text.get_rect(midtop=(ScreenX // 2, 48)))
        if my_player.Hp <= 0:
            respawn_panel = pygame.Surface((340, 112), pygame.SRCALPHA)
            pygame.draw.rect(
                respawn_panel,
                (12, 20, 32, 215),
                respawn_panel.get_rect(),
                border_radius=14,
            )
            pygame.draw.rect(
                respawn_panel,
                (255, 120, 120, 220),
                respawn_panel.get_rect(),
                width=2,
                border_radius=14,
            )
            display.blit(
                respawn_panel,
                respawn_panel.get_rect(center=(ScreenX // 2, ScreenY // 2)),
            )
            respawn_title = GuiFont.render("부활 중", True, (255, 225, 225))
            display.blit(
                respawn_title,
                respawn_title.get_rect(center=(ScreenX // 2, ScreenY // 2 - 20)),
            )
            respawn_timer = KillFeedFont.render(
                f"부활까지 {respawn_ms_remaining / 1000:.1f}초",
                True, (255, 170, 170),
            )
            display.blit(
                respawn_timer,
                respawn_timer.get_rect(center=(ScreenX // 2, ScreenY // 2 + 23)),
            )
        scores = server_players.get(network.player_id, {}).get("kill_scores", {})
        ranked_players = sorted(
            scores.items(), key=lambda item: (-item[1], str(item[0]))
        )[:MAX_PLAYERS]
        for rank, (score_player_id, score) in enumerate(ranked_players):
            score_player = server_players.get(score_player_id, {})
            score_name = score_player.get("name", str(score_player_id)[:8])
            score_color = (255, 235, 160) if str(score_player_id) == str(network.player_id) else (240, 240, 240)
            score_text = KillFeedFont.render(
                f"{rank + 1}. {score_name}: {score}", True, score_color
            )
            smaller_score_text = pygame.transform.smoothscale(
                score_text,
                (
                    max(1, round(score_text.get_width() * 0.9)),
                    max(1, round(score_text.get_height() * 0.9)),
                ),
            )
            display.blit(smaller_score_text, (ScreenX - 300, 94 + rank * 22))
    if game_start_banner_until > now:
        remaining = game_start_banner_until - now
        game_start_banner.set_alpha(min(255, max(0, remaining * 2)))
        display.blit(game_start_banner, game_start_banner.get_rect(center=(ScreenX // 2, 150)))
    unique_warning = next(
        (
            supply for supply in supply_drops
            if supply.get("type") == "special_weapon" and now < supply["warning_until"]
        ),
        None,
    )
    unique_message = ""
    if unique_warning is not None:
        remaining_seconds = max(
            1,
            (round(unique_warning["warning_until"] - now) + 999) // 1000,
        )
        unique_message = f"유니크 보급품이 곧 도착합니다 · {remaining_seconds}초"
    elif now < unique_supply_notice_until:
        unique_message = unique_supply_notice
    if unique_message:
        cached_banners = unique_supply_banner_cache.get(unique_message)
        if cached_banners is None:
            unique_banner = KillFeedFont.render(
                unique_message, True, (255, 230, 125)
            )
            shadow = KillFeedFont.render(unique_message, True, (20, 20, 15))
            if len(unique_supply_banner_cache) >= 8:
                unique_supply_banner_cache.clear()
            unique_supply_banner_cache[unique_message] = (unique_banner, shadow)
        else:
            unique_banner, shadow = cached_banners
        unique_banner_rect = unique_banner.get_rect(
            center=(ScreenX // 2, ScreenY // 2 - 120)
        )
        for offset in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            display.blit(shadow, unique_banner_rect.move(*offset))
        display.blit(unique_banner, unique_banner_rect)
    ui_x = 30
    ui_y = 80  
    draw_health_bar(
        display,
        ui_x,
        ui_y,
        my_player.Hp,
        my_player.MaxHp,
        HpBarFrame,
        HP_FRAME_SIZE,
        (HEALTH_GREEN_THRESHOLD, HEALTH_YELLOW_THRESHOLD),
    )
    
    # [커스텀 가능] HP 텍스트 표시 폰트 (GuiFont 사용)
    hp_text = GuiFont.render(f"HP: {my_player.Hp} / {my_player.MaxHp}", True, (255, 255, 255))
    display.blit(hp_text, (ui_x + HP_FRAME_SIZE[0] + 15, ui_y + 30))

    # [커스텀 가능] 플레이어 ID 표시 폰트 (GuiFont 사용)
    id_text = GuiFont.render(f"ID: {network.player_id}", True, (255, 255, 255))
    display.blit(id_text, (20, 20))
    
    # --- [퀵슬롯 배경과 스킬 소스창] ---
    draw_skill_panel(display)
    hovered_skill = draw_skill_inventory(display, MousePos, inventory_open)
    draw_healing_inventory(display)

    # 하단 퀵슬롯 (�익슬롯은 항상 보임)
    for slot in quick_slots:
        slot.update(MousePos)  # 호버 상태 업데이트
        slot.draw(display)

    draw_quick_slot_cooldowns(display, quick_slots, skill_cooldowns, GuiFont)
    draw_ammo_status(
        display,
        weapon_state,
        GuiFont,
        ScreenX,
        ScreenY,
        AMMO_PANEL_SIZE,
        AMMO_PANEL_MARGIN,
    )
    
    # ★ [추가] 스킬 툴팁 그리기 (마우스 raycast 무시 - 드래그 중이 아닐 때만)
    if hovered_skill:
        draw_skill_tooltip(display, MousePos, hovered_skill)

    player_name_text = GuiFont.render(player_name or "플레이어", True, (255, 230, 160))
    display.blit(player_name_text, (30, ScreenY - 78))

    # 시스템 메시지
    if system_message:
        # [커스텀 가능] 시스템 메시지 텍스트 폰트 (GuiFont 사용)
        message_text = GuiFont.render(system_message, True, (255, 255, 255))
        display.blit(message_text, (30, ScreenY - 42))
    
    if is_practice_mode or debug_mode: # 스킬 창 상태 표시 (우측 상단)
        if zone_enabled:
            zone_center_x, zone_center_y = get_player_world_center(
                my_player.X, my_player.Y, IML.Player.get_width(), IML.Player.get_height()
            )
            zone_status = MagneticZoneState.stage_text(zone_elapsed_ms)
            if not MagneticZoneState.is_inside(zone_center_x, zone_center_y, zone_elapsed_ms):
                zone_status = "자기장 밖: 3초 후 피해 증가"
                zone_color = (255, 100, 100)
            else:
                zone_color = (255, 180, 180)
        else:
            zone_status = "훈련장: 자기장 비활성화"
            zone_color = (180, 220, 255)
        practice_view.draw_training_status(
            current_vision_shape,
            camera_fov,
            CAMERA_FOV_MAX,
            zone_status,
            zone_color,
        )
    if hurt_flash_started_at:
        elapsed = now - hurt_flash_started_at
        hurt_image = IML.GetHurtImage()
        if 0 <= elapsed < HURT_FLASH_DURATION_MS and hurt_image is not None:
            hurt_image.set_alpha(round(
                HURT_FLASH_MAX_ALPHA * (1 - elapsed / HURT_FLASH_DURATION_MS)
            ))
            display.blit(hurt_image, (0, 0))
    if spectator_mode and not settings_overlay_open:
        MiniMapRenderer.draw_spectator(
            display,
            frame_server_players,
            IML.Player,
            spectator_selected_player_id,
        )
    if settings_overlay_open:
        main_screen.draw_settings(
            settings, key_bindings, settings_key_waiting, overlay=True
        )
    # ------------------ [그리기 끝] ------------------


def GameView():
    GameFrame(practice_mode=False)


def PracticeGameView():
    GameFrame(practice_mode=True)


while running: 
    display.fill((0,0,0))
    if ScreenState == "MainView":
        MainView()
    elif ScreenState == "ModeSelectView":
        ModeSelectView()
    elif ScreenState == "NameInputView":
        NameInputView()
    elif ScreenState == "SettingsView":
        SettingsView()
    elif ScreenState == "LoadingView":
        LoadingView()
    elif ScreenState == "GameView":
        GameView()
    elif ScreenState == "PracticeView":
        PracticeGameView()
    elif ScreenState == "ExitConfirmView":
        ExitConfirmView()
    elif ScreenState == "Victory":
        VictoryView()
    elif ScreenState == "GameOver":
        GameOverView()
    pygame.display.update() 
    clock.tick(FPS)

pygame.quit()
