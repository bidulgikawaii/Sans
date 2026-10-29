import math
import random

import pygame
from Settings import key_label, settings
from Config import (
    QUICK_SLOT_SIZE,
    QUICK_SLOT_START_X,
    QUICK_SLOT_Y,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    SKILL_ICON_SIZE,
    INVENTORY_ITEM_COLUMNS,
    INVENTORY_SIZE,
    INVENTORY_X,
    INVENTORY_Y,
    INVENTORY_ITEM_ALPHA,
    SKILL_PANEL_SIZE,
    SKILL_PANEL_X,
    SKILL_PANEL_Y,
    SKILL_ICON_START_X,
    SKILL_ICON_START_Y,
    SKILL_ICON_GAP_X,
    SKILL_ICON_GAP_Y,
)

# 보유 스킬 목록과 실제 사용 슬롯을 별도로 관리해, 인벤토리 보유만으로 스킬이 발동하지 않게 합니다.

class SkillUIState:
    """스킬 UI가 공유하는 선택 상태와 렌더링 자산을 보관합니다."""

    def __init__(self):
        self.image_loader = None
        self.font = None
        self.small_font = None
        self.quick_slot_image = None
        self.skill_slot_image = None
        self.skill_panel_image = None
        self.selected_skill = None


_ui_state = SkillUIState()

def set_image_loader(loader):
    _ui_state.image_loader = loader

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
DARK_GRAY = (70, 70, 70)
RED = (255, 100, 100)
BLUE = (100, 100, 255)
YELLOW = (255, 255, 100)
def get_font():
    if _ui_state.font is None:
        _ui_state.font = pygame.font.SysFont("malgungothic", 14)
    return _ui_state.font


def get_small_font():
    if _ui_state.small_font is None:
        _ui_state.small_font = pygame.font.SysFont("malgungothic", 12)
    return _ui_state.small_font


def set_ui_assets(skill_window_image, quick_slot_image):
    _ui_state.skill_panel_image = pygame.transform.smoothscale(skill_window_image, SKILL_PANEL_SIZE)
    _ui_state.quick_slot_image = pygame.transform.smoothscale(quick_slot_image, (QUICK_SLOT_SIZE, QUICK_SLOT_SIZE))
    _ui_state.skill_slot_image = pygame.transform.smoothscale(quick_slot_image, (SKILL_ICON_SIZE, SKILL_ICON_SIZE))


class Skill:
    def __init__(self, name, color, msg, power=10, ability=""):
        self.name = name
        self.color = color
        self.Power = power
        self.Ability = ability
        self.msg = msg

    def Atk(self):
        return self.msg

    def get_info(self):
        return f"{self.name} | 공격력: {self.Power} | 능력: {self.Ability}"


SKILL_BOOK = {
    "폭탄받아라!": Skill("폭탄받아라!", RED, "폭탄을 던졌습니다!", 15, "폭탄을 던져 광범위 공격"),
    "매의 눈": Skill("매의 눈", (120, 220, 255), "최대 거리까지 시야가 넓어집니다!", 0, "3초간 360도 최대 사거리 시야로 플레이어 확인"),
    "와드": Skill("와드", (120, 240, 255), "와드를 설치했습니다!", 0, "설치한 위치의 시야를 밝힘"),
    "부활의 차": Skill("부활의 차", (255, 210, 120), "일반전: 장착 중 사망 시 한 번 부활. 데스매치: 사용 시 체력 회복 및 사망 1회 방지", 0, "일반: 사망 시 부활 / 데스매치: 사용 시 체력 완전 회복·사망 1회 방지"),
    "보호막": Skill("보호막", (100, 255, 180), "3초간 피해를 막지만 이동할 수 없습니다!", 0, "3초간 공격 피해를 무효화하는 대신 이동 불가"),
    "은신": Skill("은신", (190, 190, 220), "몸을 숨깁니다!", 0, "4.5초간 적에게 완전히 보이지 않음"),
    "텔포": Skill("텔포", (180, 255, 180), "일반전: 석상을 설치해 이동합니다. 데스매치: 마우스 위치로 즉시 이동합니다.", 0, "일반전은 설치/재사용, 데스매치는 지정 위치 순간이동"),
    "기절탄": Skill("기절탄", (255, 245, 180), "맞은 플레이어를 2.5초 동안 기절시킵니다.", 10, "청록색 전기 탄환, 적중 시 2.5초 스턴"),
}

