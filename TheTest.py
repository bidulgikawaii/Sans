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

pygame.init()
pygame.display.set_caption("전설적인 게임")
display = pygame.display.set_mode((ScreenX, ScreenY), 0, 32)
clock = pygame.time.Clock()
ScreenState = "MainView"
# [커스텀 가능] 게임 전체에서 사용할 기본 폰트입니다. 서체와 크기를 여기서 조정합니다.
GuiFont = pygame.font.Font(
    os.path.join(
        os.path.dirname(
            os.path.abspath(__file__)
            ),"Font","HeirofLightRegular.ttf"
            ), 30)




# --- [네트워크 초기화] ---
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM) 
client.connect((ServerIp, ServerPort))

init_data = pickle.loads(client.recv(1024))
my_id = init_data["init_id"]
print(f"내 아이디:{my_id}번 입니다.")


map = random.seed(init_data["seed"])  # 시드 고정
IML = Imageload()
set_ui_assets(IML.SkillWindow, IML.QuickSlot)
set_image_loader(IML)  # SkillAndSlot에 이미지 로더 전달
TileGene = TileGenerator()
# [커스텀 가능] 맵 가로/세로 타일 수입니다. 타일 크기와 곱해 전체 월드 크기가 결정됩니다.
TileGene.generate_map(MAP_WIDTH_TILES, MAP_HEIGHT_TILES, seed_value=init_data["seed"])

# [커스텀 가능] HP 프레임의 화면 표시 크기입니다. 원본 비율을 유지해 한 번만 축소합니다.
HpBarFrame = pygame.transform.smoothscale(IML.HpBar, HP_FRAME_SIZE)

# 🕹️ [Player 클래스 인스턴스 생성 - 랜덤 스폰]
p_w = IML.Player.get_width()
p_h = IML.Player.get_height()

# [커스텀 가능] 안전 스폰을 찾을 타일 좌표 범위입니다.
safe_spawn = TileGene.find_safe_spawn(SPAWN_MIN_X, SPAWN_MAX_X, SPAWN_MIN_Y, SPAWN_MAX_Y)
spawn_tile_x, spawn_tile_y = safe_spawn or (MAP_WIDTH_TILES // 2, MAP_HEIGHT_TILES // 2)
spawn_world_x = spawn_tile_x * TileGene.tile_size
spawn_world_y = spawn_tile_y * TileGene.tile_size

my_player = Player(spawn_world_x, spawn_world_y, (p_w, p_h), IML, TileGene)
my_player.image = IML.Player
print(f"🎮 플레이어가 ({spawn_tile_x}, {spawn_tile_y}) 타일에 스폰되었습니다.")

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
    
    # 발사한 총알 정보 (여러 개 가능)
    "bullets": [],      # [{"x": x, "y": y, "angle": angle}, ...]
}

CameraPosX = 0
CameraPosY = 0
camera_fov = max(1.0, min(CAMERA_FOV, CAMERA_FOV_MAX))
camera_zoom = 1.0 / camera_fov
lerp = 0.05

Weapon_Angle = 0
Weapon_Pos = (0, 0)

running = True
bullets = []
remote_bullets = []
processed_bullet_events = set()
skill_cooldowns = {}
vision_skill_until = 0
shield_until = 0
haste_until = 0
stealth_until = 0
stealth_token = 0
debug_mode = False
active_bombs = []
active_explosions = []
knife_attack_until = 0
supply_drops = []
next_supply_drop_at = pygame.time.get_ticks() + SUPPLY_DROP_INTERVAL_MS
pending_treasure_destroys = []
screen_shake = 0
server_players = {}
particles = ParticleSystem()
last_effect_tick = pygame.time.get_ticks()
# 시야 밖을 검게 덮을 때 재사용하는 투명 레이어입니다.
vision_overlay = pygame.Surface((ScreenX, ScreenY), pygame.SRCALPHA)
# 방향과 모양이 크게 바뀔 때만 시야 폴리곤을 다시 계산합니다.
visibility_polygon_cache = {}
mouse_fire_hold = False
preserve_magazine_after_chest = False
teleport_anchor = None
teleport_anchor_expires_at = 0

