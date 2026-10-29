import pygame
import os
from Config import MAIN_SCREEN_BACKGROUND_COLOR
from GameModes import get_game_mode, get_game_modes
from Settings import KEY_ACTION_LABELS


class MainScreenRenderer:
    """메인 메뉴와 로비 화면의 배치와 그리기를 담당합니다."""

    # 화면 표현과 입력 처리를 분리해, 버튼 영역을 호출부가 상태 전환에 사용합니다.
    def __init__(self, surface, titles, font, screen_size):
        self.surface = surface
        self.titles = titles
        self.font = font
        self.screen_width, self.screen_height = screen_size
        self.background = titles.get("BackG")
        self._background_scaled = (
            pygame.transform.smoothscale(self.background, screen_size)
            if self.background is not None else None
        )
        self._weapon_previews = {}
        font_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "Font", "HeirofLightRegular.ttf"
        )
        self._credit_text = pygame.font.Font(font_path, 30).render(
            "By PGM.", True, (190, 200, 220)
        )

    def _draw_background(self, image=False):
        self.surface.fill(MAIN_SCREEN_BACKGROUND_COLOR)
        if image and self._background_scaled is not None:
            self.surface.blit(self._background_scaled, (0, 0))

    def _center_rect(self, image_name, center_y):
        image = self.titles[image_name]
        return image, image.get_rect(center=(self.screen_width // 2, center_y))

    def draw_main(self, weapon_name=None, weapon_image=None):
        self._draw_background(image=True)
        title, title_rect = self._center_rect("TitleText", 210)
        profile, profile_rect = self._center_rect("MainProfile", 700)
        self.surface.blit(title, title_rect)
        self.surface.blit(profile, profile_rect)
        if weapon_name:
            weapon_text = self.font.render(f"무기: {weapon_name}  [1~5 선택]", True, (220, 235, 255))
            self.surface.blit(weapon_text, weapon_text.get_rect(center=(270, 820)))
        if weapon_image is not None:
            cache_key = id(weapon_image)
            preview = self._weapon_previews.get(cache_key)
            if preview is None:
                preview = pygame.transform.smoothscale(weapon_image, (240, 120))
                self._weapon_previews[cache_key] = preview
            preview_rect = preview.get_rect(center=(270, 680))
            pygame.draw.rect(self.surface, (20, 28, 46), preview_rect.inflate(34, 24), border_radius=10)
            pygame.draw.rect(self.surface, (255, 220, 120), preview_rect.inflate(34, 24), 2, border_radius=10)
            self.surface.blit(preview, preview_rect)
        self.surface.blit(
            self._credit_text,
            self._credit_text.get_rect(center=(self.screen_width // 2, self.screen_height - 24)),
        )
        settings_image = self.titles.get("Setting")
        if settings_image is not None:
            settings_rect = settings_image.get_rect(
                center=(self.screen_width - 220, self.screen_height - 100)
            )
            self.surface.blit(settings_image, settings_rect)
        else:
            settings_rect = pygame.Rect(self.screen_width - 340, self.screen_height - 140, 240, 64)
            pygame.draw.rect(self.surface, (20, 30, 48), settings_rect, border_radius=8)
            pygame.draw.rect(self.surface, (255, 220, 120), settings_rect, 2, border_radius=8)
            settings_text = self.font.render("설정", True, (255, 235, 160))
            self.surface.blit(settings_text, settings_text.get_rect(center=settings_rect.center))
        name_button = pygame.Rect(self.screen_width - 300, 35, 250, 64)
        pygame.draw.rect(self.surface, (20, 30, 48), name_button, border_radius=8)
        pygame.draw.rect(self.surface, (255, 220, 120), name_button, 2, border_radius=8)
        name_text = self.font.render("이름 바꾸기", True, (255, 235, 160))
        self.surface.blit(name_text, name_text.get_rect(center=name_button.center))
        return {"profile": profile_rect, "name": name_button, "settings": settings_rect}

    def draw_settings(self, settings, key_bindings, waiting_action=None, overlay=False):
        if overlay:
            veil = pygame.Surface(self.surface.get_size(), pygame.SRCALPHA)
            veil.fill((8, 12, 20, 230))
            self.surface.blit(veil, (0, 0))
        else:
            self._draw_background()
        title = self.font.render("설정", True, (255, 235, 150))
        self.surface.blit(title, title.get_rect(center=(self.screen_width // 2, 105)))
        buttons = {"keys": {}}
        actions = list(key_bindings)
        column_width = min(620, (self.screen_width - 120) // 2)
        column_gap = 36
        total_width = column_width * 2 + column_gap
        first_x = (self.screen_width - total_width) // 2
        row_height = 66
        first_y = 190
        for index, action in enumerate(actions):
            column, row = divmod(index, 7)
            rect = pygame.Rect(
                first_x + column * (column_width + column_gap),
                first_y + row * row_height,
                column_width,
                54,
            )
            pygame.draw.rect(self.surface, (20, 30, 48), rect, border_radius=6)
            active = action == waiting_action
            border = (255, 220, 120) if active else (90, 120, 150)
            pygame.draw.rect(self.surface, border, rect, 2, border_radius=6)
            label = self.font.render(
                KEY_ACTION_LABELS[action], True, (235, 240, 250)
            )
            key_text = self.font.render(
                "키 입력 대기" if active else pygame.key.name(key_bindings[action]).upper(),
                True,
                (255, 220, 120),
            )
            self.surface.blit(label, (rect.x + 18, rect.y + 11))
            self.surface.blit(key_text, key_text.get_rect(midright=(rect.right - 18, rect.centery)))
            buttons["keys"][action] = rect

        option_y = first_y + 7 * row_height + 12
        sensitivity_rect = pygame.Rect(first_x, option_y, total_width, 62)
        pygame.draw.rect(self.surface, (20, 30, 48), sensitivity_rect, border_radius=6)
        pygame.draw.rect(self.surface, (90, 120, 150), sensitivity_rect, 2, border_radius=6)
        sensitivity_label = self.font.render(
            f"마우스 감도  {settings['mouse_sensitivity']:.2f}", True, (235, 240, 250)
        )
        self.surface.blit(sensitivity_label, (sensitivity_rect.x + 18, sensitivity_rect.y + 13))
        slider = pygame.Rect(sensitivity_rect.right - 420, sensitivity_rect.y + 27, 380, 8)
        pygame.draw.rect(self.surface, (70, 85, 105), slider, border_radius=4)
        progress = (settings["mouse_sensitivity"] - 0.25) / 1.75
        knob_x = slider.x + round(slider.width * progress)
        pygame.draw.line(self.surface, (255, 220, 120), slider.topleft, (knob_x, slider.centery), 8)
        pygame.draw.circle(self.surface, (255, 235, 170), (knob_x, slider.centery), 12)
        buttons["sensitivity"] = slider.inflate(24, 34)

        volume_rect = pygame.Rect(first_x, option_y + 82, total_width, 62)
        pygame.draw.rect(self.surface, (20, 30, 48), volume_rect, border_radius=6)
        pygame.draw.rect(self.surface, (90, 120, 150), volume_rect, 2, border_radius=6)
        volume_label = self.font.render(
            f"효과음 음량  {round(settings['sound_volume'] * 100)}%", True, (235, 240, 250)
        )
        self.surface.blit(volume_label, (volume_rect.x + 18, volume_rect.y + 13))
        volume_slider = pygame.Rect(volume_rect.right - 420, volume_rect.y + 27, 380, 8)
        pygame.draw.rect(self.surface, (70, 85, 105), volume_slider, border_radius=4)
        volume_knob_x = volume_slider.x + round(volume_slider.width * settings["sound_volume"])
        pygame.draw.line(
            self.surface, (255, 220, 120), volume_slider.topleft,
            (volume_knob_x, volume_slider.centery), 8,
        )
        pygame.draw.circle(self.surface, (255, 235, 170), (volume_knob_x, volume_slider.centery), 12)
        buttons["volume"] = volume_slider.inflate(24, 34)

        toggle_rect = pygame.Rect(first_x, option_y + 164, total_width, 62)
        pygame.draw.rect(self.surface, (20, 30, 48), toggle_rect, border_radius=6)
        pygame.draw.rect(self.surface, (90, 120, 150), toggle_rect, 2, border_radius=6)
        toggle_label = self.font.render("보유한 스킬 아이콘만 표시", True, (235, 240, 250))
        self.surface.blit(toggle_label, (toggle_rect.x + 18, toggle_rect.y + 13))
        toggle_value = "켜짐" if settings["owned_skills_only"] else "꺼짐"
        toggle_text = self.font.render(toggle_value, True, (255, 220, 120))
        toggle_button = pygame.Rect(toggle_rect.right - 150, toggle_rect.y + 9, 118, 44)
        pygame.draw.rect(self.surface, (50, 65, 82), toggle_button, border_radius=5)
        self.surface.blit(toggle_text, toggle_text.get_rect(center=toggle_button.center))
        buttons["owned_only"] = toggle_rect

        if waiting_action:
            guide_text = "변경할 키를 누르세요 · Esc 취소"
        else:
            guide_text = "키 항목을 눌러 변경 · 감도와 효과음 음량 조절"
        guide = self.font.render(guide_text, True, (180, 195, 215))
        self.surface.blit(guide, guide.get_rect(center=(self.screen_width // 2, toggle_rect.bottom + 34)))
        back_rect = pygame.Rect(0, 0, 220, 60)
        back_rect.center = (self.screen_width // 2, self.screen_height - 70)
        pygame.draw.rect(self.surface, (20, 30, 48), back_rect, border_radius=6)
        pygame.draw.rect(self.surface, (255, 220, 120), back_rect, 2, border_radius=6)
        back_text = self.font.render(
            "게임으로 돌아가기" if overlay else "돌아가기", True, (255, 235, 160)
        )
        self.surface.blit(back_text, back_text.get_rect(center=back_rect.center))
        buttons["back"] = back_rect
        return buttons

    def draw_mode_select(self):
        self._draw_background()
        modes = get_game_modes()
        button_height = 88
        button_gap = 22
        total_height = len(modes) * button_height + max(0, len(modes) - 1) * button_gap
        first_y = (self.screen_height - total_height) // 2
        buttons = {}
        for index, mode in enumerate(modes):
            button_rect = pygame.Rect(0, 0, min(620, self.screen_width - 80), button_height)
            button_rect.center = (
                self.screen_width // 2,
                first_y + index * (button_height + button_gap) + button_height // 2,
            )
            pygame.draw.rect(self.surface, (22, 34, 52), button_rect, border_radius=8)
            pygame.draw.rect(self.surface, (255, 220, 120), button_rect, 2, border_radius=8)
            mode_text = self.font.render(mode.label, True, (255, 235, 170))
            self.surface.blit(mode_text, mode_text.get_rect(center=button_rect.center))
            buttons[mode.mode_id] = button_rect

        back_image, back_rect = self._center_rect("Exit", self.screen_height - 72)
        self.surface.blit(back_image, back_rect)
        buttons["back"] = back_rect
        return buttons

    def draw_name_input(self, nickname, default_name="플레이어"):
        self._draw_background()
        title = self.font.render("닉네임을 입력하세요", True, (255, 235, 150))
        value = self.font.render(nickname or default_name, True, (240, 245, 255) if nickname else (140, 155, 180))
        guide = self.font.render("Enter: 확인   R: 랜덤 이름   Esc: 뒤로", True, (190, 205, 225))
        self.surface.blit(title, title.get_rect(center=(self.screen_width // 2, 330)))
        box = pygame.Rect(0, 0, 520, 70)
        box.center = (self.screen_width // 2, 450)
        pygame.draw.rect(self.surface, (20, 30, 48), box, border_radius=8)
        pygame.draw.rect(self.surface, (255, 220, 120), box, 2, border_radius=8)
        self.surface.blit(value, value.get_rect(center=box.center))
        self.surface.blit(guide, guide.get_rect(center=(self.screen_width // 2, 540)))

    def draw_loading(self, lobby_status, selected_game_mode, max_players):
        self._draw_background()
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
        confirm_text = self.font.render(
            "확인됨 · Space를 눌러 취소" if lobby_status.get("confirmed", False) else "Space를 눌러 확인",
            True,
            (120, 255, 160) if lobby_status.get("confirmed", False) else (220, 220, 220),
        )
        self.surface.blit(confirm_text, confirm_text.get_rect(center=(self.screen_width // 2, 480)))
        mode_name = get_game_mode(selected_game_mode).label
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
        self.surface.blit(mode_text, mode_text.get_rect(center=(self.screen_width // 2, 530)))
        self.surface.blit(status_text, status_text.get_rect(center=(self.screen_width // 2, 570)) )