# 현재 보유 중인 스킬입니다. 도감(SKILL_BOOK)과 달리 실제 획득 목록만 표시합니다.
owned_skills = set()


class SkillWindowItem:
    def __init__(self, x, y, skill_name, is_owned=False):
        self.rect = pygame.Rect(x, y, SKILL_ICON_SIZE, SKILL_ICON_SIZE)
        self.skill_name = skill_name
        self.is_owned = is_owned
        self.is_hovering = False
        self.is_selected = False
        self._icon_surface = None

    def update(self, mouse_pos):
        self.is_hovering = self.rect.collidepoint(mouse_pos)

    def draw(self, surface):
        skill = SKILL_BOOK[self.skill_name]
        self.is_selected = self.skill_name == _ui_state.selected_skill
        border_color = (255, 220, 100) if self.is_selected else (
            (255, 255, 0) if self.is_hovering and self.is_owned else BLACK
        )
        border_width = 3 if self.is_hovering or self.is_selected else 2
        if self._icon_surface is None:
            icon_surface = pygame.Surface(self.rect.size, pygame.SRCALPHA)
            if _ui_state.skill_slot_image:
                icon_surface.blit(_ui_state.skill_slot_image, (0, 0))
            else:
                pygame.draw.rect(icon_surface, skill.color, icon_surface.get_rect(), border_radius=5)
            skill_icon = (
                _ui_state.image_loader.GetSkillIcon(self.skill_name)
                if _ui_state.image_loader
                else None
            )
            if skill_icon:
                icon_surface.blit(skill_icon, (0, 0))
            else:
                pygame.draw.rect(icon_surface, skill.color, icon_surface.get_rect().inflate(-12, -12), border_radius=4)
                text = get_font().render(skill.name[:2], True, BLACK)
                icon_surface.blit(text, text.get_rect(center=icon_surface.get_rect().center))
            self._icon_surface = icon_surface
        self._icon_surface.set_alpha(255 if self.is_owned else INVENTORY_ITEM_ALPHA)
        surface.blit(self._icon_surface, self.rect)
        
        pygame.draw.rect(surface, border_color, self.rect, border_width, border_radius=5)


