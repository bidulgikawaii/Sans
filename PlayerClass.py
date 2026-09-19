import pygame
from Config import *
from ImageLoad import *

class Player:
    def __init__(self, x, y, size, IML: Imageload,tile_Gene = None):
        self.image = IML.GetPlayer()
        self.X = x
        self.Y = y
        self.size = size
       
        self.Hp = PLAYER_MAX_HP
        self.MaxHp = PLAYER_MAX_HP
        self.rect = self.image.get_rect(topleft=(x, y))

        self.tile_generator = tile_Gene

        self.normal_speed = PLAYER_NORMAL_SPEED
        self.sprint_speed = PLAYER_SPRINT_SPEED
        self.dash_speed = PLAYER_DASH_SPEED
        
        # --- 대쉬 관련 변수 세팅 ---
        self.dash_duration = PLAYER_DASH_DURATION_MS
        self.dash_cooldown = PLAYER_DASH_COOLDOWN_MS
        
        self.last_dash_time = -PLAYER_DASH_COOLDOWN_MS
        self.is_dashing = False    # 현재 대쉬 중인지 상태를 저장
        self.dash_end_time = 0     # 대쉬가 끝나는 시각을 기록할 변수

        # 대쉬 방향을 기억할 변수
        self.dash_dir_x = 0
        self.dash_dir_y = 0

        self._update_hitboxes()

    @staticmethod
    def hitboxes_for_position(x, y, width, height):
        """플레이어의 월드 좌표에서 머리/몸통 히트박스를 계산합니다."""
        head_width = round(width * HEAD_HITBOX_WIDTH_RATIO)
        head_height = round(height * HEAD_HITBOX_HEIGHT_RATIO)
        head = pygame.Rect(x + (width - head_width) // 2, y, head_width, head_height)
        inset = round(width * BODY_HITBOX_INSET_RATIO)
        body = pygame.Rect(
            x + inset,
            y + head_height,
            width - inset * 2,
            height - head_height,
        )
        return head, body

    def _update_hitboxes(self):
        self.head_hitbox, self.body_hitbox = self.hitboxes_for_position(
            self.X, self.Y, self.rect.width, self.rect.height
        )

    def check_bullet_hit(self, bullet_rect, damage):
        """총알이 머리 또는 몸통에 닿으면 HP를 감소시키고 맞은 부위를 반환합니다."""
        if self.head_hitbox.colliderect(bullet_rect):
            hit_part = "head"
        elif self.body_hitbox.colliderect(bullet_rect):
            hit_part = "body"
        else:
            return None

        if hit_part == "head":

            self.Hp = max(0, self.Hp - max(0, int(damage)) * HEADSHOT_DAMAGE_MULTIPLIER)
        elif hit_part == "body":
            self.Hp = max(0,self.Hp - max(0,int(damage)))
        return hit_part

    


    def handle_input(self, dash_requested=False):
        keys = pygame.key.get_pressed()
        current_time = pygame.time.get_ticks()

        # 1. 일반적인 이동 방향 계산 (방향키 입력)
        dx = 0
        dy = 0
        if keys[pygame.K_a]:  dx = -1
        if keys[pygame.K_d]:  dx = 1
        if keys[pygame.K_w]:  dy = -1
        if keys[pygame.K_s]:  dy = 1

        # 2. 달리기/대쉬 키(G) 입력 확인 및 대쉬 시작 조건
        if dash_requested and not self.is_dashing:
            # 쿨타임이 지났고, 멈춰있지 않고 움직이는 중일 때만 대쉬 발동
            if current_time - self.last_dash_time >= self.dash_cooldown and (dx != 0 or dy != 0):
                self.is_dashing = True
                self.last_dash_time = current_time
                self.dash_end_time = current_time + self.dash_duration # 0.2초 뒤 종료 예약
                
                # 대쉬를 시작한 시점의 이동 방향을 고정 (대쉬 중 방향 전환 방지)
                self.dash_dir_x = dx
                self.dash_dir_y = dy
                print("대쉬 시작!")

        # 3. 속도 결정 및 대쉬 종료 체크
        if self.is_dashing:
            if current_time > self.dash_end_time:
                self.is_dashing = False # 0.2초가 지나면 대쉬 강제 종료
                print("대쉬 종료, 일반 속도로 전환")
                speed = self.normal_speed
            else:
                speed = self.dash_speed # 0.2초 안에는 대쉬 속도 유지
                # 대쉬 중에는 처음에 고정된 방향으로만 이동
                dx = self.dash_dir_x
                dy = self.dash_dir_y
        else:
            sprinting = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
            speed = self.sprint_speed if sprinting else self.normal_speed

        if self.tile_generator:
            center_x = self.X + self.rect.width / 2
            center_y = self.Y + self.rect.height / 2
            if self.tile_generator.is_in_water(center_x, center_y):
                speed *= WATER_SPEED_MULTIPLIER

        # 4. [수정 포인트] 계산된 최종 이동량(방향 * 속도)을 Move 함수로 전달!
        final_dx = dx * speed
        final_dy = dy * speed
        
        if final_dx != 0 or final_dy != 0:
            self.Move(final_dx, final_dy)

    def Move(self, dx, dy):
        """이동 시 벽 충돌 감지를 수행합니다."""
        moved = False
        for axis_dx, axis_dy in ((dx, 0), (0, dy)):
            if axis_dx == 0 and axis_dy == 0:
                continue
            candidate_x = self.X + axis_dx
            candidate_y = self.Y + axis_dy
            next_head_hitbox, next_body_hitbox = self.hitboxes_for_position(
                candidate_x, candidate_y, self.rect.width, self.rect.height
            )
            if self.tile_generator and (
                self.tile_generator.check_collision(next_head_hitbox)
                or self.tile_generator.check_collision(next_body_hitbox)
            ):
                continue
            self.X = candidate_x
            self.Y = candidate_y
            self.rect.topleft = (round(self.X), round(self.Y))
            self._update_hitboxes()
            moved = True
        return moved

    def draw(self, surface, camera_x=0, camera_y=0, zoom=1.0, offset_x=0, offset_y=0):
        # 카메라 위치를 차감하여 화면용 상대 좌표 계산
        screen_x = (self.rect.x - camera_x) * zoom + offset_x
        screen_y = (self.rect.y - camera_y) * zoom + offset_y
        
        # 화면 좌표 기준 캐릭터 렌더링
        image = self.image if zoom == 1.0 else pygame.transform.scale(
            self.image, (max(1, round(self.image.get_width() * zoom)), max(1, round(self.image.get_height() * zoom)))
        )
        surface.blit(image, (screen_x, screen_y))
        
