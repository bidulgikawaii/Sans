import pygame
from Config import *
from ImageLoad import *
import math
from TileGenerator import *
from Bullet import *
import Tool
import random
import os
import socket
import pickle
from PlayerClass import Player
from Tool_Cordinate import *
from SkillAndSlot import *
from Weapon import WeaponState, WEAPONS, WEAPON_KEYS
from Effects import ParticleSystem
from MainScreen import MainScreenRenderer
from MiniMap import MiniMap
from GameRendering import (
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
)
from GameAudio import load_effect_sound, play_effect_sound
from Zone import MagneticZone

pygame.init()
pygame.display.set_caption("전설적인 게임")
display = pygame.display.set_mode((ScreenX, ScreenY), 0, 32)
clock = pygame.time.Clock()
ScreenState = "MainView"
selected_game_mode = GAME_MODE_NORMAL
local_match = False
main_weapon_id = DEFAULT_WEAPON_ID
player_name = ""
lobby_status = {
    "count": 0,
    "max_players": MAX_PLAYERS,
    "mode": GAME_MODE_NORMAL,
    "started": False,
}
last_lobby_request_at = 0
# [커스텀 가능] 게임 전체에서 사용할 기본 폰트입니다. 서체와 크기를 여기서 조정합니다.
GuiFont = pygame.font.Font(os.path.join(os.path.dirname(os.path.abspath(__file__)
        ),"Font","HeirofLightRegular.ttf"
            ), 30)


class OfflineClient:
    def __init__(self):
        self.initialized = False

    def send(self, _data):
        return None

    def sendall(self, _data):
        return None

    def recv(self, _size):
        if not self.initialized:
            self.initialized = True
            return pickle.dumps({"init_id": 1, "seed": SERVER_SEED})
        return pickle.dumps({})

    def close(self):
        return None




# --- [네트워크 초기화] ---
def connect_to_server():
    last_error = None
    for host in (ServerIp, ServerIp2):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        try:
            sock.connect((host, ServerPort))
            return sock
        except (OSError, socket.timeout) as exc:
            last_error = exc
            sock.close()
    print(f"서버 연결 실패, 로컬 모드로 실행합니다: {last_error}")
    return OfflineClient()

client = connect_to_server()

init_data = pickle.loads(client.recv(1024))
my_id = init_data["init_id"]
print(f"내 아이디:{my_id}번 입니다.")


random.seed(init_data["seed"])
IML = Imageload()
main_screen = MainScreenRenderer(display, IML.GetTitles(), GuiFont, (ScreenX, ScreenY))
set_ui_assets(IML.SkillWindow, IML.QuickSlot)
set_image_loader(IML)  # SkillAndSlot에 이미지 로더 전달
TileGene = TileGenerator()
# [커스텀 가능] 맵 가로/세로 타일 수입니다. 타일 크기와 곱해 전체 월드 크기가 결정됩니다.
TileGene.generate_map(MAP_WIDTH_TILES, MAP_HEIGHT_TILES, seed_value=init_data["seed"])
MiniMapFont = pygame.font.Font(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "Font", "HeirofLightRegular.ttf"),
    18,
)
MiniMapRenderer = MiniMap(TileGene, MINIMAP_SIZE, MINIMAP_MARGIN, MiniMapFont)
MagneticZoneState = MagneticZone(MAP_WIDTH_TILES, MAP_HEIGHT_TILES, TileGene.tile_size)

# [커스텀 가능] HP 프레임의 화면 표시 크기입니다. 원본 비율을 유지해 한 번만 축소합니다.
HpBarFrame = pygame.transform.smoothscale(IML.HpBar, HP_FRAME_SIZE)

# 🕹️ [Player 클래스 인스턴스 생성 - 랜덤 스폰]
p_w = IML.Player.get_width()
p_h = IML.Player.get_height()

