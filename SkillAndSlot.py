import pygame
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

# 글로벌 이미지 로더
image_loader = None

def set_image_loader(loader):
    global image_loader
    image_loader = loader



FONT = None
QUICK_SLOT_IMAGE = None
SKILL_SLOT_IMAGE = None
SKILL_PANEL_IMAGE = None

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
DARK_GRAY = (70, 70, 70)
RED = (255, 100, 100)
BLUE = (100, 100, 255)
YELLOW = (255, 255, 100)


def get_font():
    global FONT
    if FONT is None:
        FONT = pygame.font.SysFont("malgungothic", 14)
    return FONT


def set_ui_assets(skill_window_image, quick_slot_image):
    global QUICK_SLOT_IMAGE, SKILL_SLOT_IMAGE, SKILL_PANEL_IMAGE
    SKILL_PANEL_IMAGE = pygame.transform.smoothscale(skill_window_image, SKILL_PANEL_SIZE)
    QUICK_SLOT_IMAGE = pygame.transform.smoothscale(quick_slot_image, (QUICK_SLOT_SIZE, QUICK_SLOT_SIZE))
    SKILL_SLOT_IMAGE = pygame.transform.smoothscale(quick_slot_image, (SKILL_ICON_SIZE, SKILL_ICON_SIZE))


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
    "매의 눈": Skill("매의 눈", (120, 220, 255), "시야가 넓어집니다!", 0, "3초간 고정 반경의 넓은 원형 시야"),
    "와드": Skill("와드", (120, 240, 255), "와드를 설치했습니다!", 0, "설치한 위치의 시야를 밝힘"),
    "부활의 차": Skill("부활의 차", (255, 210, 120), "죽음을 한 번 초월합니다!", 0, "퀵슬롯 장착 중 사망 시 한 번 부활하고 사라짐"),
    "보호막": Skill("보호막", (100, 255, 180), "보호막이 생겼습니다!", 0, "5초간 피해 무효화"),
    "은신": Skill("은신", (190, 190, 220), "몸을 숨겼습니다!", 0, "4.5초간 적에게 완전히 보이지 않음"),
    "텔포": Skill("텔포", (180, 255, 180), "시전자 위치에 5초간 텔포석상을 만들고 다시 누르면 이동합니다.", 0, "5초 지속 후 15초 쿨타임"),
    "기절탄": Skill("기절탄", (255, 245, 180), "맞은 플레이어를 2.5초 동안 기절시킵니다.", 10, "흰색 탄환, 적중 시 2.5초 스턴"),
}

# 현재 보유 중인 스킬입니다. 도감(SKILL_BOOK)과 달리 실제 획득 목록만 표시합니다.
owned_skills = set()


class SkillWindowItem:
    def __init__(self, x, y, skill_name, is_owned=False):
        self.rect = pygame.Rect(x, y, SKILL_ICON_SIZE, SKILL_ICON_SIZE)
        self.skill_name = skill_name
        self.is_owned = is_owned
        self.is_hovering = False

    def update(self, mouse_pos):
        self.is_hovering = self.rect.collidepoint(mouse_pos)

    def draw(self, surface):
        global image_loader
        skill = SKILL_BOOK[self.skill_name]
        border_color = (255, 255, 0) if self.is_hovering and self.is_owned else BLACK
        border_width = 3 if self.is_hovering else 2
        icon_surface = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        
        # 스킬 아이콘 이미지가 있으면 표시, 없으면 색상 박스 표시
        if SKILL_SLOT_IMAGE:
            icon_surface.blit(SKILL_SLOT_IMAGE, (0, 0))
        else:
            pygame.draw.rect(icon_surface, skill.color, icon_surface.get_rect(), border_radius=5)
        
        # 스킬 아이콘 이미지 표시
        if image_loader:
            skill_icon = image_loader.GetSkillIcon(self.skill_name)
            if skill_icon:
                icon_surface.blit(skill_icon, (0, 0))
            else:
                pygame.draw.rect(icon_surface, skill.color, icon_surface.get_rect().inflate(-12, -12), border_radius=4)
                text = get_font().render(skill.name[:2], True, BLACK)
                icon_surface.blit(text, text.get_rect(center=icon_surface.get_rect().center))
        else:
            pygame.draw.rect(icon_surface, skill.color, icon_surface.get_rect().inflate(-12, -12), border_radius=4)
            text = get_font().render(skill.name[:2], True, BLACK)
            icon_surface.blit(text, text.get_rect(center=icon_surface.get_rect().center))

        if not self.is_owned:
            icon_surface.set_alpha(INVENTORY_ITEM_ALPHA)
        surface.blit(icon_surface, self.rect)
        
        pygame.draw.rect(surface, border_color, self.rect, border_width, border_radius=5)