class QuickSlot:
    def __init__(self, x, y, key_name):
        self.rect = pygame.Rect(x, y, QUICK_SLOT_SIZE, QUICK_SLOT_SIZE)
        self.key_name = key_name
        self.assigned_skill = None
        self.is_hovering = False
        self.equip_particles = []

    def update(self, mouse_pos):
        self.is_hovering = self.rect.collidepoint(mouse_pos)

    def draw(self, surface):
        border_color = (255, 255, 100) if self.is_hovering else WHITE
        border_width = 3 if self.is_hovering else 2
        if _ui_state.quick_slot_image:
            surface.blit(_ui_state.quick_slot_image, self.rect)
        else:
            pygame.draw.rect(surface, DARK_GRAY, self.rect, border_radius=5)

        content_rect = self.rect.inflate(-12, -12)
        if self.assigned_skill:
            skill = SKILL_BOOK[self.assigned_skill]
            
            # 스킬 아이콘 이미지가 있으면 표시
            if _ui_state.image_loader:
                skill_icon = _ui_state.image_loader.GetSkillIcon(self.assigned_skill)
                if skill_icon:
                    # 스킬 아이콘을 퀵슬롯의 정중앙에 배치합니다.
                    icon_rect = skill_icon.get_rect(center=self.rect.center)
                    surface.blit(skill_icon, icon_rect)
                else:
                    pygame.draw.rect(surface, skill.color, content_rect, border_radius=4)
                    text = get_font().render(skill.name[:2], True, BLACK)
                    surface.blit(text, text.get_rect(center=(self.rect.centerx, self.rect.centery + 5)))
                    power_text = get_small_font().render(f"P:{skill.Power}", True, BLACK)
                    surface.blit(power_text, (self.rect.x + 5, self.rect.bottom - 20))
            else:
                pygame.draw.rect(surface, skill.color, content_rect, border_radius=4)
                text = get_font().render(skill.name[:2], True, BLACK)
                surface.blit(text, text.get_rect(center=(self.rect.centerx, self.rect.centery + 5)))
                power_text = get_small_font().render(f"P:{skill.Power}", True, BLACK)
                surface.blit(power_text, (self.rect.x + 5, self.rect.bottom - 20))
        else:
            text = get_font().render("EMPTY", True, (150, 150, 150))
            surface.blit(text, text.get_rect(center=self.rect.center))

        pygame.draw.rect(surface, border_color, self.rect, border_width, border_radius=5)
        key_text = get_font().render(key_label(f"slot_{self.key_name.lower()}"), True, border_color)
        surface.blit(key_text, (self.rect.x + 8, self.rect.y + 5))
        self._draw_equip_particles(surface)

    def emit_equip_particles(self, color):
        """장착 순간 슬롯 중심에서 UI 공간 파티클을 방사합니다."""
        now = pygame.time.get_ticks()
        center_x, center_y = self.rect.center
        self.equip_particles = []
        for _ in range(20):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(45, 115)
            self.equip_particles.append({
                "x": center_x,
                "y": center_y,
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed,
                "started_at": now,
                "lifetime": random.randint(420, 720),
                "size": random.randint(2, 5),
                "color": color,
            })

    def _draw_equip_particles(self, surface):
        now = pygame.time.get_ticks()
        alive_particles = []
        for particle in self.equip_particles:
            age = now - particle["started_at"]
            if age >= particle["lifetime"]:
                continue
            progress = age / particle["lifetime"]
            x = particle["x"] + particle["vx"] * age / 1000
            y = particle["y"] + particle["vy"] * age / 1000
            radius = max(1, round(particle["size"] * (1 - progress)))
            pygame.draw.circle(surface, particle["color"][:3], (round(x), round(y)), radius)
            alive_particles.append(particle)
        self.equip_particles = alive_particles


def add_skill_to_inventory(skill_name):
    """새 스킬을 중복 없이 인벤토리에 추가하고 추가 여부를 반환합니다."""
    if skill_name not in SKILL_BOOK or skill_name in owned_skills:
        return False
    owned_skills.add(skill_name)
    refresh_skill_inventory()
    return True


def refresh_skill_inventory():
    """보유 스킬 목록을 화면에 표시할 아이콘으로 다시 만듭니다."""
    if _ui_state.selected_skill not in owned_skills:
        _ui_state.selected_skill = None
    inventory_items.clear()
    item_width = SKILL_ICON_SIZE + SKILL_ICON_GAP_X
    item_height = SKILL_ICON_SIZE + SKILL_ICON_GAP_Y

    visible_skills = (
        [name for name in SKILL_BOOK if name in owned_skills]
        if settings["owned_skills_only"]
        else list(SKILL_BOOK)
    )
    for index, skill_name in enumerate(visible_skills):
        row, column = divmod(index, INVENTORY_ITEM_COLUMNS)
        inventory_items.append(
            SkillWindowItem(
                SKILL_ICON_START_X + column * item_width,
                SKILL_ICON_START_Y + row * item_height,
                skill_name,
                skill_name in owned_skills,
            )
        )


inventory_items = []
refresh_skill_inventory()
quick_slots = [
    # 스킬 장착 후 표시되는 퀵슬롯의 가로 위치와 간격입니다.
    QuickSlot(QUICK_SLOT_START_X + index * (QUICK_SLOT_SIZE + 20), QUICK_SLOT_Y, key_name)
    for index, key_name in enumerate(("Q", "E", "T"))
]


