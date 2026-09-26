import pygame
import random
import math
from Config import (
    MAP_HOUSE_COUNT,
    MAP_HOUSE_PADDING,
    MAP_HOUSE_MAX_SIZE,
    MAP_HOUSE_MIN_SIZE,
    MAP_SAFE_ZONE_MAX,
    MAP_SAFE_ZONE_MIN,
    MAP_BUSH_COUNT,
    MAP_BUSH_CLUSTER_COUNT,
    MAP_BUSH_CLUSTER_RADIUS_MIN,
    MAP_BUSH_CLUSTER_RADIUS_MAX,
    MAP_TREASURE_CHANCE,
    MAP_RUNE_COUNT,
    MAP_FURNITURE_CHANCE,
    MAP_STONE_COUNT,
    MAP_WATER_RADIUS,
)
from shapely.geometry import Polygon
from shapely.ops import unary_union
from ImageLoad import Imageload

VISION_CIRCLE = "circle"       # 360도 원형 시야
VISION_CONE = "cone"            # 지정한 각도의 부채꼴 시야
VISION_RECTANGLE = "rectangle"  # 전방 직사각형 시야
VISION_LINE = "line"            # 전방의 얇은 직선 시야
# [커스텀 가능] 타일 한 칸의 픽셀 크기입니다. 맵 해상도와 렌더링 비용에 영향을 줍니다.
DEFAULT_TILE_SIZE = 32

class Tile:
    def __init__(self, tile_type, is_walkable):
        # [커스텀 가능] 새 타일 종류의 번호와 이동 가능 여부를 설정합니다.
        self.tile_type = tile_type
        self.is_walkable = is_walkable

