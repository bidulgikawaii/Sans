import pygame
import os


class MainScreenRenderer:
    """메인 메뉴와 로비 화면의 배치와 그리기를 담당합니다."""

    def __init__(self, surface, titles, font, screen_size):
        self.surface = surface
        self.titles = titles
        self.font = font
        self.screen_width, self.screen_height = screen_size

    def _center_rect(self, image_name, center_y):
        image = self.titles[image_name]
        return image, image.get_rect(center=(self.screen_width // 2, center_y))

    def draw_main(self, weapon_name=None, weapon_image=None):
        title, title_rect = self._center_rect("TitleText", 210)
        profile, profile_rect = self._center_rect("MainProfile", 700)
        self.surface.blit(title, title_rect)
        self.surface.blit(profile, profile_rect)
        if weapon_name:
            weapon_text = self.font.render(f"무기: {weapon_name}  [1~6 선택]", True, (220, 235, 255))
            self.surface.blit(weapon_text, weapon_text.get_rect(center=(270, 820)))
        if weapon_image is not None:
            preview = pygame.transform.smoothscale(weapon_image, (240, 120))
            preview_rect = preview.get_rect(center=(270, 680))
            pygame.draw.rect(self.surface, (20, 28, 46), preview_rect.inflate(34, 24), border_radius=10)
            pygame.draw.rect(self.surface, (255, 220, 120), preview_rect.inflate(34, 24), 2, border_radius=10)
            self.surface.blit(preview, preview_rect)
        credit_font =  pygame.font.Font(os.path.join(os.path.dirname(os.path.abspath(__file__)
        ),"Font","HeirofLightRegular.ttf"
            ), 30)
        credit = credit_font.render("By PGM.", True, (190, 200, 220))
        self.surface.blit(credit, credit.get_rect(center=(self.screen_width // 2, self.screen_height - 24)))
        name_button = pygame.Rect(self.screen_width - 300, 35, 250, 64)
        pygame.draw.rect(self.surface, (20, 30, 48), name_button, border_radius=8)
        pygame.draw.rect(self.surface, (255, 220, 120), name_button, 2, border_radius=8)
        name_text = self.font.render("이름 바꾸기", True, (255, 235, 160))
        self.surface.blit(name_text, name_text.get_rect(center=name_button.center))
        return {"profile": profile_rect, "name": name_button}

    def draw_mode_select(self):
        normal, normal_rect = self._center_rect("GameStart", 330)
        debug, debug_rect = self._center_rect("Practice", 520)
        back, back_rect = self._center_rect("Exit", 710)
        self.surface.blit(normal, normal_rect)
        self.surface.blit(debug, debug_rect)
        self.surface.blit(back, back_rect)
        return {"normal": normal_rect, "debug": debug_rect, "back": back_rect}

    def draw_name_input(self, nickname):
        title = self.font.render("닉네임을 입력하세요", True, (255, 235, 150))
        value = self.font.render(nickname or "플레이어", True, (240, 245, 255) if nickname else (140, 155, 180))
        guide = self.font.render("Enter: 확인   Esc: 뒤로", True, (190, 205, 225))
        self.surface.blit(title, title.get_rect(center=(self.screen_width // 2, 330)))
        box = pygame.Rect(0, 0, 520, 70)
        box.center = (self.screen_width // 2, 450)
        pygame.draw.rect(self.surface, (20, 30, 48), box, border_radius=8)
        pygame.draw.rect(self.surface, (255, 220, 120), box, 2, border_radius=8)
        self.surface.blit(value, value.get_rect(center=box.center))
        self.surface.blit(guide, guide.get_rect(center=(self.screen_width // 2, 540)))

    def draw_loading(self, lobby_status, selected_game_mode, max_players, debug_mode):
        profile, profile_rect = self._center_rect("GameStart", 150)
        self.surface.blit(profile, profile_rect)
        title = self.font.render("게임 로딩", True, (255, 255, 255))
        self.surface.blit(title, title.get_rect(center=(self.screen_width // 2, 280)))
        count_text = self.font.render(
            f"플레이어 {lobby_status.get('count', 0)} / {lobby_status.get('max_players', max_players)}",
            True,
            (255, 255, 255),
        )
        self.surface.blit(count_text, count_text.get_rect(center=(self.screen_width // 2, 390)))
        ready_count = lobby_status.get("ready_count", 0)
        ready_text = self.font.render(
            f"확인 인원: {ready_count} / {max(1, lobby_status.get('count', 0))}",
            True,
            (180, 235, 255),
        )
        self.surface.blit(ready_text, ready_text.get_rect(center=(self.screen_width // 2, 440)))
        mode_name = "디버그 모드" if selected_game_mode == "debug" else "일반 모드"
        countdown_ms = lobby_status.get("countdown_ms", 0)
        if lobby_status.get("accepted") is False:
            status_name = lobby_status.get("message", "게임이 진행 중이라 참가할 수 없습니다.")
        elif countdown_ms > 0:
            status_name = f"게임 시작까지 {max(1, (countdown_ms + 999) // 1000)}"
        elif lobby_status.get("all_ready"):
            status_name = "모든 인원이 확인했습니다. 3초 후 시작"
        else:
            status_name = "스페이스를 눌러 인원 확인" if not lobby_status.get("started") else "게임 시작 중..."
        mode_text = self.font.render(mode_name, True, (255, 220, 120))
        status_text = self.font.render(status_name, True, (220, 220, 220))
        self.surface.blit(mode_text, mode_text.get_rect(center=(self.screen_width // 2, 500)))
        self.surface.blit(status_text, status_text.get_rect(center=(self.screen_width // 2, 570)) )