def assign_skill_to_quick_slot(slot, skill_name):
    """보유 스킬을 지정한 퀵슬롯에 중복 없이 장착합니다."""
    if skill_name not in SKILL_BOOK or skill_name not in owned_skills:
        return False

    duplicate_slot = next(
        (
            other_slot
            for other_slot in quick_slots
            if other_slot is not slot and other_slot.assigned_skill == skill_name
        ),
        None,
    )
    if duplicate_slot:
        return False

    # 실제 스킬 장착 상태를 바꾸는 지점입니다.
    slot.assigned_skill = skill_name
    slot.emit_equip_particles(SKILL_BOOK[skill_name].color)
    return True


def select_skill_at(position):
    """클릭한 보유 스킬을 키 지정 대상으로 선택합니다."""
    _ui_state.selected_skill = next(
        (
            item.skill_name
            for item in inventory_items
            if item.is_owned and item.rect.collidepoint(position)
        ),
        None,
    )
    return _ui_state.selected_skill


def bind_selected_skill(key_name):
    """선택한 스킬을 Q/E/T 슬롯에 지정합니다."""
    if _ui_state.selected_skill is None:
        return None, False
    slot = next((item for item in quick_slots if item.key_name == key_name), None)
    if slot is None:
        return _ui_state.selected_skill, False
    skill_name = _ui_state.selected_skill
    if assign_skill_to_quick_slot(slot, skill_name):
        _ui_state.selected_skill = None
        return skill_name, True
    return skill_name, False


def clear_selected_skill():
    _ui_state.selected_skill = None

mouse_pos = (0, 0)
system_message = "I를 눌러 인벤토리를 열고, 보유 스킬을 선택한 뒤 Q/E/T로 장착하세요."

SKILL_PANEL_RECT = pygame.Rect(SKILL_PANEL_X, SKILL_PANEL_Y, *SKILL_PANEL_SIZE)
def draw_skill_panel(surface):
    if _ui_state.skill_panel_image:
        surface.blit(_ui_state.skill_panel_image, SKILL_PANEL_RECT)
    else:
        pygame.draw.rect(surface, (30, 30, 50), SKILL_PANEL_RECT, border_radius=10)


def draw_skill_inventory(surface, mouse_pos, is_open):
    # 인벤토리는 I 키로 열었을 때만 화면과 입력을 활성화합니다.
    if not is_open:
        return None
    inventory_rect = pygame.Rect(INVENTORY_X, INVENTORY_Y, *INVENTORY_SIZE)
    pygame.draw.rect(surface, (18, 22, 42), inventory_rect, border_radius=12)
    pygame.draw.rect(surface, (110, 180, 255), inventory_rect, 2, border_radius=12)
    title = get_font().render(
        f"스킬 인벤토리  {len(owned_skills)}/{len(SKILL_BOOK)}",
        True,
        (180, 225, 255),
    )
    surface.blit(title, (inventory_rect.x + 20, inventory_rect.y + 18))
    guide = get_small_font().render("아이콘 선택 후 Q / E / T 키로 장착", True, (190, 205, 225))
    surface.blit(guide, (inventory_rect.x + 20, inventory_rect.y + 42))

    hovered_skill = None
    for item in inventory_items:
        item.update(mouse_pos)
        item.draw(surface)
        if item.is_hovering and item.is_owned:
            hovered_skill = item.skill_name

    return hovered_skill


def draw_skill_tooltip(surface, mouse_pos, skill_name):
    if skill_name is None:
        return
    skill = SKILL_BOOK[skill_name]
    font = get_small_font()
    lines = [f"{skill.name}", f"공격력: {skill.Power}", skill.Ability]
    rendered = [font.render(line, True, WHITE) for line in lines]
    padding = 10
    width = max(text.get_width() for text in rendered) + padding * 2
    height = sum(text.get_height() for text in rendered) + padding * 2 + 5
    x = min(mouse_pos[0] + 20, SCREEN_WIDTH - width - 10)
    y = min(mouse_pos[1] - 10, SCREEN_HEIGHT - height - 10)
    rect = pygame.Rect(x, y, width, height)
    pygame.draw.rect(surface, (20, 20, 40), rect, border_radius=5)
    pygame.draw.rect(surface, skill.color, rect, 2, border_radius=5)
    offset = y + padding
    for text in rendered:
        surface.blit(text, (x + padding, offset))
        offset += text.get_height() + 3