# [커스텀 가능] 안전 스폰을 찾을 타일 좌표 범위입니다.
safe_spawn = TileGene.find_safe_spawn(
    SPAWN_MIN_X,
    SPAWN_MAX_X,
    SPAWN_MIN_Y,
    SPAWN_MAX_Y,
    rng=random.SystemRandom(),
)
spawn_tile_x, spawn_tile_y = safe_spawn or (MAP_WIDTH_TILES // 2, MAP_HEIGHT_TILES // 2)
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
    "revive_token": 0,
    "revive_request": False,
    "revive_armed": False,
    
    # 발사한 총알 정보 (여러 개 가능)
    "bullets": [],      # [{"x": x, "y": y, "angle": angle}, ...]
        "hit_events": [],   # [{"target_id": id, "damage": damage, "hit_part": part}, ...]
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
supply_drops = []
next_supply_drop_at = pygame.time.get_ticks() + SUPPLY_DROP_INTERVAL_MS
pending_treasure_destroys = []
pending_furniture_destroys = []
pending_hit_events = []
screen_shake = 0
server_players = {}
kill_feed = []
spectator_players = {}
spectator_camera_x = 0
spectator_camera_y = 0
match_result = None
result_started_at = 0
game_start_banner_until = 0
show_hitboxes = True
local_stun_until = 0
zone_elapsed_ms = 0
particles = ParticleSystem()
last_effect_tick = pygame.time.get_ticks()
# 시야 밖을 검게 덮을 때 재사용하는 투명 레이어입니다.
vision_overlay = pygame.Surface((ScreenX, ScreenY), pygame.SRCALPHA)
# 방향과 모양이 크게 바뀔 때만 시야 폴리곤을 다시 계산합니다.
visibility_polygon_cache = {}
mouse_fire_hold = False
aim_lock_until = 0
aim_locked_pos = None
weapon_fire_until = 0
weapon_smoke_until = 0
preserve_magazine_after_chest = False
teleport_anchor = None
teleport_anchor_expires_at = 0

def spawn_supply_drop(now):
    """안전한 바닥 타일에 보급품을 하나 생성합니다."""
    # 벽이나 집 안에 생성되면 플레이어가 접근할 수 없으므로
    # TileGenerator가 찾은 이동 가능한 타일의 중앙에 배치합니다.
    spawn_tile = TileGene.find_safe_spawn(2, TileGene.map_width - 3, 2, TileGene.map_height - 3)
    if not spawn_tile:
        return
    tile_x, tile_y = spawn_tile
    reward_type = random.choice(SUPPLY_REWARD_TYPES)
    supply_drops.append({
        "x": (tile_x + 0.5) * TileGene.tile_size,
        "y": (tile_y + 0.5) * TileGene.tile_size,
        "type": reward_type,
        "warning_until": now + SUPPLY_DROP_WARNING_MS,
        "expires_at": now + SUPPLY_DROP_LIFETIME_MS,
    })


def apply_supply_reward(reward_type):
    """보급품 종류별 회복·버프 효과를 적용합니다."""
    # 보급품은 서버에 아이템 자체를 동기화하지 않고,
    # 획득한 클라이언트의 플레이어 상태에만 효과를 적용합니다.
    global send_data, heal_token, pending_heal_amount
    now = pygame.time.get_ticks()
    center_x, center_y = get_player_world_center(
        my_player.X, my_player.Y, IML.Player.get_width(), IML.Player.get_height()
    )
    if reward_type == "heal":
        my_player.Hp = min(my_player.MaxHp, my_player.Hp + SUPPLY_HEAL_AMOUNT)
        heal_token += 1
        pending_heal_amount += SUPPLY_HEAL_AMOUNT
        message = f"보급품 획득: 체력 +{SUPPLY_HEAL_AMOUNT}"
        color = (100, 255, 130)
    elif reward_type == "haste":
        global haste_until
        haste_until = max(haste_until, now) + SUPPLY_BUFF_DURATION_MS
        message = "보급품 획득: 이동속도 증가"
        color = (255, 240, 100)
    elif reward_type == "shield":
        global shield_until
        shield_until = max(shield_until, now) + SUPPLY_BUFF_DURATION_MS
        message = "보급품 획득: 보호막"
        color = (100, 220, 255)
    else:
        my_player.Hp = min(my_player.MaxHp, my_player.Hp + SUPPLY_HEAL_AMOUNT)
        heal_token += 1
        pending_heal_amount += SUPPLY_HEAL_AMOUNT
        message = "보급품 획득: 체력 회복"
        color = (100, 255, 130)
    particles.emit(center_x, center_y, color, count=24, speed=80, lifetime=600, size=6)
    return message


def collect_treasure(tile_position):
    global preserve_magazine_after_chest, system_message, pending_treasure_destroys
    if not tile_position or not TileGene.destroy_treasure(*tile_position):
        return False
    pending_treasure_destroys.append(tile_position)
    play_effect_sound(chest_sound, "chest_open.wav")
    available = [name for name in SKILL_BOOK if name not in owned_skills]
    if random.choice(CHEST_REWARD_TYPES) == "skill" and available:
        obtained_skill = random.choice(available)
        add_skill_to_inventory(obtained_skill)
        system_message = f"보물상자 획득: [{obtained_skill}] 스킬을 얻었습니다."
    else:
        weapon_state.magazine_ammo = weapon_state.config.magazine_size
        weapon_state.reloading = False
        preserve_magazine_after_chest = True
        system_message = "보물상자 획득: 탄창이 최대치로 회복되었습니다."
    return True


def use_revive_skill():
    """퀵슬롯에 장착된 부활의 차 스킬을 사망 순간 한 번 소모합니다."""
    global revive_token, system_message, send_data
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
    system_message = "부활의 차 스킬이 발동했습니다."
    return True


skill_sounds = {
    "달팽이 세개": load_effect_sound("skill_bomb.wav"),
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
weapon_state = WeaponState()
vision_shape_override = None

def MainView():
    global running, ScreenState, selected_game_mode, debug_mode, local_match, game_start_banner_until
    if weapon_state.weapon_id == "pistol":
        preview_image = IML.GetPistol()
    elif weapon_state.weapon_id == "sniper":
        preview_image = IML.GetSniper()
    elif weapon_state.weapon_id == "smg":
        preview_image = IML.GetGigwan()
    elif weapon_state.weapon_id == "knife":
        blade_frames = IML.GetBladeFrames()
        preview_image = blade_frames[0] if blade_frames else IML.GetShotGun()
    else:
        preview_image = IML.GetShotGun()
    button_rects = main_screen.draw_main(weapon_state.config.name, preview_image)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
            elif event.key == pygame.K_F10:
                debug_mode = True
                local_match = False
                selected_game_mode = GAME_MODE_DEBUG
                local_match = True
                game_start_banner_until = pygame.time.get_ticks() + 2000
                ScreenState = "GameView"
            elif event.key == pygame.K_SPACE:
                ScreenState = "NameInputView"
            elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6, pygame.K_7):
                if event.key == pygame.K_7:
                    select_weapon(random.choice(WEAPON_KEYS[:-1]))
                    continue
                select_weapon(dict(zip(
                    (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6),
                    WEAPON_KEYS,
                ))[event.key])
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if button_rects["profile"].collidepoint(event.pos):
                ScreenState = "ModeSelectView"


def ModeSelectView():
    global running, ScreenState, selected_game_mode, debug_mode, local_match, game_start_banner_until
    button_rects = main_screen.draw_mode_select()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                pygame.key.stop_text_input()
                ScreenState = "MainView"
            elif event.key == pygame.K_F10:
                debug_mode = True
                local_match = False
                selected_game_mode = GAME_MODE_NORMAL
                ScreenState = "LoadingView"
            elif event.key == pygame.K_1:
                debug_mode = False
                selected_game_mode = GAME_MODE_NORMAL
                local_match = False
                ScreenState = "LoadingView"
            elif event.key == pygame.K_2:
                debug_mode = True
                local_match = False
                selected_game_mode = GAME_MODE_DEBUG
                ScreenState = "LoadingView"
            elif event.key == pygame.K_3:
                ScreenState = "SpectatorPromptView"
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if button_rects["normal"].collidepoint(event.pos):
                debug_mode = False
                selected_game_mode = GAME_MODE_NORMAL
                local_match = False
                ScreenState = "LoadingView"
            elif button_rects["debug"].collidepoint(event.pos):
                debug_mode = True
                local_match = True
                selected_game_mode = GAME_MODE_DEBUG
                game_start_banner_until = pygame.time.get_ticks() + 2000
                ScreenState = "GameView"


def NameInputView():
    global running, ScreenState, player_name
    pygame.key.start_text_input()
    main_screen.draw_name_input(player_name)
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
            elif event.key == pygame.K_RETURN:
                player_name = player_name.strip() or "플레이어"
                pygame.key.stop_text_input()
                ScreenState = "ModeSelectView"


def SpectatorPromptView():
    global running, ScreenState, spectator_players
    display.fill((10, 15, 24))
    title = GuiFont.render("게임이 진행 중입니다", True, (255, 225, 140))
    prompt = GuiFont.render("관전으로 참여하시겠습니까?", True, (240, 245, 255))
    guide = GuiFont.render("Space: 관전 시작   Esc: 돌아가기", True, (180, 205, 230))
    display.blit(title, title.get_rect(center=(ScreenX // 2, 360)))
    display.blit(prompt, prompt.get_rect(center=(ScreenX // 2, 440)))
    display.blit(guide, guide.get_rect(center=(ScreenX // 2, 530)))
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                ScreenState = "ModeSelectView"
            elif event.key == pygame.K_SPACE:
                spectator_players = {}
                ScreenState = "SpectatorView"


def LoadingView():
    global running, ScreenState, lobby_status, last_lobby_request_at, local_match, game_start_banner_until
    if debug_mode:
        owned_skills.update(SKILL_BOOK)
        refresh_skill_inventory()
    now = pygame.time.get_ticks()
    if now - last_lobby_request_at >= 100:
        client.sendall(pickle.dumps({
            "type": "lobby_join",
            "mode": selected_game_mode,
            "debug_enabled": debug_mode,
            "name": player_name,
        }))
        response = pickle.loads(client.recv(4096))
        if response.get("type") == "lobby_status":
            lobby_status = response
        last_lobby_request_at = now

    main_screen.draw_loading(
        lobby_status,
        selected_game_mode,
        MAX_PLAYERS,
        GAME_MODE_DEBUG,
    )

    if lobby_status.get("started") and lobby_status.get("accepted", True):
        game_start_banner_until = pygame.time.get_ticks() + 2000
        ScreenState = "GameView"
    elif lobby_status.get("accepted") is False and not debug_mode:
        ScreenState = "SpectatorPromptView"

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                ScreenState = "ModeSelectView"
            elif event.key == pygame.K_SPACE and not lobby_status.get("started"):
                client.sendall(pickle.dumps({
                    "type": "lobby_ready",
                    "ready": True,
                }))
                response = pickle.loads(client.recv(NETWORK_BUFFER_SIZE))
                if response.get("type") == "lobby_status":
                    lobby_status = response


def GameOverView():
    global running, ScreenState, result_started_at
    if not result_started_at:
        result_started_at = pygame.time.get_ticks()
    _draw_result_screen("패배", (220, 50, 50), pygame.time.get_ticks() - result_started_at)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            running = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
            ScreenState = "MainView"


def VictoryView():
    global running, ScreenState, result_started_at
    if not result_started_at:
        result_started_at = pygame.time.get_ticks()
    _draw_result_screen("승리", (255, 220, 80), pygame.time.get_ticks() - result_started_at)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            running = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
            ScreenState = "MainView"


def _draw_result_screen(title_text, color, elapsed):
    pulse = 1.0 + 0.06 * math.sin(elapsed * 0.006)
    fade = min(210, 80 + elapsed // 8)
    overlay = pygame.Surface((ScreenX, ScreenY), pygame.SRCALPHA)
    overlay.fill((*color, fade))
    display.blit(overlay, (0, 0))
    pygame.draw.circle(
        display,
        (*color, 80),
        (ScreenX // 2, ScreenY // 2 - 50),
        max(40, round(150 * pulse)),
        5,
    )
    title = GuiFont.render(title_text, True, (255, 255, 255))
    title = pygame.transform.smoothscale(
        title,
        (max(1, round(title.get_width() * pulse)), max(1, round(title.get_height() * pulse))),
    )
    display.blit(title, title.get_rect(center=(ScreenX // 2, ScreenY // 2 - 60)))
    guide = GuiFont.render("ESC를 눌러 종료하세요", True, (255, 255, 255))
    display.blit(guide, guide.get_rect(center=(ScreenX // 2, ScreenY // 2 + 70)))


def SpectatorView():
    global running, ScreenState, spectator_players, spectator_camera_x, spectator_camera_y
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            ScreenState = "ModeSelectView"
            return

    client.sendall(pickle.dumps({"type": "spectator_join"}))
    response = client.recv(NETWORK_BUFFER_SIZE)
    if response:
        spectator_players = pickle.loads(response)
    if not spectator_players:
        display.fill((10, 15, 24))
        waiting = GuiFont.render("진행 중인 게임이 없습니다", True, (230, 235, 245))
        display.blit(waiting, waiting.get_rect(center=(ScreenX // 2, ScreenY // 2)))
        guide = GuiFont.render("ESC: 나가기", True, (180, 200, 220))
        display.blit(guide, guide.get_rect(center=(ScreenX // 2, ScreenY // 2 + 55)))
        return

    tracked_id = next(iter(spectator_players))
    tracked = spectator_players[tracked_id]
    target_x = tracked.get("posX", 0) + 36
    target_y = tracked.get("posY", 0) + 36
    spectator_camera_x, spectator_camera_y = get_camera_target(
        target_x, target_y, ScreenX, ScreenY, camera_zoom
    )
    spectator_camera_x, spectator_camera_y = TileGene.clamp_camera(
        spectator_camera_x, spectator_camera_y, ScreenX, ScreenY, camera_zoom
    )
    display.fill((0, 0, 0))
    TileGene.draw(display, spectator_camera_x, spectator_camera_y, camera_zoom)
    title = GuiFont.render("관전모드  |  ESC: 나가기", True, (255, 235, 150))
    display.blit(title, (30, 25))
    for player_id, player_info in spectator_players.items():
        image = IML.Player
        screen_x, screen_y = world_to_screen(
            player_info.get("posX", 0), player_info.get("posY", 0),
            spectator_camera_x, spectator_camera_y, camera_zoom,
        )
        display.blit(image, (round(screen_x), round(screen_y)))
        label = GuiFont.render(
            str(player_info.get("name", f"P{player_id}")),
            True,
            (255, 230, 160),
        )
        display.blit(label, label.get_rect(midbottom=(round(screen_x + 36), round(screen_y - 5))))


def handle_quit(_event, _mouse_pos):
    global running
    running = False


def activate_quick_slot(key):
    global system_message, vision_shape_override, vision_skill_until, shield_until, haste_until, stealth_until, stealth_token, teleport_anchor, teleport_anchor_expires_at, wards
    global pending_hit_events
    key_name = pygame.key.name(key).upper()
    slot = next((slot for slot in quick_slots if slot.key_name == key_name), None)
    if not slot or not slot.assigned_skill:
        system_message = f"[{key_name}] 슬롯이 비어있습니다."
        return

    skill_name = slot.assigned_skill
    if skill_name == "부활의 차":
        system_message = "부활의 차는 장착 중 사망하면 자동 발동합니다."
        return
    now = pygame.time.get_ticks()
    if skill_name == "텔포" and teleport_anchor is None and now < skill_cooldowns.get(skill_name, 0):
        remain = (skill_cooldowns[skill_name] - now) / 1000
        system_message = f"텔포 재사용 대기: {remain:.1f}초"
        return
    if skill_name != "텔포" and now < skill_cooldowns.get(skill_name, 0):
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
    if skill_name == "달팽이 세개":
        target_x, target_y = screen_to_world(*pygame.mouse.get_pos(), CameraPosX, CameraPosY, camera_zoom)
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
        active_bombs.append({"x": target_x, "y": target_y, "explode_at": now + BOMB_DELAY_MS})
        particles.emit(target_x, target_y, (255, 190, 40), count=18, speed=55, lifetime=500, size=6)
        particles.ring(target_x, target_y, (255, 220, 80), radius=35, lifetime=450)
        system_message = "폭탄을 설치했습니다."
    elif skill_name == "매의 눈":
        vision_shape_override = VISION_CIRCLE
        vision_skill_until = now + VISION_DURATION_MS
        particles.ring(
            my_player.X + my_player.rect.width / 2,
            my_player.Y + my_player.rect.height / 2,
            (120, 220, 255), count=24, radius=90, lifetime=650, size=4,
        )
        system_message = "3초 동안 원형으로 넓게 봅니다."
    elif skill_name == "보호막":
        shield_until = now + SHIELD_DURATION_MS
        particles.ring(
            my_player.X + my_player.rect.width / 2,
            my_player.Y + my_player.rect.height / 2,
            (100, 220, 255), count=28, radius=55, lifetime=700, size=5,
        )
        system_message = "5초 동안 피해를 받지 않습니다."
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
        system_message = "4.5초 동안 적에게 완전히 보이지 않습니다."
    elif skill_name == "와드":
        target_x, target_y = screen_to_world(*pygame.mouse.get_pos(), CameraPosX, CameraPosY, camera_zoom)
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
    elif skill_name == "텔포":
        if teleport_anchor is None:
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
            particles.emit(target_x, target_y, (180, 255, 180), count=30, speed=90, lifetime=700, size=6)
            particles.ring(target_x, target_y, (180, 255, 180), count=20, radius=38, lifetime=900, size=5)
            system_message = "시전자 위치에 텔포석상을 설치했습니다. 5초 안에 다시 누르세요."
        else:
            old_x = my_player.X + my_player.rect.width / 2
            old_y = my_player.Y + my_player.rect.height / 2
            my_player.X = teleport_anchor[0] - my_player.rect.width / 2
            my_player.Y = teleport_anchor[1] - my_player.rect.height / 2
            my_player.rect.topleft = (round(my_player.X), round(my_player.Y))
            my_player._update_hitboxes()
            particles.emit(old_x, old_y, (180, 255, 180), count=24, speed=80, lifetime=600, size=5)
            particles.emit(teleport_anchor[0], teleport_anchor[1], (180, 255, 180), count=30, speed=90, lifetime=700, size=6)
            system_message = "텔레포트로 이동했습니다. 5초 후 석상이 사라집니다."

def select_weapon(weapon_id):
    global system_message, vision_shape_override, main_weapon_id
    if ScreenState != "GameView":
        main_weapon_id = weapon_id
    elif not debug_mode and weapon_id not in (main_weapon_id, "knife"):
        system_message = "게임 중에는 선택한 총과 칼만 사용할 수 있습니다."
        return
    if weapon_state.select(weapon_id):
        vision_shape_override = None
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
    key_name = pygame.key.name(key).upper()
    slot = next((slot for slot in quick_slots if slot.key_name == key_name), None)
    if slot and slot.assigned_skill:
        activate_quick_slot(key)
    else:
        reload_weapon()


def remove_ward_at_cursor():
    """마우스 주변의 자기 와드 하나를 제거합니다."""
    global system_message
    target_x, target_y = screen_to_world(
        *pygame.mouse.get_pos(), CameraPosX, CameraPosY, camera_zoom
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
    global inventory_open, dragging_skill, debug_mode, system_message, show_hitboxes
    weapon_id = None
    if event.key == pygame.K_1:
        weapon_id = main_weapon_id
    elif event.key == pygame.K_2:
        weapon_id = "knife"
    elif ScreenState != "GameView":
        weapon_id = dict(zip(
            (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6),
            WEAPON_KEYS,
        )).get(event.key)
    if weapon_id:
        select_weapon(weapon_id)
        return

    if event.key == pygame.K_F10:
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

    key_actions = {
        pygame.K_ESCAPE: lambda _key: handle_quit(None, None),
        pygame.K_i: lambda _key: toggle_inventory(),
        pygame.K_v: lambda _key: cycle_vision_shape(),
        pygame.K_q: lambda _key: activate_quick_slot(_key),
        pygame.K_e: lambda _key: activate_quick_slot(_key),
        pygame.K_t: lambda _key: activate_quick_slot(_key),
        pygame.K_r: lambda _key: reload_weapon(),
        pygame.K_f: lambda _key: activate_skill_or_reload(_key),
        pygame.K_x: lambda _key: remove_ward_at_cursor(),
    }
    key_actions.get(event.key, activate_quick_slot)(event.key)


def toggle_inventory():
    global inventory_open, dragging_skill
    inventory_open = not inventory_open
    dragging_skill = None


def cycle_vision_shape():
    """V 키로 현재 시야 모양을 순서대로 변경합니다."""
    global vision_shape_index, vision_shape_override, system_message
    if ScreenState == "GameView" and not debug_mode:
        system_message = "시야 변경은 디버그 모드에서만 사용할 수 있습니다."
        return
    vision_shape_index = (vision_shape_index + 1) % len(vision_shapes)
    vision_shape_override = vision_shapes[vision_shape_index]
    shape_name = vision_shape_override
    system_message = f"시야 모양: {shape_name}" 


def fire_knife():
    """칼 공격: 근거리 범위 내의 모든 적에게 데미지를 주고, 보물상자도 파괴합니다."""
    global screen_shake, system_message, knife_attack_until
    global training_dummy, damage_numbers
    config = weapon_state.config
    knife_attack_until = pygame.time.get_ticks() + MELEE_ATTACK_DURATION_MS

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
        if int(p_id) == my_id:
            continue

        enemy_center_x = p_info["posX"] + IML.Player.get_width() / 2
        enemy_center_y = p_info["posY"] + IML.Player.get_height() / 2

        distance = math.sqrt((center_x - enemy_center_x)**2 + (center_y - enemy_center_y)**2)
        if distance <= knife_range:
            attacked_count += 1
            pending_hit_events.append({
                "target_id": int(p_id),
                "damage": config.damage,
                "hit_part": "body",
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
            if math.hypot(center_x - tile_center[0], center_y - tile_center[1]) > knife_range:
                continue
            if TileGene.destroy_furniture(tile_x, tile_y):
                pending_furniture_destroys.append((tile_x, tile_y))
                destroyed_furniture_count += 1

    if debug_mode and training_dummy is not None and training_dummy.Hp > 0:
        dummy_center_x = training_dummy.rect.centerx
        dummy_center_y = training_dummy.rect.centery
        if math.hypot(center_x - dummy_center_x, center_y - dummy_center_y) <= knife_range:
            training_dummy.Hp = max(0, training_dummy.Hp - config.damage)
            damage_numbers.append({
                "x": dummy_center_x,
                "y": training_dummy.rect.top,
                "damage": config.damage,
                "color": (255, 255, 255),
                "started_at": pygame.time.get_ticks(),
                "lifetime": DAMAGE_TEXT_LIFETIME_MS,
            })
            if training_dummy.Hp <= 0:
                training_dummy.respawn_at = pygame.time.get_ticks() + TRAINING_DUMMY_RESPAWN_MS
                kill_feed.append({
                    "killer_id": my_id,
                    "target_id": "더미",
                    "weapon_id": weapon_state.weapon_id,
                    "started_at": pygame.time.get_ticks(),
                })
            attacked_count += 1

    weapon_state.consume_round()
    screen_shake = min(SCREEN_SHAKE_MAX, screen_shake + MELEE_SHAKE)

    if attacked_count > 0:
        particles.emit(center_x, center_y, (255, 80, 80), count=18, speed=100, lifetime=400, size=5)
        system_message = f"칼 공격! {config.damage} 데미지 × {attacked_count}명"
        if destroyed_furniture_count:
            system_message += f", 가구 {destroyed_furniture_count}개 파괴"
    else:
        system_message = f"칼 휘둘렀습니다. (데미지: {config.damage})"
        if destroyed_furniture_count:
            system_message += f" 가구 {destroyed_furniture_count}개 파괴"


def fire_stun_bullet():
    global bullets, screen_shake, system_message
    if not weapon_state.can_fire():
        system_message = "기절탄을 발사할 수 없습니다."
        return False
    center_x, center_y = get_player_world_center(
        my_player.X, my_player.Y, IML.Player.get_width(), IML.Player.get_height()
    )
    mouse_x, mouse_y = pygame.mouse.get_pos()
    target_world_x, target_world_y = screen_to_world(
        mouse_x, mouse_y, AimCameraPosX, AimCameraPosY, camera_zoom
    )
    player_screen = get_player_screen_center(
        my_player.X, my_player.Y, IML.Player.get_width(), IML.Player.get_height(),
        CameraPosX, CameraPosY, camera_zoom,
    )
    angle = math.atan2(target_world_y - center_y, target_world_x - center_x)
    bullet = Bullet(4, damage=DEFAULT_BULLET_DAMAGE, owner_id=my_id, weapon_id=weapon_state.weapon_id, stun_ms=STUN_DURATION_MS)
    bullet.launch(
        center_x, center_y,
        center_x + math.cos(angle) * BULLET_TARGET_DISTANCE,
        center_y + math.sin(angle) * BULLET_TARGET_DISTANCE,
        speed=weapon_state.config.bullet_speed,
        hold_ms=0,
    )
    bullet.just_fired = True
    bullets.append(bullet)
    weapon_state.consume_round()
    system_message = "기절탄을 발사했습니다."
    return True


def fire_bullet():
    global bullets, screen_shake, system_message, aim_lock_until, aim_locked_pos
    global weapon_fire_until, weapon_smoke_until
    config = weapon_state.config

    if weapon_state.is_reloading_now():
        system_message = "재장전 중입니다."
        return
    
    # 칼 공격 특수 처리
    if not config.projectile:
        if not weapon_state.can_fire():
            system_message = f"{config.name} 공격은 아직 준비 중입니다."
            return
        fire_knife()
        return
    
    if not weapon_state.can_fire():
        if config.projectile and weapon_state.magazine_ammo == 0:
            reload_weapon()
        return

    center_x, center_y = get_player_world_center(
        my_player.X,
        my_player.Y,
        IML.Player.get_width(),
        IML.Player.get_height(),
    )
    current_mouse_pos = pygame.mouse.get_pos()
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
            owner_id=my_id,
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
    global dragging_skill, mouse_fire_hold
    if event.button != 1:
        return

    available_items = inventory_items if inventory_open else ()
    dragging_skill = next(
        (
            item.skill_name
            for item in available_items
            if item.is_owned and item.rect.collidepoint(mouse_pos)
        ),
        None,
    )
    if dragging_skill is None:
        mouse_fire_hold = weapon_state.config.automatic
        fire_bullet()


def handle_mouse_up(event, mouse_pos):
    global dragging_skill, system_message, mouse_fire_hold
    if event.button != 1:
        mouse_fire_hold = False
        return
    mouse_fire_hold = False
    if not dragging_skill:
        return

    slot = next(
        (slot for slot in quick_slots if slot.rect.collidepoint(mouse_pos)),
        None,
    )
    if slot:
        skill = SKILL_BOOK[dragging_skill]
        if assign_skill_to_quick_slot(slot, dragging_skill):
            system_message = (
                f"⌨️ [{slot.key_name}] 슬롯에 [{skill.name}] 장착! "
                f"(공격력: {skill.Power})"
            )
        else:
            system_message = f"[{skill.name}]은 이미 다른 퀵슬롯에 장착되어 있습니다."
    dragging_skill = None


def handle_game_events():
    mouse_pos = pygame.mouse.get_pos()
    event_handlers = {
        pygame.QUIT: handle_quit,
        pygame.KEYDOWN: handle_key_event,
        pygame.MOUSEBUTTONDOWN: handle_mouse_down,
        pygame.MOUSEBUTTONUP: handle_mouse_up,
    }
    for event in pygame.event.get():
        handler = event_handlers.get(event.type)
        if handler:
            handler(event, mouse_pos)


def GameView():
    global running, ScreenState, CameraPosX, CameraPosY, AimCameraPosX, AimCameraPosY, Weapon_Angle, Weapon_Pos, camera_fov, camera_zoom, match_result, local_stun_until, zone_elapsed_ms, game_start_banner_until
    global screen_shake, server_players, bullets, remote_bullets, processed_bullet_events, processed_damage_event_ids, MousePos, system_message, kill_feed, main_weapon_id
    global vision_shape_override, vision_skill_until, shield_until, haste_until
    global active_bombs, active_explosions, supply_drops, next_supply_drop_at, pending_treasure_destroys, pending_furniture_destroys, pending_hit_events, pending_heal_amount, wards, active_rune_tile, rune_alerts
    global visibility_polygon_cache, mouse_fire_hold, last_effect_tick, preserve_magazine_after_chest
    global aim_lock_until, aim_locked_pos, weapon_fire_until
    global teleport_anchor, teleport_anchor_expires_at
    global training_dummy, damage_numbers, easter_egg_found, easter_egg_flash_until

    MousePos = pygame.mouse.get_pos()
    if my_player.Hp <= 0 and not use_revive_skill():
        ScreenState = "GameOver"
        return
    now = pygame.time.get_ticks()
    revived_after_server_update = False
    if debug_mode and training_dummy is None:
        respawn_training_dummy()
    damage_numbers = [
        number for number in damage_numbers
        if now - number["started_at"] < number["lifetime"]
    ]
    if teleport_anchor is not None and now >= teleport_anchor_expires_at:
        teleport_anchor = None
        teleport_anchor_expires_at = 0
        skill_cooldowns["텔포"] = now + TELEPORT_COOLDOWN_MS
        system_message = "텔포석상이 사라졌습니다. 15초 후 다시 사용할 수 있습니다."
    handle_game_events()

    if mouse_fire_hold and weapon_state.config.automatic and weapon_state.can_fire():
        fire_bullet()

    Weapon_Pos = pygame.mouse.get_pos()

    if now >= local_stun_until:
        dash_requested = (
            weapon_state.weapon_id == "knife"
            and pygame.mouse.get_pressed(3)[2]
        )
        my_player.handle_input(dash_requested)
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
    base_speed = PLAYER_HASTE_SPEED if now < haste_until else PLAYER_NORMAL_SPEED
    knife_speed_bonus = 3 if weapon_state.weapon_id == "knife" else 0
    player_center_x, player_center_y = get_player_world_center(
        my_player.X, my_player.Y, IML.Player.get_width(), IML.Player.get_height()
    )
    effective_base_speed = base_speed + knife_speed_bonus
    my_player.normal_speed = effective_base_speed
    my_player.sprint_speed = PLAYER_SPRINT_SPEED + knife_speed_bonus
    my_player.dash_speed = PLAYER_DASH_SPEED + knife_speed_bonus

    if now >= next_supply_drop_at:
        if len(supply_drops) < SUPPLY_DROP_MAX and random.random() < SUPPLY_DROP_CHANCE:
            spawn_supply_drop(now)
        next_supply_drop_at = now + SUPPLY_DROP_INTERVAL_MS

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
        if now >= supply["expires_at"]:
            continue
        if player_rect.colliderect(supply_rect):
            # 아이템을 획득한 순간 목록에서 제거해 한 번만 보상합니다.
            system_message = apply_supply_reward(supply["type"])
            continue
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
        for p_id, p_info in server_players.items():
            distance = math.hypot(p_info["posX"] - bomb["x"], p_info["posY"] - bomb["y"])
            if distance <= BOMB_RADIUS:
                pending_hit_events.append({
                    "target_id": int(p_id),
                    "damage": BOMB_DAMAGE,
                    "hit_part": "body",
                })
    active_bombs = pending_bombs
    active_explosions = [explosion for explosion in active_explosions if now < explosion["until"]]

    # ★ [정리] 서버 데이터 동기화 - 필요한 움직임 데이터만 전송
    send_data["posX"] = my_player.X
    send_data["posY"] = my_player.Y
    send_data["hp"] = my_player.Hp
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
    in_bush = TileGene.is_in_bush(player_world_x, player_world_y)
    send_data["stealth"] = now < stealth_until or in_bush
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
    send_data["hit_events"] = list(pending_hit_events)
    
    # ★ [정리] 총알 정보 - 이번 프레임에서 새로 발사된 총알만 전송
    send_data["bullets"] = [
        {
            "x": bullet.x,
            "y": bullet.y,
            "angle": bullet.angle,
            "weapon_id": bullet.weapon_id,
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
        client.send(pickle.dumps(send_data))
        server_raw = client.recv(NETWORK_BUFFER_SIZE)
        if server_raw:
            server_players = pickle.loads(server_raw)
            seen_kills = {
                (item.get("killer_id"), item.get("target_id"), item.get("weapon_id"))
                for item in kill_feed
            }
            for player_snapshot in server_players.values():
                for kill_event in player_snapshot.get("kill_events", []):
                    key = (kill_event.get("killer_id"), kill_event.get("target_id"), kill_event.get("weapon_id"))
                    if key not in seen_kills:
                        kill_feed.append({**kill_event, "started_at": now})
            kill_feed = [event for event in kill_feed if now - event["started_at"] < 5000][-5:]
            for player_snapshot in server_players.values():
                for damage_event in player_snapshot.get("damage_events", []):
                    event_id = damage_event.get("event_id")
                    if event_id in processed_damage_event_ids:
                        continue
                    processed_damage_event_ids.add(event_id)
                    target_id = damage_event.get("target_id")
                    target = server_players.get(target_id)
                    if target is None and str(target_id) == str(my_id):
                        target = {
                            "posX": my_player.X,
                            "posY": my_player.Y,
                        }
                    if target is not None:
                        damage_numbers.append({
                            "x": target.get("posX", my_player.X) + my_player.rect.width / 2,
                            "y": target.get("posY", my_player.Y),
                            "damage": damage_event.get("damage", 0),
                            "color": (255, 235, 100) if damage_event.get("hit_part") == "head" else (255, 255, 255),
                            "started_at": now,
                            "lifetime": DAMAGE_TEXT_LIFETIME_MS,
                        })
            synchronized_treasures = set()
            synchronized_furniture = set()
            synchronized_rune_alerts = []
            for player_snapshot in server_players.values():
                synchronized_treasures.update(
                    tuple(treasure) for treasure in player_snapshot.get("destroyed_treasures", [])
                )
                synchronized_furniture.update(
                    tuple(furniture) for furniture in player_snapshot.get("destroyed_furniture", [])
                )
            own_snapshot = server_players.get(my_id)
            if own_snapshot:
                synchronized_rune_alerts = own_snapshot.get("rune_alerts", [])
            for tile_x, tile_y in synchronized_treasures:
                TileGene.destroy_treasure(tile_x, tile_y)
            for tile_x, tile_y in synchronized_furniture:
                TileGene.destroy_furniture(tile_x, tile_y)
            rune_alerts = synchronized_rune_alerts
            pending_treasure_destroys.clear()
            pending_furniture_destroys.clear()
            pending_hit_events.clear()
            pending_heal_amount = 0
            send_data["revive_request"] = False
            zone_elapsed_ms = max(
                zone_elapsed_ms,
                max(0, int(server_players.get(my_id, {}).get("zone_elapsed_ms", 0))),
            )
            if own_snapshot:
                my_player.Hp = own_snapshot.get("hp", my_player.Hp)
                local_stun_until = now + own_snapshot.get("stun_ms_remaining", 0)
                weapon_id = own_snapshot.get("weapon_id", weapon_state.weapon_id)
                if weapon_id in WEAPONS:
                    weapon_state.weapon_id = weapon_id
                if preserve_magazine_after_chest:
                    preserve_magazine_after_chest = False
                else:
                    weapon_state.magazine_ammo = own_snapshot.get(
                        "magazine_ammo", weapon_state.magazine_ammo
                    )
                weapon_state.reserve_ammo = own_snapshot.get(
                    "reserve_ammo", weapon_state.reserve_ammo
                )
                if my_player.Hp <= 0:
                    revived_after_server_update = use_revive_skill()
            own_winner_id = own_snapshot.get("winner_id") if own_snapshot else None
            if own_winner_id is not None and not revived_after_server_update:
                winner_id = own_winner_id
                match_result = "victory" if int(winner_id) == my_id else "defeat"
                ScreenState = "Victory" if match_result == "victory" else "GameOver"
                return
            # ★ [정리] 서버에서 받은 플레이어 데이터 구조:
            # server_players[id] = {
            #     "posX": x,          # 상대 플레이어 위치
            #     "posY": y,
            #     "angle": angle,     # 상대 플레이어 무기 각도
            #     "hp": hp,           # 상대 플레이어 체력
            #     "bullets": [...]    # 상대가 발사한 총알들
            # }
    except Exception as e:
        print(f"네트워크 통신 오류: {e}")

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
    zone_enabled = not debug_mode and selected_game_mode == GAME_MODE_NORMAL
    if zone_enabled:
        MagneticZoneState.draw(display, CameraPosX, CameraPosY, camera_zoom, zone_elapsed_ms)

    player_world_x, player_world_y = get_player_world_center(my_player.X, my_player.Y, IML.Player.get_width(), IML.Player.get_height())
    if debug_mode and not easter_egg_found:
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
                if tile_type == 9 and pygame.time.get_ticks() >= bullet.reflect_until:
                    stone_center = pygame.Vector2(
                        (tile_x + 0.5) * TileGene.tile_size,
                        (tile_y + 0.5) * TileGene.tile_size,
                    )
                    bullet_center = pygame.Vector2(bullet.rect.center)
                    bullet.reflect(
                        horizontal=abs(bullet_center.x - stone_center.x) > abs(bullet_center.y - stone_center.y),
                        vertical=abs(bullet_center.y - stone_center.y) >= abs(bullet_center.x - stone_center.x),
                    )
                    particles.emit(bullet.x, bullet.y, (190, 200, 215), count=10, speed=55, lifetime=280, size=3)
                else:
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
            destroyed_treasure = TileGene.destroy_treasure_at(bullet.rect)
            if destroyed_treasure:
                # 보물상자 타일은 먼저 제거하고, 이 클라이언트에게 보상을 지급합니다.
                # destroyed_treasures 동기화는 다른 클라이언트의 맵에서도 상자를 제거합니다.
                pending_treasure_destroys.append(destroyed_treasure)
                play_effect_sound(chest_sound, "chest_open.wav")
                available = [name for name in SKILL_BOOK if name not in owned_skills]
                chest_reward = random.choice(CHEST_REWARD_TYPES)
                if chest_reward == "skill" and available:
                    obtained_skill = random.choice(available)
                    add_skill_to_inventory(obtained_skill)
                    system_message = f"보물상자: [{obtained_skill}] 인벤토리에 저장"
                else:
                    weapon_state.magazine_ammo = weapon_state.config.magazine_size
                    weapon_state.reloading = False
                    preserve_magazine_after_chest = True
                    system_message = "보물상자: 탄창이 최대치로 회복되었습니다."
                bullet.is_active = False
                continue
            for p_id, p_info in server_players.items():
                if int(p_id) == my_id:
                    continue
                head, body = Player.hitboxes_for_position(
                    p_info["posX"], p_info["posY"], IML.Player.get_width(), IML.Player.get_height()
                )
                if head.colliderect(bullet.rect) or body.colliderect(bullet.rect):
                    hit_part = "head" if head.colliderect(bullet.rect) else "body"
                    pending_hit_events.append({
                        "target_id": int(p_id),
                        "damage": bullet.damage,
                        "hit_part": hit_part,
                        "stun_ms": bullet.stun_ms,
                    })
                    bullet.is_active = False
                    particles.emit(
                        bullet.x, bullet.y, (255, 70, 70),
                        count=12, speed=65, lifetime=350, size=4,
                    )
                    break
            if bullet.is_active and debug_mode and training_dummy is not None:
                hit_part = training_dummy.check_bullet_hit(bullet.rect, bullet.damage)
                if hit_part:
                    dealt_damage = bullet.damage * (HEADSHOT_DAMAGE_MULTIPLIER if hit_part == "head" else 1)
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
    if debug_mode and training_dummy is not None and training_dummy.Hp <= 0 and now >= training_dummy.respawn_at:
        respawn_training_dummy()

    # 서버 스냅샷에는 같은 발사 이벤트가 모든 플레이어 항목에 포함될 수
    # 있으므로 event_id 기준으로 한 번만 생성합니다.
    for p_info in server_players.values():
        for bullet_info in p_info.get("bullets", []):
            event_id = bullet_info.get("event_id")
            if event_id in processed_bullet_events:
                continue
            processed_bullet_events.add(event_id)
            if bullet_info.get("owner_id") == my_id:
                continue
            weapon_id = bullet_info.get("weapon_id", DEFAULT_WEAPON_ID)
            config = WEAPONS.get(weapon_id, WEAPONS[DEFAULT_WEAPON_ID])
            enemy_bullet = Bullet(
                config.bullet_size,
                damage=config.damage,
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
            remote_bullets.append(enemy_bullet)

    for bullet in remote_bullets:
        bullet.update()
        if bullet.is_active:
            destructible = TileGene.destructible_collision(bullet.collision_rect)
            if destructible:
                tile_x, tile_y, tile_type = destructible
                if tile_type == 9 and pygame.time.get_ticks() >= bullet.reflect_until:
                    stone_center = pygame.Vector2(
                        (tile_x + 0.5) * TileGene.tile_size,
                        (tile_y + 0.5) * TileGene.tile_size,
                    )
                    bullet_center = pygame.Vector2(bullet.rect.center)
                    bullet.reflect(
                        horizontal=abs(bullet_center.x - stone_center.x) > abs(bullet_center.y - stone_center.y),
                        vertical=abs(bullet_center.y - stone_center.y) >= abs(bullet_center.x - stone_center.x),
                    )
                elif TileGene.destroy_furniture(tile_x, tile_y):
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
                    "target_id": my_id,
                    "damage": bullet.damage,
                    "hit_part": hit_part,
                    "stun_ms": bullet.stun_ms,
                })
                bullet.is_active = False
    remote_bullets = [b for b in remote_bullets if b.is_active]

    if my_player.Hp <= 0 and not use_revive_skill():
        ScreenState = "GameOver"
        return

    visible_player_ids = set()
    # 다른 플레이어 그리기
    for p_id, p_info in server_players.items():
        if int(p_id) == my_id:
            continue

        other_world_x, other_world_y = get_player_world_center(
            p_info["posX"],
            p_info["posY"],
            IML.Player.get_width(),
            IML.Player.get_height(),
        )
        close_to_bush = math.hypot(
            other_world_x - player_world_x,
            other_world_y - player_world_y,
        ) <= MAP_BUSH_VISIBLE_DISTANCE
        if p_info.get("stealth", False):
            continue

        bush_fov_bonus = (
            BUSH_VISION_FOV_BONUS
            if p_info.get("in_bush", False) and close_to_bush
            else 0
        )
        if not is_visible(other_world_x, other_world_y, bush_fov_bonus):
            continue
        visible_player_ids.add(int(p_id))

        other_screen_x, other_screen_y = world_to_screen(p_info["posX"], p_info["posY"], CameraPosX, CameraPosY, camera_zoom)
        stun_offset_x = round(math.sin(now * 0.08) * 8) if p_info.get("stun_ms_remaining", 0) > 0 else 0
        other_image = IML.Player if camera_zoom == 1.0 else pygame.transform.scale(
            IML.Player, (round(IML.Player.get_width() * camera_zoom), round(IML.Player.get_height() * camera_zoom))
        )
        display.blit(other_image, (other_screen_x + stun_offset_x, other_screen_y))

        other_center_x, other_center_y = get_player_screen_center(p_info["posX"], p_info["posY"], IML.Player.get_width(), IML.Player.get_height(), CameraPosX, CameraPosY, camera_zoom)
        other_weapon_image = IML.GetWeaponImage(p_info.get("weapon_id", DEFAULT_WEAPON_ID))
        if p_info.get("weapon_id") == "pistol":
            other_weapon_image = pygame.transform.flip(other_weapon_image, True, False)
        other_gun = other_weapon_image if camera_zoom == 1.0 else pygame.transform.scale(
            other_weapon_image, (round(other_weapon_image.get_width() * camera_zoom), round(other_weapon_image.get_height() * camera_zoom))
        )
        other_rotated_gun = pygame.transform.rotate(other_gun, -p_info["angle"])
        other_gun_rect = other_rotated_gun.get_rect()
        other_gun_rect.center = (other_center_x, other_center_y)
        display.blit(other_rotated_gun, other_gun_rect)

    if debug_mode and training_dummy is not None and training_dummy.Hp > 0:
        dummy_screen_x, dummy_screen_y = world_to_screen(
            training_dummy.X, training_dummy.Y, CameraPosX, CameraPosY, camera_zoom
        )
        dummy_image = training_dummy.image if camera_zoom == 1.0 else pygame.transform.scale(
            training_dummy.image,
            (round(training_dummy.image.get_width() * camera_zoom), round(training_dummy.image.get_height() * camera_zoom)),
        )
        display.blit(dummy_image, (dummy_screen_x, dummy_screen_y))
        dummy_hp = GuiFont.render(f"더미 {training_dummy.Hp}/{training_dummy.MaxHp}", True, (255, 235, 120))
        display.blit(dummy_hp, dummy_hp.get_rect(midbottom=(round(dummy_screen_x + dummy_image.get_width() / 2), round(dummy_screen_y - 8))))

    # 내 캐릭터 및 무기 그리기
    local_stun_offset_x = round(math.sin(now * 0.08) * 8) if now < local_stun_until else 0
    if now < stealth_until or in_bush:
        stealth_image = my_player.image.copy()
        stealth_image.set_alpha(75 if now < stealth_until else 145)
        display.blit(
            stealth_image,
            ((my_player.rect.x - CameraPosX) * camera_zoom + local_stun_offset_x,
             (my_player.rect.y - CameraPosY) * camera_zoom),
        )
    else:
        my_player.draw(display, CameraPosX, CameraPosY, camera_zoom, local_stun_offset_x)
        if weapon_state.weapon_id == "knife" and knife_attack_until > now and IML.GetBladeFrames():
            elapsed = MELEE_ATTACK_DURATION_MS - max(0, knife_attack_until - now)
            frame_index = min(
                len(IML.GetBladeFrames()) - 1,
                max(0, int(elapsed / MELEE_ATTACK_DURATION_MS * len(IML.GetBladeFrames()))),
            )
            blade = IML.GetBladeFrames()[frame_index]
            blade = pygame.transform.smoothscale(
                blade,
                (
                    max(1, round(blade.get_width() * camera_zoom * MELEE_WEAPON_SCALE)),
                    max(1, round(blade.get_height() * camera_zoom * MELEE_WEAPON_SCALE)),
                ),
            )
            blade = pygame.transform.flip(blade, True, False)
            blade = pygame.transform.rotate(blade, -Weapon_Angle)
            display.blit(blade, blade.get_rect(center=(player_center_screen_x, player_center_screen_y)))
        elif weapon_state.weapon_id != "knife":
            display.blit(rotated_shotgun, Shotgun_rect)



    
    # 기본 시야는 무기 시야와 구분되는 어두운 청색 영역으로 표시합니다.
    base_overlay = pygame.Surface((ScreenX, ScreenY), pygame.SRCALPHA)
    base_overlay.fill((8, 24, 42, PLAYER_BASE_VISION_ALPHA))
    base_vision_polygon = TileGene.get_visibility_polygon(
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

    # 위치 8픽셀, 방향 4도 단위로 묶어 마우스 이동 중 재계산을 줄입니다.
    polygon_cache_key = (
        round(player_world_x / 8),
        round(player_world_y / 8),
        round(Weapon_Angle / 4),
        current_vision_shape,
        current_vision_radius,
        current_vision.vision_fov,
        current_vision_width,
    )
    if polygon_cache_key not in visibility_polygon_cache:
        # 캐시가 없을 때만 벽과 광선이 포함된 폴리곤을 계산합니다.
        visibility_polygon_cache[polygon_cache_key] = TileGene.get_visibility_polygon(
            player_world_x,
            player_world_y,
            current_vision_radius,
            vision_shape=current_vision_shape,
            direction_angle=Weapon_Angle,
            fov_angle=current_vision.vision_fov,
            vision_width=current_vision_width,
            ray_samples=None,  # 자동 최적화 (저격총 직선은 8, 기타는 12)
        )
        # [최적화] 캐시 크기를 128로 증대 (저격총 직선은 각도 변화가 많음)
        if len(visibility_polygon_cache) > 128:
            visibility_polygon_cache.pop(next(iter(visibility_polygon_cache)))
    visibility_polygon = visibility_polygon_cache[polygon_cache_key]
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

    # 시야 오버레이 위에 로컬 플레이어를 다시 그려 기본 시야에서도 항상 보이게 합니다.
    if now < stealth_until or in_bush:
        visible_player_image = my_player.image.copy()
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
                round((my_player.rect.y - CameraPosY) * camera_zoom),
            ),
        )
    else:
        my_player.draw(display, CameraPosX, CameraPosY, camera_zoom, local_stun_offset_x)

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
        alert_text = pygame.font.Font(None, 24).render("발광 룬", True, (255, 235, 130))
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

    for bullet in remote_bullets:
        bullet.draw(display, CameraPosX, CameraPosY, camera_zoom, force_visible=True)

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
            p_info = server_players.get(p_id)
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
        if debug_mode and training_dummy is not None and training_dummy.Hp > 0:
            draw_player_hitboxes(
                display,
                training_dummy.head_hitbox,
                training_dummy.body_hitbox,
                CameraPosX,
                CameraPosY,
                camera_zoom,
            )

    # 폭탄과 폭발 범위는 시야 효과 위에 표시합니다.
    supply_colors = {
        "heal": (100, 255, 130),
        "haste": (255, 240, 100),
        "shield": (100, 220, 255),
        "skill": (210, 150, 255),
    }
    for supply in supply_drops:
        draw_supply_drop(display, supply, CameraPosX, CameraPosY, camera_zoom, supply_colors, now)

    for bomb in active_bombs:
        bomb_screen = world_to_screen(bomb["x"], bomb["y"], CameraPosX, CameraPosY, camera_zoom)
        pygame.draw.circle(display, (255, 170, 40), (round(bomb_screen[0]), round(bomb_screen[1])),
                           max(5, round(12 * camera_zoom)), 3)
    for explosion in active_explosions:
        explosion_screen = world_to_screen(
            explosion["x"], explosion["y"], CameraPosX, CameraPosY, camera_zoom
        )
        if IML.GetExplosionFrames():
            progress = (pygame.time.get_ticks() - explosion["started_at"]) / EXPLOSION_DURATION_MS
            frame_index = min(len(IML.GetExplosionFrames()) - 1, max(0, int(progress * len(IML.GetExplosionFrames()))))
            explosion_image = IML.GetExplosionFrames()[frame_index]
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
        draw_ward(display, ward_x, ward_y, CameraPosX, CameraPosY, camera_zoom)
    for player_id, player_info in server_players.items():
        if int(player_id) == my_id:
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
                draw_ward(display, ward_x, ward_y, CameraPosX, CameraPosY, camera_zoom)

    if shield_until > pygame.time.get_ticks():
        shield_center = get_player_screen_center(
            my_player.X, my_player.Y, IML.Player.get_width(), IML.Player.get_height(),
            CameraPosX, CameraPosY, camera_zoom
        )
        # Protect.png 이미지가 있으면 반투명으로 표시
        if IML.Protect:
            protect_size = max(50, int(90 * camera_zoom))
            protect_scaled = pygame.transform.scale(IML.Protect, (protect_size, protect_size))
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
        server_players,
        my_id,
        training_dummy if debug_mode else None,
        rune_alerts,
        MagneticZoneState if zone_enabled else None,
        zone_elapsed_ms,
    )
    kill_feed = [
        event for event in kill_feed
        if now - event.get("started_at", now) < 5000
    ][-5:]
    kill_font = pygame.font.Font(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "Font", "HeirofLightRegular.ttf"),
        20,
    )
    for index, event in enumerate(reversed(kill_feed)):
        killer = "나" if event.get("killer_id") == my_id else event.get("killer_name", f"플레이어 {event.get('killer_id')}")
        target = "나" if event.get("target_id") == my_id else event.get("target_name", str(event.get("target_id")))
        kill_text = kill_font.render(f"{killer}  >  {target}", True, (255, 225, 150))
        display.blit(kill_text, (ScreenX - 330, 330 + index * 26))
    if game_start_banner_until > now:
        remaining = game_start_banner_until - now
        banner_font = pygame.font.Font(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "Font", "HeirofLightRegular.ttf"),
            54,
        )
        banner = banner_font.render("게임 시작!", True, (255, 225, 120))
        banner.set_alpha(min(255, max(0, remaining * 2)))
        display.blit(banner, banner.get_rect(center=(ScreenX // 2, 150)))
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
    id_text = GuiFont.render(f"ID: {my_id}", True, (255, 255, 255))
    display.blit(id_text, (20, 20))
    
    # --- [퀵슬롯 배경과 스킬 소스창] ---
    draw_skill_panel(display)
    hovered_skill = draw_skill_inventory(display, MousePos, inventory_open, dragging_skill)

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
        IML.TanChang,
        AMMO_PANEL_SIZE,
        AMMO_PANEL_MARGIN,
    )
    
    # ★ [추가] 스킬 툴팁 그리기 (마우스 raycast 무시 - 드래그 중이 아닐 때만)
    if hovered_skill and dragging_skill is None:
        draw_skill_tooltip(display, MousePos, hovered_skill)

    # 시스템 메시지
    if system_message:
        # [커스텀 가능] 시스템 메시지 텍스트 폰트 (GuiFont 사용)
        message_text = GuiFont.render(system_message, True, (255, 255, 255))
        display.blit(message_text, (30, ScreenY - 40))
    
    if debug_mode: # 스킬 창 상태 표시 (우측 상단)
        inventory_status = "🎒 인벤토리: [I]"
        inventory_text = GuiFont.render(inventory_status, True, (170, 220, 180))
        display.blit(inventory_text, (ScreenX - 300, 20))
        vision_status = f"시야: {current_vision_shape} [V]"
        # [커스텀 가능] 시야 정보 폰트 (GuiFont 사용)
        vision_text = GuiFont.render(vision_status, True, (255, 220, 120))
        display.blit(vision_text, (ScreenX - 300, 55))
        # [커스텀 가능] 카메라 FOV 정보 폰트 (GuiFont 사용)
        fov_text = GuiFont.render(f"카메라 FOV: {camera_fov:.2f} / 최대 {CAMERA_FOV_MAX:.2f}", True, (180, 230, 255))
        display.blit(fov_text, (ScreenX - 420, 90))
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
        zone_text = GuiFont.render(zone_status, True, zone_color)
        display.blit(zone_text, (ScreenX - 420, 125))
    # ------------------ [그리기 끝] ------------------


while running: 
    display.fill((0,0,0))
    if ScreenState == "MainView":
        MainView()
    elif ScreenState == "ModeSelectView":
        ModeSelectView()
    elif ScreenState == "NameInputView":
        NameInputView()
    elif ScreenState == "SpectatorPromptView":
        SpectatorPromptView()
    elif ScreenState == "SpectatorView":
        SpectatorView()
    elif ScreenState == "LoadingView":
        LoadingView()
    elif ScreenState == "GameView":
        GameView()
    elif ScreenState == "Victory":
        VictoryView()
    elif ScreenState == "GameOver":
        GameOverView()
    pygame.display.update() 
    clock.tick(FPS)

pygame.quit()