def draw_visibility_geometry(surface, geometry, camera_x, camera_y, zoom):
    """시야 부분을 마스크에서 투명하게 뚫습니다."""
    if geometry.is_empty:
        return
    polygons = geometry.geoms if geometry.geom_type == "MultiPolygon" else (geometry,)
    for polygon in polygons:
        points = [
            ((world_x - camera_x) * zoom, (world_y - camera_y) * zoom)
            for world_x, world_y in polygon.exterior.coords
        ]
        if len(points) >= 3:
            pygame.draw.polygon(surface, (0, 0, 0, 0), points)


def get_aim_ray_endpoint(origin_x, origin_y, angle_degrees):
    """로컬 플레이어의 조준 ray가 벽에 닿는 월드 좌표를 계산합니다."""
    angle = math.radians(angle_degrees)
    step = max(4, TileGene.tile_size // 4)
    last_x, last_y = origin_x, origin_y
    for distance in range(step, BULLET_TARGET_DISTANCE + step, step):
        ray_x = origin_x + math.cos(angle) * distance
        ray_y = origin_y + math.sin(angle) * distance
        ray_rect = pygame.Rect(round(ray_x) - 2, round(ray_y) - 2, 4, 4)
        if TileGene.check_wall_collision(ray_rect):
            return last_x, last_y
        last_x, last_y = ray_x, ray_y
    return last_x, last_y


def draw_local_aim_ray(surface, start_x, start_y, angle_degrees):
    """현재 클라이언트의 조준선만 그립니다."""
    end_x, end_y = get_aim_ray_endpoint(
        (start_x + CameraPosX) / camera_zoom,
        (start_y + CameraPosY) / camera_zoom,
        angle_degrees,
    )
    end_screen = world_to_screen(end_x, end_y, CameraPosX, CameraPosY, camera_zoom)
    pygame.draw.line(
        surface,
        (255, 0, 0),
        (round(start_x), round(start_y)),
        (round(end_screen[0]), round(end_screen[1])),
        max(1, round(2 * camera_zoom)),
    )


def draw_teleport_anchor(surface, anchor_x, anchor_y):
    """설치된 텔포석상을 로컬 화면에 지속적으로 표시합니다."""
    screen_x, screen_y = world_to_screen(anchor_x, anchor_y, CameraPosX, CameraPosY, camera_zoom)
    center = (round(screen_x), round(screen_y))
    width = max(8, round(18 * camera_zoom))
    height = max(16, round(48 * camera_zoom))
    pygame.draw.ellipse(
        surface,
        (100, 255, 150),
        (center[0] - width, center[1] + height // 3, width * 2, max(4, height // 3)),
        2,
    )
    pygame.draw.polygon(
        surface,
        (150, 255, 180),
        [
            (center[0], center[1] - height),
            (center[0] - width, center[1] + height // 3),
            (center[0] + width, center[1] + height // 3),
        ],
        2,
    )
    pygame.draw.circle(surface, (220, 255, 220), center, max(3, round(6 * camera_zoom)), 2)

def load_effect_sound(filename):
    """효과음 파일이 아직 없어도 게임이 실행되도록 선택적으로 로드합니다."""
    sound_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Sound", filename)
    try:
        return pygame.mixer.Sound(sound_path)
    except (pygame.error, OSError) as error:
        print(f"[사운드 로드 실패] {filename}: {error}")
        return None


def play_effect_sound(sound, filename):
    if sound is None:
        return
    try:
        sound.play()
    except pygame.error as error:
        print(f"[사운드 재생 실패] {filename}: {error}")


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
        "expires_at": now + SUPPLY_DROP_LIFETIME_MS,
    })


def apply_supply_reward(reward_type):
    """보급품 종류별 회복·버프 효과를 적용합니다."""
    # 보급품은 서버에 아이템 자체를 동기화하지 않고,
    # 획득한 클라이언트의 플레이어 상태에만 효과를 적용합니다.
    now = pygame.time.get_ticks()
    center_x, center_y = get_player_world_center(
        my_player.X, my_player.Y, IML.Player.get_width(), IML.Player.get_height()
    )
    if reward_type == "heal":
        my_player.Hp = min(my_player.MaxHp, my_player.Hp + SUPPLY_HEAL_AMOUNT)
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
        available = [name for name in SKILL_BOOK if name not in owned_skills]
        if not available:
            my_player.Hp = min(my_player.MaxHp, my_player.Hp + SUPPLY_HEAL_AMOUNT)
            message = "보급품 획득: 체력 회복"
            color = (100, 255, 130)
        else:
            skill_name = random.choice(available)
            add_skill_to_inventory(skill_name)
            message = f"보급품 획득: {skill_name}"
            color = SKILL_BOOK[skill_name].color
    particles.emit(center_x, center_y, color, count=24, speed=80, lifetime=600, size=6)
    return message


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

def draw_ui_gauge(surface, x, y, current_val, max_val):
    """투명 중앙이 뚫린 HP 프레임 안쪽에 HP 게이지를 그립니다."""
    
    frame_width, frame_height = HpBarFrame.get_size()
    ratio = max(0, min(current_val, max_val)) / max(1, max_val)

    global hp_color
    # HpBar.png의 중앙 투명 영역 비율에 맞춘 내부 게이지 영역
    inner_x = int(frame_width * 0.11)
    inner_y = int(frame_height * 0.34)
    inner_width = int(frame_width * 0.78)
    inner_height = int(frame_height * 0.27)
    
    inner_rect = pygame.Rect(x + inner_x, y + inner_y, inner_width, inner_height)

    # 1. 배경 사각형 그리기 (피가 달았을 때 비어있는 공간을 나타낼 어두운 색)
    bg_color = pygame.Color("gray20")  # 어두운 회색 (또는 (40, 40, 40))
    pygame.draw.rect(surface, bg_color, inner_rect)

    # 2. 체력 비율에 따른 게이지 색상 결정 (인자 fill_color 대신 실시간 계산)
    health_ratio = current_val / max(1, max_val)
    if health_ratio >= HEALTH_GREEN_THRESHOLD:
        hp_color = pygame.Color("green")
    elif health_ratio >= HEALTH_YELLOW_THRESHOLD:
        hp_color = pygame.Color("yellow")
    else:
        hp_color = pygame.Color("red")
        
    # 3. 현재 체력만큼 게이지 채워 그리기
    fill_rect = inner_rect.copy()
    fill_rect.width = int(inner_rect.width * ratio)
    
    if fill_rect.width > 0:
        pygame.draw.rect(surface, hp_color, fill_rect)

    # 4. 중앙 게이지 위에 테두리 이미지를 올려 프레임이 게이지를 감쌉니다.
    surface.blit(HpBarFrame, (x, y))


def draw_ammo_status(surface):
    """현재 무기와 탄창/예비 탄약을 화면 오른쪽 아래에 표시합니다."""
    config = weapon_state.config
    # [커스텀 가능] 탄약 표시 폰트: 서체("malgungothic"), 크기(24)
    ammo_font = GuiFont
    name_text = ammo_font.render(config.name, True, (255, 220, 120))
    if weapon_state.is_reloading_now():
        ammo_text = ammo_font.render("재장전 중...", True, (255, 180, 120))
    else:
        ammo_text = ammo_font.render(weapon_state.ammo_text(), True, (255, 255, 255))
    surface.blit(name_text, (ScreenX - 210, ScreenY - 72))
    surface.blit(ammo_text, (ScreenX - 80, ScreenY - 72))


def draw_quick_slot_cooldowns(surface):
    """스킬 쿨타임을 각 슬롯에 표시합니다."""
    now = pygame.time.get_ticks()
    for slot in quick_slots:
        if not slot.assigned_skill:
            continue
        end_time = skill_cooldowns.get(slot.assigned_skill, 0)
        if end_time <= now:
            continue
        remain = max(0.0, (end_time - now) / 1000.0)
        overlay = pygame.Surface((slot.rect.width, slot.rect.height), pygame.SRCALPHA)
        pygame.draw.rect(overlay, (0, 0, 0, 170), overlay.get_rect(), border_radius=8)
        surface.blit(overlay, slot.rect.topleft)
        # [커스텀 가능] 쿨타임 표시 폰트: 서체("malgungothic"), 크기(14)
        text = GuiFont.render(f"{remain:.1f}s", True, (255, 255, 255))
        surface.blit(text, (slot.rect.centerx - text.get_width() / 2, slot.rect.centery - 8))


def MainView():
    global running, ScreenState
    # [커스텀 가능] 메인 화면 타이틀 (GuiFont는 기본 폰트)
    gf = GuiFont.render("안녕하살법 전설적인 테스트", 1, pygame.Color("White"))
    display.blit(gf, (20, 20))

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
            if event.key == pygame.K_SPACE:
                ScreenState = "GameView"


def GameOverView():
    global running
    title = GuiFont.render("게임 오버", True, (220, 50, 50))
    guide = GuiFont.render("ESC를 눌러 종료하세요", True, (255, 255, 255))
    display.blit(title, title.get_rect(center=(ScreenX // 2, ScreenY // 2 - 60)))
    display.blit(guide, guide.get_rect(center=(ScreenX // 2, ScreenY // 2 + 70)))

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            running = False


def handle_quit(_event, _mouse_pos):
    global running
    running = False


def activate_quick_slot(key):
    global system_message, vision_shape_override, vision_skill_until, shield_until, haste_until, stealth_until, stealth_token, teleport_anchor, teleport_anchor_expires_at
    key_name = pygame.key.name(key).upper()
    slot = next((slot for slot in quick_slots if slot.key_name == key_name), None)
    if not slot or not slot.assigned_skill:
        system_message = f"[{key_name}] 슬롯이 비어있습니다."
        return

    skill_name = slot.assigned_skill
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
    if skill_name == "달팽이 세개":
        target_x, target_y = screen_to_world(*pygame.mouse.get_pos(), CameraPosX, CameraPosY, camera_zoom)
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
        system_message = "1.5초 동안 은신합니다."
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
    global system_message, vision_shape_override
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


def handle_key_event(event, _mouse_pos):
    global inventory_open, dragging_skill, debug_mode, system_message
    weapon_key_codes = (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6)
    weapon_id = dict(zip(weapon_key_codes, WEAPON_KEYS)).get(event.key)
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

    key_actions = {
        pygame.K_ESCAPE: lambda _key: handle_quit(None, None),
        pygame.K_i: lambda _key: toggle_inventory(),
        pygame.K_v: lambda _key: cycle_vision_shape(),
        pygame.K_q: lambda _key: activate_quick_slot(_key),
        pygame.K_e: lambda _key: activate_quick_slot(_key),
        pygame.K_t: lambda _key: activate_quick_slot(_key),
        pygame.K_r: lambda _key: reload_weapon(),
        pygame.K_f: lambda _key: activate_skill_or_reload(_key),
    }
    key_actions.get(event.key, activate_quick_slot)(event.key)


def toggle_inventory():
    global inventory_open, dragging_skill
    inventory_open = not inventory_open
    dragging_skill = None


def cycle_vision_shape():
    """V 키로 현재 시야 모양을 순서대로 변경합니다."""
    global vision_shape_index, vision_shape_override, system_message
    vision_shape_index = (vision_shape_index + 1) % len(vision_shapes)
    vision_shape_override = vision_shapes[vision_shape_index]
    shape_name = vision_shape_override
    system_message = f"시야 모양: {shape_name}" 


def fire_knife():
    """칼 공격: 근거리 범위 내의 모든 적에게 데미지를 줍니다."""
    global screen_shake, system_message, knife_attack_until
    config = weapon_state.config
    knife_attack_until = pygame.time.get_ticks() + MELEE_ATTACK_DURATION_MS
    
    center_x, center_y = get_player_world_center(
        my_player.X,
        my_player.Y,
        IML.Player.get_width(),
        IML.Player.get_height(),
    )
    
    # 칼 공격 범위 (데미지를 줄 최대 거리)
    knife_range = MELEE_RANGE
    
    # 근처 서버 플레이어 찾기
    attacked_count = 0
    for p_id, p_info in server_players.items():
        if int(p_id) == my_id:
            continue
        
        enemy_center_x = p_info["posX"] + IML.Player.get_width() / 2
        enemy_center_y = p_info["posY"] + IML.Player.get_height() / 2
        
        # 거리 계산
        distance = math.sqrt((center_x - enemy_center_x)**2 + (center_y - enemy_center_y)**2)
        if distance <= knife_range:
            attacked_count += 1
    
    weapon_state.consume_round()
    screen_shake = min(SCREEN_SHAKE_MAX, screen_shake + MELEE_SHAKE)
    
    if attacked_count > 0:
        particles.emit(center_x, center_y, (255, 80, 80), count=18, speed=100, lifetime=400, size=5)
        system_message = f"칼 공격! {config.damage} 데미지 × {attacked_count}명"
    else:
        system_message = f"칼 휘둘렀습니다. (데미지: {config.damage})"


def fire_bullet():
    global bullets, screen_shake, system_message
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
        CameraPosX,
        CameraPosY,
        camera_zoom,
    )
    base_angle = math.radians(
        Tool.GetAtn2Angle_Degrees(player_screen_center, current_mouse_pos)
    )
    muzzle_x = center_x + math.cos(base_angle) * 40
    muzzle_y = center_y + math.sin(base_angle) * 40
    weapon_state.consume_round()
    screen_shake = min(SCREEN_SHAKE_MAX, screen_shake + int(config.recoil * 2))
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
    global running, ScreenState, CameraPosX, CameraPosY, Weapon_Angle, Weapon_Pos, camera_fov, camera_zoom
    global screen_shake, server_players, bullets, remote_bullets, processed_bullet_events, MousePos, system_message
    global vision_shape_override, vision_skill_until, shield_until, haste_until
    global active_bombs, active_explosions, supply_drops, next_supply_drop_at, pending_treasure_destroys
    global visibility_polygon_cache, mouse_fire_hold, last_effect_tick, preserve_magazine_after_chest
    global teleport_anchor, teleport_anchor_expires_at

    MousePos = pygame.mouse.get_pos()
    if my_player.Hp <= 0:
        ScreenState = "GameOver"
        return
    now = pygame.time.get_ticks()
    if teleport_anchor is not None and now >= teleport_anchor_expires_at:
        teleport_anchor = None
        teleport_anchor_expires_at = 0
        skill_cooldowns["텔포"] = now + TELEPORT_COOLDOWN_MS
        system_message = "텔포석상이 사라졌습니다. 15초 후 다시 사용할 수 있습니다."
    handle_game_events()
    Weapon_Pos = pygame.mouse.get_pos()

    if mouse_fire_hold and weapon_state.config.automatic and weapon_state.can_fire():
        fire_bullet()

    my_player.handle_input()
    weapon_state.update_reload()

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
    my_player.normal_speed = PLAYER_HASTE_SPEED if now < haste_until else PLAYER_NORMAL_SPEED

    if now >= next_supply_drop_at:
        if len(supply_drops) < SUPPLY_DROP_MAX and random.random() < SUPPLY_DROP_CHANCE:
            spawn_supply_drop(now)
        next_supply_drop_at = now + SUPPLY_DROP_INTERVAL_MS

    player_rect = my_player.rect
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
                p_info["hp"] = max(0, p_info.get("hp", PLAYER_MAX_HP) - BOMB_DAMAGE)
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
    send_data["destroyed_treasures"] = list(pending_treasure_destroys)
    
    # ★ [정리] 총알 정보 - 이번 프레임에서 새로 발사된 총알만 전송
    send_data["bullets"] = [
        {
            "x": bullet.x,
            "y": bullet.y,
            "angle": bullet.angle,
            "weapon_id": bullet.weapon_id,
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
            synchronized_treasures = set()
            for player_snapshot in server_players.values():
                synchronized_treasures.update(
                    tuple(treasure) for treasure in player_snapshot.get("destroyed_treasures", [])
                )
            for tile_x, tile_y in synchronized_treasures:
                TileGene.destroy_treasure(tile_x, tile_y)
            pending_treasure_destroys.clear()
            own_snapshot = server_players.get(my_id)
            if own_snapshot:
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

    if screen_shake > 0:
        CameraPosX += random.randint(-screen_shake, screen_shake)
        CameraPosY += random.randint(-screen_shake, screen_shake)
        screen_shake -= 1

    CameraPosX, CameraPosY = TileGene.clamp_camera(
        CameraPosX, CameraPosY, ScreenX, ScreenY, camera_zoom
    )

    player_screen_x, player_screen_y = world_to_screen(my_player.X, my_player.Y, CameraPosX, CameraPosY, camera_zoom)
    player_center_screen_x, player_center_screen_y = get_player_screen_center(my_player.X, my_player.Y, IML.Player.get_width(), IML.Player.get_height(), CameraPosX, CameraPosY, camera_zoom)

    Weapon_Angle = Tool.GetAtn2Angle_Degrees((player_center_screen_x, player_center_screen_y), Weapon_Pos)
    weapon_image = IML.GetPistol() if weapon_state.weapon_id == "pistol" else IML.GetShotGun()
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
    # 같은 프레임에서 같은 대상은 한 번만 벽 가림을 계산합니다.
    visibility_cache = {}

    def is_visible(point_x, point_y):
        """다른 플레이어가 현재 시야 안에 있는지 확인합니다."""
        point = (point_x, point_y)
        if point not in visibility_cache:
            visibility_cache[point] = TileGene.is_point_visible_from(
                player_world_x,
                player_world_y,
                point_x,
                point_y,
                current_vision.vision_radius,
                vision_shape=current_vision_shape,
                direction_angle=Weapon_Angle,
                fov_angle=current_vision.vision_fov,
                vision_width=current_vision.vision_width,
            )
        return visibility_cache[point]

    # ------------------ [게임 월드 그리기] ------------------
    display.fill((0, 0, 200))
    TileGene.draw(display, CameraPosX, CameraPosY, camera_zoom)

    player_world_x, player_world_y = get_player_world_center(my_player.X, my_player.Y, IML.Player.get_width(), IML.Player.get_height())

    for bullet in bullets:
        bullet.update()
        bullet.draw(display, CameraPosX, CameraPosY, camera_zoom)

        if bullet.is_active:
            if TileGene.check_wall_collision(bullet.rect):
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
                    bullet.is_active = False
                    particles.emit(
                        bullet.x, bullet.y, (255, 70, 70),
                        count=12, speed=65, lifetime=350, size=4,
                    )
                    break
    bullets = [b for b in bullets if b.is_active]

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
            )
            angle = math.radians(bullet_info.get("angle", 0.0))
            enemy_bullet.launch(
                bullet_info["x"], bullet_info["y"],
                bullet_info["x"] + math.cos(angle) * BULLET_TARGET_DISTANCE,
                bullet_info["y"] + math.sin(angle) * BULLET_TARGET_DISTANCE,
                speed=config.bullet_speed,
            )
            remote_bullets.append(enemy_bullet)

    for bullet in remote_bullets:
        bullet.update()
        if bullet.is_active and TileGene.check_wall_collision(bullet.rect):
            bullet.is_active = False
        if bullet.is_active and shield_until <= pygame.time.get_ticks() and my_player.check_bullet_hit(bullet.rect, bullet.damage):
            bullet.is_active = False
        bullet.draw(display, CameraPosX, CameraPosY, camera_zoom)
    remote_bullets = [b for b in remote_bullets if b.is_active]

    if my_player.Hp <= 0:
        ScreenState = "GameOver"
        return

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
        if p_info.get("stealth", False) and not (p_info.get("in_bush", False) and close_to_bush):
            continue

        if not is_visible(other_world_x, other_world_y):
            continue

        other_screen_x, other_screen_y = world_to_screen(p_info["posX"], p_info["posY"], CameraPosX, CameraPosY, camera_zoom)
        other_image = IML.Player if camera_zoom == 1.0 else pygame.transform.scale(
            IML.Player, (round(IML.Player.get_width() * camera_zoom), round(IML.Player.get_height() * camera_zoom))
        )
        display.blit(other_image, (other_screen_x, other_screen_y))

        other_center_x, other_center_y = get_player_screen_center(p_info["posX"], p_info["posY"], IML.Player.get_width(), IML.Player.get_height(), CameraPosX, CameraPosY, camera_zoom)
        other_weapon_image = IML.GetPistol() if p_info.get("weapon_id") == "pistol" else IML.GetShotGun()
        if p_info.get("weapon_id") == "pistol":
            other_weapon_image = pygame.transform.flip(other_weapon_image, True, False)
        other_gun = other_weapon_image if camera_zoom == 1.0 else pygame.transform.scale(
            other_weapon_image, (round(other_weapon_image.get_width() * camera_zoom), round(other_weapon_image.get_height() * camera_zoom))
        )
        other_rotated_gun = pygame.transform.rotate(other_gun, -p_info["angle"])
        other_gun_rect = other_rotated_gun.get_rect()
        other_gun_rect.center = (other_center_x, other_center_y)
        display.blit(other_rotated_gun, other_gun_rect)

    # 내 캐릭터 및 무기 그리기
    if now < stealth_until:
        stealth_image = my_player.image.copy()
        stealth_image.set_alpha(75)
        display.blit(
            stealth_image,
            ((my_player.rect.x - CameraPosX) * camera_zoom,
             (my_player.rect.y - CameraPosY) * camera_zoom),
        )
    else:
        my_player.draw(display, CameraPosX, CameraPosY, camera_zoom)
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



    
    # 화면 전체를 어둡게 한 뒤, 아래에서 시야 폴리곤만 투명하게 뚫습니다.
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

    # 위치 8픽셀, 방향 4도 단위로 묶어 마우스 이동 중 재계산을 줄입니다.
    polygon_cache_key = (
        round(player_world_x / 8),
        round(player_world_y / 8),
        round(Weapon_Angle / 4),
        current_vision_shape,
        current_vision.vision_radius,
        current_vision.vision_fov,
        current_vision.vision_width,
    )
    if polygon_cache_key not in visibility_polygon_cache:
        # 캐시가 없을 때만 벽과 광선이 포함된 폴리곤을 계산합니다.
        visibility_polygon_cache[polygon_cache_key] = TileGene.get_visibility_polygon(
            player_world_x,
            player_world_y,
            current_vision.vision_radius,
            vision_shape=current_vision_shape,
            direction_angle=Weapon_Angle,
            fov_angle=current_vision.vision_fov,
            vision_width=current_vision.vision_width,
            ray_samples=None,  # 자동 최적화 (저격총 직선은 8, 기타는 12)
        )
        # [최적화] 캐시 크기를 128로 증대 (저격총 직선은 각도 변화가 많음)
        if len(visibility_polygon_cache) > 128:
            visibility_polygon_cache.pop(next(iter(visibility_polygon_cache)))
    visibility_polygon = visibility_polygon_cache[polygon_cache_key]
    if visibility_polygon:
        # 월드 폴리곤을 현재 카메라 좌표로 변환해 어두운 레이어를 뚫습니다.
        draw_visibility_geometry(dark_overlay, visibility_polygon, CameraPosX, CameraPosY, camera_zoom)

    display.blit(dark_overlay, (0, 0))

    # 조준선은 로컬 화면에만 그리므로 다른 플레이어에게 동기화되지 않습니다.
    draw_local_aim_ray(display, player_center_screen_x, player_center_screen_y, Weapon_Angle)

    # 시야 밖에 있어도 총알은 항상 보이도록 최종 레이어에서 다시 그립니다.
    for bullet in bullets:
        bullet.draw(display, CameraPosX, CameraPosY, camera_zoom, force_visible=True)

    for bullet in remote_bullets:
        bullet.draw(display, CameraPosX, CameraPosY, camera_zoom, force_visible=True)

    # 폭탄과 폭발 범위는 시야 효과 위에 표시합니다.
    supply_colors = {
        "heal": (100, 255, 130),
        "haste": (255, 240, 100),
        "shield": (100, 220, 255),
        "skill": (210, 150, 255),
    }
    for supply in supply_drops:
        supply_screen = world_to_screen(
            supply["x"], supply["y"], CameraPosX, CameraPosY, camera_zoom
        )
        color = supply_colors[supply["type"]]
        pygame.draw.circle(
            display,
            color,
            (round(supply_screen[0]), round(supply_screen[1])),
            max(8, round(SUPPLY_DROP_RADIUS * camera_zoom)),
        )
        pygame.draw.circle(
            display,
            (255, 255, 255),
            (round(supply_screen[0]), round(supply_screen[1])),
            max(10, round((SUPPLY_DROP_RADIUS + 5) * camera_zoom)),
            2,
        )

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

    if teleport_anchor is not None:
        draw_teleport_anchor(display, *teleport_anchor)

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
    ui_x = 30
    ui_y = 80  
    draw_ui_gauge(display, ui_x, ui_y, my_player.Hp, my_player.MaxHp)
    
    # [커스텀 가능] HP 텍스트 표시 폰트 (GuiFont 사용)
    hp_text = GuiFont.render(f"HP: {my_player.Hp} / {my_player.MaxHp}", True, (255, 255, 255))
    display.blit(hp_text, (ui_x + HP_FRAME_SIZE[0] + 15, ui_y + 42))

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

    draw_quick_slot_cooldowns(display)
    draw_ammo_status(display)
    
    # ★ [추가] 스킬 툴팁 그리기 (마우스 raycast 무시 - 드래그 중이 아닐 때만)
    if hovered_skill and dragging_skill is None:
        draw_skill_tooltip(display, MousePos, hovered_skill)

    # 시스템 메시지
    if system_message:
        # [커스텀 가능] 시스템 메시지 텍스트 폰트 (GuiFont 사용)
        message_text = GuiFont.render(system_message, True, (255, 255, 255))
        display.blit(message_text, (30, ScreenY - 40))
    
    # 스킬 창 상태 표시 (우측 상단)
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
    # ------------------ [그리기 끝] ------------------


while running: 
    display.fill((0,0,0))
    if ScreenState == "MainView":
        MainView()
    elif ScreenState == "GameView":
        GameView()
    elif ScreenState == "GameOver":
        GameOverView()
    pygame.display.update() 
    clock.tick(FPS)

pygame.quit()