class TileGenerator:
    def __init__(self, tile_size=DEFAULT_TILE_SIZE):
        self.IML = Imageload()  # Imageload 인스턴스 생성
        self.tile_size = tile_size
        # [커스텀 가능] 타일 번호별 Surface를 등록하는 딕셔너리입니다.
        self.tile_images = {}
        # [커스텀 가능] (타일 x, 타일 y): Tile 객체 형태의 맵 데이터입니다.
        self.map_data = {}
        self.map_width = 0
        self.map_height = 0
        self.house_rects = []
        self.stone_objects = []
        self.world_surface = None
        self._scaled_world_surface = None
        self._scaled_world_zoom = None
        # 플레이어와 목표 지점의 타일 단위 시야 판정 캐시입니다.
        self._visibility_cache = {}
        # 시야 계산에 사용할 벽 타일 목록입니다.
        self._vision_wall_rects = None
        
        # 이미지 풀링 생성
        self._load_placeholder_images()
        
        # ⚠️ [멀티플레이 최적화 수정] 
        # 서버에서 시드(Seed)를 받아오기 전에 생성자가 먼저 작동하므로,
        # 인스턴스 초기화 단계에서의 임의 맵 생성(generate_map) 구문은 제거했습니다.

    def _load_placeholder_images(self):
        """이미지 풀링: 바닥과 집 벽면 타일을 시각적으로 디자인"""
        # [커스텀 가능] 아래 tile_images[번호] 블록에서 타일 색상, 텍스처, 모양을 변경합니다.
        # -------------------------------------
        # 0: 기본 바닥 (부드러운 잔디/흙 느낌의 연녹색)
        # -------------------------------------
        floor = pygame.Surface((self.tile_size, self.tile_size))
        floor.fill((140, 180, 130)) # [커스텀 가능] 바닥 기본 색상
        self.tile_images[0] = floor

        # -------------------------------------
        # 1: 집 벽면 / 장애물 벽 타일 (붉은 벽돌 및 지붕 느낌)
        # -------------------------------------
        wall = pygame.Surface((self.tile_size, self.tile_size))
        
        wall_texture = pygame.transform.scale(
            self.IML.GetTileTest(),
            (self.tile_size, self.tile_size),
        )
        wall.fill((140, 180, 130))  # 바닥색
        wall.blit(wall_texture, (0, 0))
        
        self.tile_images[1] = wall
        
        # -------------------------------------
        # 2: 문 타일 (갈색, 열림 표시)
        # -------------------------------------
        door = pygame.Surface((self.tile_size, self.tile_size))
        door.fill((140, 180, 130))  # 바닥색
        door_width = max(8, round(self.tile_size * 0.95))
        door_height = self.tile_size
        door_x = (self.tile_size - door_width) // 2
        door_y = max(0, (self.tile_size - door_height) // 2)
        pygame.draw.rect(door, (101, 67, 33), (door_x, door_y, door_width, door_height))
        pygame.draw.rect(door, (255, 200, 100), (door_x, door_y, door_width, door_height), 2)
        pygame.draw.circle(door, (200, 150, 50), (door_x + door_width - 5, self.tile_size // 2), 3)
        self.tile_images[2] = door
        
        # -------------------------------------
        # 3: 보물상자 (황금색)
        # -------------------------------------
        treasure = pygame.Surface((self.tile_size, self.tile_size))
        treasure.fill((140, 180, 130))  # 바닥색
        chest_x = self.tile_size // 6
        chest_y = self.tile_size // 3
        chest_width = self.tile_size - chest_x * 2
        chest_height = max(8, self.tile_size // 3)
        pygame.draw.rect(treasure, (200, 150, 50), (chest_x, chest_y, chest_width, chest_height))
        pygame.draw.rect(treasure, (255, 200, 0), (chest_x, chest_y, chest_width, chest_height), 1)
        pygame.draw.line(treasure, (150, 100, 0), (self.tile_size // 2, chest_y), (self.tile_size // 2, chest_y + chest_height), 1)
        self.tile_images[3] = treasure

        # 4: 통과할 수 있는 은신용 덤불입니다.
        bush = pygame.Surface((self.tile_size, self.tile_size), pygame.SRCALPHA)
        center = self.tile_size // 2
        pygame.draw.circle(bush, (45, 105, 45), (center, center), max(5, self.tile_size // 3))
        for angle in range(0, 360, 45):
            direction = pygame.Vector2(1, 0).rotate(angle)
            tip = pygame.Vector2(center, center) + direction * (self.tile_size * 0.45)
            pygame.draw.line(bush, (120, 190, 90), (center, center), tip, 2)
        self.tile_images[4] = bush

        rune = pygame.Surface((self.tile_size, self.tile_size), pygame.SRCALPHA)
        rune_center = self.tile_size // 2
        rune_points = [
            (rune_center, 4),
            (self.tile_size - 5, rune_center),
            (rune_center, self.tile_size - 4),
            (5, rune_center),
        ]
        pygame.draw.polygon(rune, (40, 180, 210, 120), rune_points)
        pygame.draw.polygon(rune, (170, 245, 255, 230), rune_points, 2)
        pygame.draw.circle(rune, (230, 255, 180, 220), (rune_center, rune_center), 3)
        self.tile_images[5] = rune

        bed = pygame.Surface((self.tile_size, self.tile_size), pygame.SRCALPHA)
        pygame.draw.rect(bed, (135, 75, 55), (3, 7, self.tile_size - 6, self.tile_size - 10), border_radius=3)
        pygame.draw.rect(bed, (235, 220, 190), (6, 10, self.tile_size - 12, self.tile_size // 2), border_radius=2)
        pygame.draw.line(bed, (90, 45, 35), (4, self.tile_size - 5), (self.tile_size - 4, self.tile_size - 5), 2)
        self.tile_images[7] = bed

        chair = pygame.Surface((self.tile_size, self.tile_size), pygame.SRCALPHA)
        pygame.draw.rect(chair, (150, 90, 45), (8, 8, self.tile_size - 16, 10), border_radius=2)
        pygame.draw.rect(chair, (120, 70, 35), (10, 17, self.tile_size - 20, 10), border_radius=2)
        pygame.draw.line(chair, (100, 55, 30), (11, 27), (8, self.tile_size - 3), 3)
        pygame.draw.line(chair, (100, 55, 30), (self.tile_size - 11, 27), (self.tile_size - 8, self.tile_size - 3), 3)
        self.tile_images[8] = chair

        stone = pygame.Surface((self.tile_size, self.tile_size), pygame.SRCALPHA)
        stone_points = [(5, 22), (9, 9), (20, 4), (29, 12), (26, 27), (14, 30)]
        pygame.draw.polygon(stone, (105, 110, 120), stone_points)
        pygame.draw.polygon(stone, (190, 195, 205), stone_points, 2)
        pygame.draw.line(stone, (145, 150, 160), (10, 12), (22, 24), 2)
        self.tile_images[9] = stone

        water = pygame.Surface((self.tile_size, self.tile_size), pygame.SRCALPHA)
        water.fill((45, 145, 205, 210))
        pygame.draw.line(water, (150, 225, 255), (4, self.tile_size // 3), (self.tile_size - 4, self.tile_size // 3), 2)
        pygame.draw.line(water, (100, 205, 245), (8, self.tile_size * 2 // 3), (self.tile_size - 6, self.tile_size * 2 // 3), 2)
        self.tile_images[6] = water

    def generate_map(self, width_tiles, height_tiles, seed_value=None):
        """★멀티플레이 동기화 핵심★: 서버 시드로 난수를 고정하여 모두에게 똑같은 집을 배치합니다."""
        if seed_value is not None:
            random.seed(seed_value) # 👈 이 구문이 돌면서 모든 유저 컴퓨터의 난수 발생 순서가 고정됩니다.

        self.map_data.clear() # 기존 데이터 초기화
        self.stone_objects.clear()
        self.map_width = width_tiles
        self.map_height = height_tiles

        # 바닥과 외곽 벽을 한 번에 만들어 경계 타일 객체를 덮어쓰지 않습니다.
        for y in range(height_tiles):
            for x in range(width_tiles):
                is_border = x == 0 or x == width_tiles - 1 or y == 0 or y == height_tiles - 1
                self.map_data[(x, y)] = Tile(
                    tile_type=1 if is_border else 0,
                    is_walkable=not is_border,
                )

        # 3. 맵 중간중간 무작위 위치에 '집' 형태 구조물 빌드
        # ★ [개선] 집의 윤곽선만 벽으로 생성 (내부는 비워 플레이어가 드나들 수 있음)
        # ★ [추가] 문과 보물상자 추가
        num_houses = MAP_HOUSE_COUNT
        self.house_rects = []
        safe_zone = pygame.Rect(
            MAP_SAFE_ZONE_MIN,
            MAP_SAFE_ZONE_MIN,
            MAP_SAFE_ZONE_MAX - MAP_SAFE_ZONE_MIN,
            MAP_SAFE_ZONE_MAX - MAP_SAFE_ZONE_MIN,
        )
        attempts = 0
        while len(self.house_rects) < num_houses and attempts < num_houses * 10:
            attempts += 1
            # 맵 중앙 안쪽 안전한 좌표를 선택합니다.
            house_w = random.randint(MAP_HOUSE_MIN_SIZE, MAP_HOUSE_MAX_SIZE)
            house_h = random.randint(MAP_HOUSE_MIN_SIZE, MAP_HOUSE_MAX_SIZE)
            house_x = random.randint(12, max(12, width_tiles - house_w - 12))
            house_y = random.randint(12, max(12, height_tiles - house_h - 12))

            candidate = pygame.Rect(
                house_x - MAP_HOUSE_PADDING,
                house_y - MAP_HOUSE_PADDING,
                house_w + MAP_HOUSE_PADDING * 2,
                house_h + MAP_HOUSE_PADDING * 2,
            )
            if candidate.colliderect(safe_zone) or any(
                candidate.colliderect(existing) for existing in self.house_rects
            ):
                continue

            self.house_rects.append(candidate)
            
            # 집의 윤곽선만 벽으로 생성 (테두리만 1, 내부는 바닥 0)
            for hy in range(house_y, house_y + house_h):
                for hx in range(house_x, house_x + house_w):
                    # 집의 테두리(위, 아래, 좌, 우)만 벽으로 설정
                    is_border = (hy == house_y or hy == house_y + house_h - 1 or 
                                 hx == house_x or hx == house_x + house_w - 1)
                    
                    if is_border:
                        self.map_data[(hx, hy)] = Tile(tile_type=1, is_walkable=False)
                    else:
                        # 내부는 바닥으로 유지 (집 내부는 이동 가능)
                        self.map_data[(hx, hy)] = Tile(tile_type=0, is_walkable=True)
            
            # ★ [추가] 집에 문 배치 (테두리 중 랜덤한 위치, 4개 방향 중 선택)
            door_x = random.randint(house_x + 1, house_x + house_w - 4)
            door_y = random.randint(house_y + 1, house_y + house_h - 4)
            door_sides = [
                # 각 방향으로 세 칸을 열어 넓은 출입구를 만듭니다.
                ((door_x, house_y), (door_x + 1, house_y), (door_x + 2, house_y)),  # 위쪽
                ((door_x, house_y + house_h - 1), (door_x + 1, house_y + house_h - 1), (door_x + 2, house_y + house_h - 1)),  # 아래쪽
                ((house_x, door_y), (house_x, door_y + 1), (house_x, door_y + 2)),  # 좌측
                ((house_x + house_w - 1, door_y), (house_x + house_w - 1, door_y + 1), (house_x + house_w - 1, door_y + 2)),  # 우측
            ]
            door_positions = random.choice(door_sides)
            for door_pos in door_positions:
                self.map_data[door_pos] = Tile(tile_type=2, is_walkable=True)  # 문은 통과 가능
            
            # 집마다 설정된 확률로 보물상자를 하나 배치합니다.
            # 확률은 Config.py의 MAP_TREASURE_CHANCE에서 조정합니다.
            if random.random() < MAP_TREASURE_CHANCE and house_w > 2 and house_h > 2:
                treasure_x = random.randint(house_x + 1, house_x + house_w - 2)
                treasure_y = random.randint(house_y + 1, house_y + house_h - 2)
                self.map_data[(treasure_x, treasure_y)] = Tile(tile_type=3, is_walkable=True)  # 보물상자

        self._place_bushes()
        self._place_runes()
        self._place_furniture()
        self._place_stones()
        self._place_central_water()

        self._build_world_surface()
        self._visibility_cache.clear()
        self._vision_wall_rects = None

    def _place_bushes(self):
        """집과 외곽 벽을 피해 여러 클러스터로 은신용 덤불을 배치합니다."""
        available = {
            (x, y)
            for y in range(1, self.map_height - 1)
            for x in range(1, self.map_width - 1)
            if self.map_data[(x, y)].tile_type == 0
            and not any(house.collidepoint(x, y) for house in self.house_rects)
        }
        centers = list(available)
        random.shuffle(centers)
        placed = 0

        for center_x, center_y in centers[:MAP_BUSH_CLUSTER_COUNT]:
            if placed >= MAP_BUSH_COUNT or (center_x, center_y) not in available:
                continue
            radius = random.randint(MAP_BUSH_CLUSTER_RADIUS_MIN, MAP_BUSH_CLUSTER_RADIUS_MAX)
            cluster = [
                (tile_x, tile_y)
                for tile_x, tile_y in available
                if (tile_x - center_x) ** 2 + (tile_y - center_y) ** 2 <= radius ** 2
            ]
            random.shuffle(cluster)
            for tile_x, tile_y in cluster:
                if placed >= MAP_BUSH_COUNT:
                    break
                self.map_data[(tile_x, tile_y)] = Tile(tile_type=4, is_walkable=True)
                available.remove((tile_x, tile_y))
                placed += 1

    def _place_runes(self):
        """맵마다 같은 씨앗으로 탐험 지점을 만드는 발광 룬을 배치합니다."""
        available = [
            position
            for position, tile in self.map_data.items()
            if tile.tile_type == 0
        ]
        random.shuffle(available)
        for tile_x, tile_y in available[:MAP_RUNE_COUNT]:
            self.map_data[(tile_x, tile_y)] = Tile(tile_type=5, is_walkable=True)

    def _place_furniture(self):
        """집 내부에 시야와 이동을 막는 파괴 가능한 가구를 배치합니다."""
        for house in self.house_rects:
            house_left = house.left + MAP_HOUSE_PADDING + 1
            house_top = house.top + MAP_HOUSE_PADDING + 1
            house_right = house.right - MAP_HOUSE_PADDING - 2
            house_bottom = house.bottom - MAP_HOUSE_PADDING - 2
            if house_right - house_left < 4 or house_bottom - house_top < 3:
                continue
            if random.random() > MAP_FURNITURE_CHANCE:
                continue

            bed_x = random.randint(house_left, house_right - 1)
            bed_y = random.randint(house_top, house_bottom)
            for tile_x in (bed_x, bed_x + 1):
                self.map_data[(tile_x, bed_y)] = Tile(tile_type=7, is_walkable=False)

            chair_x = random.randint(house_left, house_right)
            chair_y = random.randint(house_top, house_bottom)
            if self.map_data[(chair_x, chair_y)].tile_type == 0:
                self.map_data[(chair_x, chair_y)] = Tile(tile_type=8, is_walkable=False)

    def _place_stones(self):
        """집과 중앙 안전 지대를 피해 총알을 튕겨내는 돌을 배치합니다."""
        available = [
            position
            for position, tile in self.map_data.items()
            if tile.tile_type == 0
            and not any(house.collidepoint(*position) for house in self.house_rects)
        ]
        random.shuffle(available)
        center_x = self.map_width // 2
        center_y = self.map_height // 2
        placed = 0
        for tile_x, tile_y in available:
            if placed >= MAP_STONE_COUNT:
                break
            if (tile_x - center_x) ** 2 + (tile_y - center_y) ** 2 <= (MAP_WATER_RADIUS + 3) ** 2:
                continue
            stone_rect = pygame.Rect(
                tile_x * self.tile_size - self.tile_size // 3,
                tile_y * self.tile_size - self.tile_size // 3,
                round(self.tile_size * 1.65),
                round(self.tile_size * 1.45),
            )
            self.stone_objects.append({"rect": stone_rect, "tile": (tile_x, tile_y)})
            placed += 1

    def _place_central_water(self):
        center_x = self.map_width // 2
        center_y = self.map_height // 2
        for tile_y in range(center_y - MAP_WATER_RADIUS, center_y + MAP_WATER_RADIUS + 1):
            for tile_x in range(center_x - MAP_WATER_RADIUS, center_x + MAP_WATER_RADIUS + 1):
                if (tile_x - center_x) ** 2 + (tile_y - center_y) ** 2 <= MAP_WATER_RADIUS ** 2:
                    tile = self.map_data.get((tile_x, tile_y))
                    if tile and tile.tile_type in (0, 5):
                        self.map_data[(tile_x, tile_y)] = Tile(tile_type=6, is_walkable=True)

    def is_in_bush(self, world_x, world_y):
        """월드 좌표가 덤불 안에 있는지 확인합니다."""
        tile_x = int(world_x // self.tile_size)
        tile_y = int(world_y // self.tile_size)
        tile = self.map_data.get((tile_x, tile_y))
        return bool(tile and tile.tile_type == 4)

    def is_in_water(self, world_x, world_y):
        tile_x = int(world_x // self.tile_size)
        tile_y = int(world_y // self.tile_size)
        tile = self.map_data.get((tile_x, tile_y))
        return bool(tile and tile.tile_type == 6)

    def _build_world_surface(self):
        """정적인 맵을 한 장으로 합쳐 매 프레임 타일을 반복 그리지 않습니다."""
        world_size = (
            self.map_width * self.tile_size,
            self.map_height * self.tile_size,
        )
        self.world_surface = pygame.Surface(world_size).convert()
        for (tile_x, tile_y), tile in self.map_data.items():
            self._draw_world_tile(tile_x, tile_y, tile)
        self._scaled_world_surface = None
        self._scaled_world_zoom = None

    def _draw_world_tile(self, tile_x, tile_y, tile):
        self.world_surface.blit(
            self.tile_images[tile.tile_type],
            (tile_x * self.tile_size, tile_y * self.tile_size),
        )
        if tile.tile_type != 0:
            return
        # 타일 경계선 대신 좌표 기반 잔디 결을 넣어 반복 무늬를 줄입니다.
        tile_rng = random.Random(tile_x * 73856093 ^ tile_y * 19349663)
        tile_left = tile_x * self.tile_size
        tile_top = tile_y * self.tile_size
        for _ in range(3):
            detail_x = tile_left + tile_rng.randrange(4, self.tile_size - 4)
            detail_y = tile_top + tile_rng.randrange(4, self.tile_size - 4)
            detail_color = tile_rng.choice(((116, 161, 105), (157, 192, 138), (126, 171, 112)))
            pygame.draw.line(
                self.world_surface,
                detail_color,
                (detail_x, detail_y),
                (detail_x + tile_rng.choice((-2, -1, 1, 2)), detail_y - 3),
                1,
            )

    def draw(self, surface, camera_x, camera_y, zoom=1.0):
        """미리 합성한 월드 Surface를 카메라 위치에 맞춰 그립니다."""
        if self.world_surface is not None:
            if zoom == 1.0:
                surface.blit(self.world_surface, (-int(camera_x), -int(camera_y)))
            else:
                if self._scaled_world_zoom != zoom:
                    self._scaled_world_surface = pygame.transform.smoothscale(
                        self.world_surface,
                        (round(self.world_surface.get_width() * zoom), round(self.world_surface.get_height() * zoom)),
                    )
                    self._scaled_world_zoom = zoom
                surface.blit(self._scaled_world_surface, (-round(camera_x * zoom), -round(camera_y * zoom)))
        self.draw_stones(surface, camera_x, camera_y, zoom)

    def draw_stones(self, surface, camera_x, camera_y, zoom=1.0):
        """타일과 분리된 큰 돌 오브젝트를 그립니다."""
        for stone in self.stone_objects:
            rect = stone["rect"]
            screen_rect = pygame.Rect(
                round((rect.x - camera_x) * zoom),
                round((rect.y - camera_y) * zoom),
                max(1, round(rect.width * zoom)),
                max(1, round(rect.height * zoom)),
            )
            points = [
                (screen_rect.left + screen_rect.width // 4, screen_rect.top),
                (screen_rect.right - screen_rect.width // 5, screen_rect.top + screen_rect.height // 8),
                (screen_rect.right, screen_rect.centery),
                (screen_rect.right - screen_rect.width // 5, screen_rect.bottom),
                (screen_rect.left + screen_rect.width // 5, screen_rect.bottom - screen_rect.height // 8),
                (screen_rect.left, screen_rect.centery),
            ]
            pygame.draw.polygon(surface, (80, 85, 95), points)
            pygame.draw.polygon(surface, (185, 190, 200), points, max(1, round(2 * zoom)))
            pygame.draw.line(
                surface,
                (135, 140, 150),
                (screen_rect.left + screen_rect.width // 4, screen_rect.top + screen_rect.height // 4),
                (screen_rect.centerx, screen_rect.centery),
                max(1, round(2 * zoom)),
            )

    def clamp_camera(self, camera_x, camera_y, screen_width, screen_height, zoom=1.0):
        """카메라가 맵 바깥을 향하지 않도록 월드 좌표에서 제한합니다."""
        view_width = screen_width / zoom
        view_height = screen_height / zoom
        world_width = self.map_width * self.tile_size
        world_height = self.map_height * self.tile_size
        max_camera_x = max(0, world_width - view_width)
        max_camera_y = max(0, world_height - view_height)
        return (
            max(0, min(camera_x, max_camera_x)),
            max(0, min(camera_y, max_camera_y)),
        )

    def get_tile_at(self, tile_x, tile_y):
        return self.map_data.get((tile_x, tile_y))

    def find_safe_spawn(self, min_x=1, max_x=None, min_y=1, max_y=None, rng=None):
        """플레이어 크기(2x2 타일)가 완전히 바닥인 스폰 위치를 찾습니다."""
        max_x = max_x or self.map_width - 2
        max_y = max_y or self.map_height - 2
        rng = rng or random

        def is_safe(x, y):
            return all(
                self.map_data.get((x + offset_x, y + offset_y))
                and self.map_data[(x + offset_x, y + offset_y)].tile_type == 0
                for offset_y in (0, 1)
                for offset_x in (0, 1)
            )

        for _ in range(200):
            spawn = (rng.randint(min_x, max_x), rng.randint(min_y, max_y))
            if is_safe(*spawn):
                return spawn

        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                if is_safe(x, y):
                    return x, y
        return None

    def _is_wall_between(self, start_x, start_y, end_x, end_y):
        """두 점을 잇는 타일 경로에서 벽을 빠르게 찾습니다."""
        start_tile_x = int(start_x // self.tile_size)
        start_tile_y = int(start_y // self.tile_size)
        end_tile_x = int(end_x // self.tile_size)
        end_tile_y = int(end_y // self.tile_size)

        delta_x = abs(end_tile_x - start_tile_x)
        delta_y = abs(end_tile_y - start_tile_y)
        step_x = 1 if start_tile_x < end_tile_x else -1
        step_y = 1 if start_tile_y < end_tile_y else -1
        error = delta_x - delta_y
        tile_x, tile_y = start_tile_x, start_tile_y

        while (tile_x, tile_y) != (end_tile_x, end_tile_y):
            if (tile_x, tile_y) != (start_tile_x, start_tile_y):
                tile = self.map_data.get((tile_x, tile_y))
                if tile and tile.tile_type in (1, 7, 8, 9):
                    return True

            double_error = error * 2
            if double_error > -delta_y:
                error -= delta_y
                tile_x += step_x
            if double_error < delta_x:
                error += delta_x
                tile_y += step_y

        target_tile = self.map_data.get((end_tile_x, end_tile_y))
        return bool(target_tile and target_tile.tile_type in (1, 7, 8, 9))

    def is_point_visible_from(
        self,
        player_x,
        player_y,
        point_x,
        point_y,
        max_radius=250,
        vision_shape=VISION_CIRCLE,
        direction_angle=0,
        fov_angle=90,
        vision_width=None,
    ):
        """거리, 시야 모양, 벽 가림을 순서대로 판정합니다."""
        # 같은 타일 사이의 판정은 방향을 10도 단위로 묶어 재사용합니다.
        cache_key = (
            int(player_x // self.tile_size),
            int(player_y // self.tile_size),
            int(point_x // self.tile_size),
            int(point_y // self.tile_size),
            max_radius,
            vision_shape,
            int(direction_angle // 10) if vision_shape != VISION_CIRCLE else 0,
            fov_angle,
            vision_width,
        )
        if cache_key in self._visibility_cache:
            return self._visibility_cache[cache_key]

        if not self._is_point_in_vision_shape(
            player_x,
            player_y,
            point_x,
            point_y,
            max_radius,
            vision_shape,
            direction_angle,
            fov_angle,
            vision_width,
        ):
            self._visibility_cache[cache_key] = False
            return False

        # 모양 안에 있어도 벽이 사이에 있으면 보이지 않습니다.
        is_visible = not self._is_wall_between(player_x, player_y, point_x, point_y)
        self._visibility_cache[cache_key] = is_visible
        if len(self._visibility_cache) > 20000:
            self._visibility_cache.clear()
        return is_visible

    def _is_point_in_vision_shape(
        self,
        player_x,
        player_y,
        point_x,
        point_y,
        max_radius,
        vision_shape,
        direction_angle,
        fov_angle,
        vision_width,
    ):
        """벽 계산을 하기 전에 점이 시야 모양 안에 있는지 확인합니다."""
        delta_x = point_x - player_x
        delta_y = point_y - player_y
        if delta_x * delta_x + delta_y * delta_y > max_radius * max_radius:
            return False
        if vision_shape == VISION_CIRCLE:
            return True

        direction = math.radians(direction_angle)
        forward = delta_x * math.cos(direction) + delta_y * math.sin(direction)
        side = -delta_x * math.sin(direction) + delta_y * math.cos(direction)
        width = vision_width or max_radius * 0.5
        if vision_shape == VISION_LINE:
            width = min(width, 48)
        if vision_shape == VISION_CONE:
            return forward >= 0 and abs(math.degrees(math.atan2(side, forward))) <= fov_angle / 2
        if vision_shape in (VISION_RECTANGLE, VISION_LINE):
            return 0 <= forward <= max_radius and abs(side) <= width / 2
        return True

    def is_tile_visible_from(self, player_x, player_y, tile_world_x, tile_world_y, max_radius=250, **vision_options):
        """타일의 중심에서 플레이어까지 직선으로 보이는지 확인. 벽이 있으면 가려짐."""
        center_x = tile_world_x + (self.tile_size // 2)
        center_y = tile_world_y + (self.tile_size // 2)
        return self.is_point_visible_from(
            player_x,
            player_y,
            center_x,
            center_y,
            max_radius,
            **vision_options,
        )

    def get_visibility_polygon(
        self,
        player_x,
        player_y,
        max_radius=250,
        vision_shape=VISION_CIRCLE,
        direction_angle=0,
        fov_angle=90,
        vision_width=None,
        ray_samples=None,
    ):
        """시야 모양을 만들고 벽 그림자를 제거합니다. (최적화: 저격총 직선은 ray 8개, 기타는 12개)"""
        # 기본값 설정: 저격총(직선)은 8개, 나머지는 12개로 크게 줄임
        if ray_samples is None:
            ray_samples = 8 if vision_shape == VISION_LINE else 12
        
        # 1. 원형, 원뿔, 사각형, 직선 중 하나의 기본 모양을 만듭니다.
        direction = math.radians(direction_angle)
        width = vision_width or max_radius / 2
        if vision_shape == VISION_LINE:
            width = min(width, 48)

        if vision_shape == VISION_CIRCLE:
            count = max(8, ray_samples * 2)
            points = [
                (player_x + max_radius * math.cos(2 * math.pi * i / count),
                 player_y + max_radius * math.sin(2 * math.pi * i / count))
                for i in range(count)
            ]
        elif vision_shape == VISION_CONE:
            half_angle = math.radians(fov_angle) / 2
            points = [(player_x, player_y)]
            for i in range(ray_samples + 1):
                angle = direction - half_angle + 2 * half_angle * i / ray_samples
                points.append((player_x + max_radius * math.cos(angle),
                               player_y + max_radius * math.sin(angle)))
        else:
            forward = pygame.Vector2(math.cos(direction), math.sin(direction)) * max_radius
            side = pygame.Vector2(-math.sin(direction), math.cos(direction)) * width / 2
            center = pygame.Vector2(player_x, player_y)
            points = [center, center + side, center + forward + side,
                      center + forward - side, center - side]

        visible_shape = Polygon(points)

        # 2. 가까운 벽만 그림자로 만들어 시야에서 제거합니다.
        if self._vision_wall_rects is None:
            self._vision_wall_rects = [
                (x * self.tile_size, y * self.tile_size, (x + 1) * self.tile_size, (y + 1) * self.tile_size)
                for (x, y), tile in self.map_data.items() if tile.tile_type in (1, 7, 8, 9)
            ]
            self._vision_wall_rects.extend(
                (stone["rect"].left, stone["rect"].top, stone["rect"].right, stone["rect"].bottom)
                for stone in self.stone_objects
            )

        # [최적화] 저격총 같은 긴 시야는 시야각 폭만 체크 (좌우 side width)
        # 직선 시야는 width가 좁으므로, 중앙 방향 근처만 체크하면 됨
        if vision_shape == VISION_LINE:
            # 직선 시야: 중앙 광선 기준으로 좌우만 체크
            search_radius = max(max_radius * 0.3, width)  # 시야 폭 기준으로 검색
        else:
            # 원형/원뿔/사각형: 기존 대로 처리
            search_radius = max_radius + self.tile_size
        
        shadows = []
        for left, top, right, bottom in self._vision_wall_rects:
            if abs((left + right) / 2 - player_x) > search_radius or abs((top + bottom) / 2 - player_y) > search_radius:
                continue
            corners = [(left, top), (right, top), (right, bottom), (left, bottom)]
            far_corners = []
            for corner_x, corner_y in corners:
                ray = pygame.Vector2(corner_x - player_x, corner_y - player_y)
                if ray.length_squared() == 0:
                    continue
                far = pygame.Vector2(corner_x, corner_y) + ray.normalize() * (max_radius * 4)
                far_corners.append((far.x, far.y))
            if len(far_corners) == 4:
                shadows.append(Polygon([*corners, *far_corners]).convex_hull)

        # 그림자를 한 번에 합치고 시야에서 뺍니다.
        if shadows:
            visible_shape = visible_shape.difference(unary_union(shadows))
        return visible_shape
    
    def get_wall_rects(self, surface, camera_x, camera_y):
        """현재 화면 범위 안에 있는 집 벽 타일들의 '절대 좌표 Rect'를 추출 (시야 차단 연산 연동용)"""
        screen_width, screen_height = surface.get_size()
        wall_rects = []

        start_x = max(0, int(camera_x // self.tile_size))
        end_x = int((camera_x + screen_width) // self.tile_size) + 1
        
        start_y = max(0, int(camera_y // self.tile_size))
        end_y = int((camera_y + screen_height) // self.tile_size) + 1

        for y in range(start_y, end_y):
            for x in range(start_x, end_x):
                tile = self.map_data.get((x, y))
                if tile and tile.tile_type in (1, 7, 8, 9):
                    world_x = x * self.tile_size
                    world_y = y * self.tile_size
                    rect = pygame.Rect(world_x, world_y, self.tile_size, self.tile_size)
                    wall_rects.append(rect)

        wall_rects.extend(
            stone["rect"] for stone in self.stone_objects
            if stone["rect"].colliderect(
                pygame.Rect(camera_x, camera_y, screen_width, screen_height)
            )
        )
                    
        return wall_rects

    def is_walkable(self, world_x, world_y):
        """월드 좌표가 이동 가능한 지형인지 확인"""
        tile_x = int(world_x // self.tile_size)
        tile_y = int(world_y // self.tile_size)
        tile = self.map_data.get((tile_x, tile_y))
        
        if tile is None:
            return False  # 맵 범위 밖
        
        return tile.is_walkable
    
    def check_collision(self, rect):
        """Rect와 벽이 충돌하는지 확인 (rect의 중심을 기준)"""
        # Rect의 4개 모서리와 중심을 체크
        points_to_check = [
            (rect.left, rect.top),      # 좌상단
            (rect.right - 1, rect.top),     # 우상단
            (rect.left, rect.bottom - 1),   # 좌하단
            (rect.right - 1, rect.bottom - 1),  # 우하단
            (rect.centerx, rect.centery) # 중심
        ]
        
        for x, y in points_to_check:
            if not self.is_walkable(x, y):
                return True  # 충돌 감지
        if any(stone["rect"].colliderect(rect) for stone in self.stone_objects):
            return True
        
        return False  # 충돌 없음

    def check_wall_collision(self, rect):
        """Rect가 벽 타일에 닿았는지 확인합니다. 문과 바닥은 통과합니다."""
        points_to_check = [
            (rect.left, rect.top),
            (rect.right, rect.top),
            (rect.left, rect.bottom),
            (rect.right, rect.bottom),
            rect.center,
        ]

        for x, y in points_to_check:
            tile_x = int(x // self.tile_size)
            tile_y = int(y // self.tile_size)
            tile = self.map_data.get((tile_x, tile_y))
            if tile is None or tile.tile_type == 1:
                return True
        if any(stone["rect"].colliderect(rect) for stone in self.stone_objects):
            return True
        return False

    def segment_wall_collision(self, start_x, start_y, end_x, end_y, radius=2):
        """빠른 총알이 벽을 통과하지 않도록 이동 구간을 작은 점으로 검사합니다."""
        distance = math.hypot(end_x - start_x, end_y - start_y)
        steps = max(1, math.ceil(distance / max(1, self.tile_size / 4)))
        for step in range(steps + 1):
            progress = step / steps
            point_rect = pygame.Rect(0, 0, radius * 2, radius * 2)
            point_rect.center = (
                round(start_x + (end_x - start_x) * progress),
                round(start_y + (end_y - start_y) * progress),
            )
            if self.check_wall_collision(point_rect):
                return True
        return False

    def destructible_collision(self, rect):
        """총알과 파괴 가능한 가구 또는 돌의 충돌 타일을 반환합니다."""
        for stone in self.stone_objects:
            if stone["rect"].colliderect(rect):
                return stone["tile"][0], stone["tile"][1], 9
        start_x = max(0, int(rect.left // self.tile_size))
        end_x = min(self.map_width - 1, int(rect.right // self.tile_size))
        start_y = max(0, int(rect.top // self.tile_size))
        end_y = min(self.map_height - 1, int(rect.bottom // self.tile_size))
        for tile_y in range(start_y, end_y + 1):
            for tile_x in range(start_x, end_x + 1):
                tile = self.map_data.get((tile_x, tile_y))
                if tile and tile.tile_type in (7, 8, 9):
                    return tile_x, tile_y, tile.tile_type
        return None

    def destroy_furniture(self, tile_x, tile_y, rebuild_surface=True):
        tile = self.map_data.get((tile_x, tile_y))
        if not tile or tile.tile_type not in (7, 8):
            return False
        self.map_data[(tile_x, tile_y)] = Tile(tile_type=0, is_walkable=True)
        if rebuild_surface:
            self.refresh_world_surface(((tile_x, tile_y),))
        return True

    def refresh_world_surface(self, changed_tiles=None):
        """변경 타일만 다시 그린 뒤 시야 캐시를 비웁니다."""
        if changed_tiles is None or self.world_surface is None:
            self._build_world_surface()
        else:
            for tile_x, tile_y in changed_tiles:
                tile = self.map_data.get((tile_x, tile_y))
                if tile is not None:
                    self._draw_world_tile(tile_x, tile_y, tile)
            self._scaled_world_surface = None
            self._scaled_world_zoom = None
        self._visibility_cache.clear()
        self._vision_wall_rects = None

    def destroy_treasure_at(self, rect):
        """총알이 맞은 보물상자를 제거하고 맵을 다시 합성합니다."""
        start_x = max(0, int(rect.left // self.tile_size))
        end_x = min(self.map_width - 1, int(rect.right // self.tile_size))
        start_y = max(0, int(rect.top // self.tile_size))
        end_y = min(self.map_height - 1, int(rect.bottom // self.tile_size))

        for tile_y in range(start_y, end_y + 1):
            for tile_x in range(start_x, end_x + 1):
                tile = self.map_data.get((tile_x, tile_y))
                if tile and tile.tile_type == 3:
                    self.destroy_treasure(tile_x, tile_y)
                    return tile_x, tile_y
        return None

    def treasure_at(self, rect):
        start_x = max(0, int(rect.left // self.tile_size))
        end_x = min(self.map_width - 1, int(rect.right // self.tile_size))
        start_y = max(0, int(rect.top // self.tile_size))
        end_y = min(self.map_height - 1, int(rect.bottom // self.tile_size))
        for tile_y in range(start_y, end_y + 1):
            for tile_x in range(start_x, end_x + 1):
                tile = self.map_data.get((tile_x, tile_y))
                if tile and tile.tile_type == 3:
                    return tile_x, tile_y
        return None

    def destroy_treasure(self, tile_x, tile_y):
        """지정한 좌표의 보물상자를 제거합니다."""
        tile = self.map_data.get((tile_x, tile_y))
        if not tile or tile.tile_type != 3:
            return False

        self.map_data[(tile_x, tile_y)] = Tile(tile_type=0, is_walkable=True)
        self.refresh_world_surface(((tile_x, tile_y),))
        return True