class QuickSlot:
    def __init__(self, x, y, key_name):
        self.rect = pygame.Rect(x, y, QUICK_SLOT_SIZE, QUICK_SLOT_SIZE)
        self.key_name = key_name
        self.assigned_skill = None
        self.is_hovering = False

    def update(self, mouse_pos):
        self.is_hovering = self.rect.collidepoint(mouse_pos)

    def draw(self, surface):
        global image_loader
        border_color = (255, 255, 100) if self.is_hovering else WHITE
        border_width = 3 if self.is_hovering else 2
        if QUICK_SLOT_IMAGE:
            surface.blit(QUICK_SLOT_IMAGE, self.rect)
        else:
            pygame.draw.rect(surface, DARK_GRAY, self.rect, border_radius=5)

        content_rect = self.rect.inflate(-12, -12)
        if self.assigned_skill:
            skill = SKILL_BOOK[self.assigned_skill]
            
            # 스킬 아이콘 이미지가 있으면 표시
            if image_loader:
                skill_icon = image_loader.GetSkillIcon(self.assigned_skill)
                if skill_icon:
                    # 스킬 아이콘을 퀵슬롯의 정중앙에 배치합니다.
                    icon_rect = skill_icon.get_rect(center=self.rect.center)
                    surface.blit(skill_icon, icon_rect)
                else:
                    pygame.draw.rect(surface, skill.color, content_rect, border_radius=4)
                    text = get_font().render(skill.name[:2], True, BLACK)
                    surface.blit(text, text.get_rect(center=(self.rect.centerx, self.rect.centery + 5)))
                    power_text = pygame.font.SysFont("malgungothic", 12).render(f"P:{skill.Power}", True, BLACK)
                    surface.blit(power_text, (self.rect.x + 5, self.rect.bottom - 20))
            else:
                pygame.draw.rect(surface, skill.color, content_rect, border_radius=4)
                text = get_font().render(skill.name[:2], True, BLACK)
                surface.blit(text, text.get_rect(center=(self.rect.centerx, self.rect.centery + 5)))
                power_text = pygame.font.SysFont("malgungothic", 12).render(f"P:{skill.Power}", True, BLACK)
                surface.blit(power_text, (self.rect.x + 5, self.rect.bottom - 20))
        else:
            text = get_font().render("EMPTY", True, (150, 150, 150))
            surface.blit(text, text.get_rect(center=self.rect.center))

        pygame.draw.rect(surface, border_color, self.rect, border_width, border_radius=5)
        key_text = get_font().render(self.key_name, True, border_color)
        surface.blit(key_text, (self.rect.x + 8, self.rect.y + 5))


def add_skill_to_inventory(skill_name):
    """새 스킬을 중복 없이 인벤토리에 추가하고 추가 여부를 반환합니다."""
    if skill_name not in SKILL_BOOK or skill_name in owned_skills:
        return False
    owned_skills.add(skill_name)
    refresh_skill_inventory()
    return True


def refresh_skill_inventory():
    """보유 스킬 목록을 화면에 표시할 아이콘으로 다시 만듭니다."""
    inventory_items.clear()
    item_width = SKILL_ICON_SIZE + SKILL_ICON_GAP_X
    item_height = SKILL_ICON_SIZE + SKILL_ICON_GAP_Y

    for index, skill_name in enumerate(SKILL_BOOK):
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
    return True

dragging_skill = None
drag_offset_x = 0
drag_offset_y = 0
mouse_pos = (0, 0)
system_message = "I를 눌러 인벤토리를 열고, 보유 스킬을 드래그해서 장착하세요!"

SKILL_PANEL_RECT = pygame.Rect(SKILL_PANEL_X, SKILL_PANEL_Y, *SKILL_PANEL_SIZE)
def draw_skill_panel(surface):
    if SKILL_PANEL_IMAGE:
        surface.blit(SKILL_PANEL_IMAGE, SKILL_PANEL_RECT)
    else:
        pygame.draw.rect(surface, (30, 30, 50), SKILL_PANEL_RECT, border_radius=10)


def draw_skill_inventory(surface, mouse_pos, is_open, dragging_skill):
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

    hovered_skill = None
    for item in inventory_items:
        item.update(mouse_pos)
        item.draw(surface)
        if item.is_hovering and item.is_owned:
            hovered_skill = item.skill_name

    draw_drag_preview(surface, mouse_pos, dragging_skill)

    return hovered_skill


def draw_drag_preview(surface, mouse_pos, skill_name):
    """마우스를 따라다니는 실제 스킬 아이콘 미리보기입니다."""
    if not skill_name:
        return

    skill = SKILL_BOOK[skill_name]
    preview = pygame.Surface((SKILL_ICON_SIZE, SKILL_ICON_SIZE), pygame.SRCALPHA)

    # 보유 스킬의 원본 아이콘을 사용해 드래그 중에도 어떤 스킬인지 보이게 합니다.
    skill_icon = image_loader.GetSkillIcon(skill_name) if image_loader else None
    if skill_icon:
        preview.blit(skill_icon, (0, 0))
    else:
        pygame.draw.rect(preview, skill.color, preview.get_rect(), border_radius=5)
        text = get_font().render(skill.name[:2], True, BLACK)
        preview.blit(text, text.get_rect(center=preview.get_rect().center))

    # 반투명 테두리는 드래그 중인 아이콘이 슬롯에 놓일 수 있음을 표시합니다.
    preview.set_alpha(220)
    pygame.draw.rect(preview, (255, 220, 100), preview.get_rect(), 3, border_radius=6)
    preview_rect = preview.get_rect(center=mouse_pos)
    surface.blit(preview, preview_rect)


def draw_skill_tooltip(surface, mouse_pos, skill_name):
    if skill_name is None:
        return
    skill = SKILL_BOOK[skill_name]
    font = pygame.font.SysFont("malgungothic", 12)
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
