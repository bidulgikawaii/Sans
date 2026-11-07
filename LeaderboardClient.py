import json
import queue
import threading
from http.client import HTTPException
from urllib.error import URLError
from urllib.request import urlopen

import pygame

from Config import LEADERBOARD_PORT, SERVER_IP
from FontAssets import get_game_font


WINDOW_SIZE = (960, 680)
BACKGROUND = (18, 24, 34)
PANEL = (30, 40, 54)
ACCENT = (100, 210, 170)
TEXT = (235, 240, 245)
MUTED = (155, 170, 185)


def parse_leaderboard_snapshot(raw):
    """Validate the API response and flatten its per-mode standings."""
    snapshot = json.loads(raw.decode("utf-8"))
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("modes"), list):
        raise ValueError("서버 순위 데이터 형식이 올바르지 않습니다.")

    rows = []
    for mode in snapshot["modes"]:
        if not isinstance(mode, dict):
            continue
        label = str(mode.get("label", mode.get("id", "모드")))
        players = mode.get("players", [])
        if not isinstance(players, list):
            continue
        for player in players:
            if not isinstance(player, dict):
                continue
            rows.append((
                label,
                str(player.get("rank", "")),
                str(player.get("name", "플레이어")),
                str(player.get("kills", 0)),
            ))
    return rows


def fetch_leaderboard(host):
    url = f"http://{host}:{LEADERBOARD_PORT}/api/leaderboard"
    with urlopen(url, timeout=3) as response:
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError("서버 응답이 너무 큽니다.")
    return parse_leaderboard_snapshot(raw)


class LeaderboardApp:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Sans - 실시간 킬 순위")
        self.screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.title_font = get_game_font(36)
        self.body_font = get_game_font(24)
        self.small_font = get_game_font(18)
        self.host = SERVER_IP
        self.host_active = False
        self.rows = []
        self.status = "게임 서버를 실행한 뒤 연결하세요."
        self.refreshing = False
        self.next_refresh_at = 0
        self.results = queue.Queue()
        self.scroll_offset = 0
        self.running = True

    def refresh(self):
        if self.refreshing:
            return
        host = self.host.strip()
        if not host or any(character in host for character in "/?#@:"):
            self.status = "서버 주소를 확인하세요. 예: 192.168.0.10"
            self.next_refresh_at = pygame.time.get_ticks() + 2000
            return
        self.refreshing = True
        self.status = "서버 연결 중..."

        def request():
            try:
                self.results.put((fetch_leaderboard(host), None))
            except (
                HTTPException,
                URLError,
                TimeoutError,
                ValueError,
                UnicodeDecodeError,
                OSError,
            ) as error:
                self.results.put((None, error))

        threading.Thread(target=request, daemon=True).start()

    def _handle_result(self):
        try:
            rows, error = self.results.get_nowait()
        except queue.Empty:
            return
        self.refreshing = False
        self.next_refresh_at = pygame.time.get_ticks() + 2000
        if error is not None:
            if isinstance(error, URLError):
                self.status = (
                    "연결할 수 없습니다. 게임 서버, 주소와 방화벽을 확인하세요."
                )
            else:
                self.status = f"연결 실패: {error}"
            return
        self.rows = rows
        self.scroll_offset = min(
            self.scroll_offset,
            max(0, len(self.rows) - self._visible_row_count()),
        )
        self.status = (
            "경기 중인 플레이어가 없습니다."
            if not rows
            else f"실시간 업데이트 · {len(rows)}명"
        )

    def _visible_row_count(self):
        return max(1, (self.screen.get_height() - 230) // 44)

    def _draw_text(self, text, font, color, position, anchor="topleft"):
        rendered = font.render(str(text), True, color)
        rect = rendered.get_rect(**{anchor: position})
        self.screen.blit(rendered, rect)
        return rect

    def _draw(self):
        width, height = self.screen.get_size()
        self.screen.fill(BACKGROUND)
        self._draw_text("실시간 킬 순위", self.title_font, TEXT, (32, 24))
        self._draw_text(
            "게임 서버의 경기별 순위를 표시합니다.",
            self.small_font,
            MUTED,
            (34, 72),
        )

        address_rect = pygame.Rect(32, 112, min(520, width - 210), 48)
        pygame.draw.rect(self.screen, PANEL, address_rect, border_radius=6)
        pygame.draw.rect(
            self.screen,
            ACCENT if self.host_active else (75, 90, 108),
            address_rect,
            2,
            border_radius=6,
        )
        self._draw_text(
            self.host or "서버 주소",
            self.body_font,
            TEXT if self.host else MUTED,
            (address_rect.x + 12, address_rect.centery),
            "midleft",
        )
        self.address_rect = address_rect

        self.refresh_rect = pygame.Rect(width - 152, 112, 120, 48)
        pygame.draw.rect(self.screen, ACCENT, self.refresh_rect, border_radius=6)
        self._draw_text(
            "새로고침",
            self.body_font,
            (18, 32, 35),
            self.refresh_rect.center,
            "center",
        )

        table_rect = pygame.Rect(32, 184, width - 64, height - 220)
        pygame.draw.rect(self.screen, PANEL, table_rect, border_radius=8)
        pygame.draw.rect(self.screen, (60, 75, 92), table_rect, 1, border_radius=8)
        headers = (
            ("모드", table_rect.x + 18, "midleft"),
            ("순위", table_rect.x + table_rect.width * 0.45, "center"),
            ("플레이어", table_rect.x + table_rect.width * 0.62, "midleft"),
            ("킬", table_rect.right - 20, "midright"),
        )
        for label, x, anchor in headers:
            self._draw_text(label, self.small_font, ACCENT, (x, table_rect.y + 26), anchor)

        first_row_y = table_rect.y + 64
        row_height = 44
        visible_rows = max(0, (table_rect.bottom - first_row_y - 10) // row_height)
        for index, row in enumerate(
            self.rows[self.scroll_offset:self.scroll_offset + visible_rows]
        ):
            mode, rank, name, kills = row
            row_y = first_row_y + index * row_height
            if index % 2 == 0:
                pygame.draw.rect(
                    self.screen,
                    (35, 47, 62),
                    (table_rect.x + 8, row_y - 4, table_rect.width - 16, row_height),
                    border_radius=4,
                )
            self._draw_text(mode, self.small_font, TEXT, (table_rect.x + 18, row_y + 16), "midleft")
            self._draw_text(rank, self.small_font, TEXT, (table_rect.x + table_rect.width * 0.45, row_y + 16), "center")
            self._draw_text(name, self.body_font, TEXT, (table_rect.x + table_rect.width * 0.62, row_y + 16), "midleft")
            self._draw_text(kills, self.body_font, ACCENT, (table_rect.right - 20, row_y + 16), "midright")

        self._draw_text(self.status, self.small_font, MUTED, (34, height - 24), "midleft")
        pygame.display.flip()

    def _handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.VIDEORESIZE:
            self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                self.host_active = self.address_rect.collidepoint(event.pos)
                if self.host_active:
                    pygame.key.start_text_input()
                else:
                    pygame.key.stop_text_input()
                if self.refresh_rect.collidepoint(event.pos):
                    self.refresh()
            elif event.button == 4:
                self.scroll_offset = max(0, self.scroll_offset - 1)
            elif event.button == 5:
                self.scroll_offset = min(
                    max(0, len(self.rows) - self._visible_row_count()),
                    self.scroll_offset + 1,
                )
        elif event.type == pygame.TEXTINPUT and self.host_active:
            self.host += event.text
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.host_active = False
                pygame.key.stop_text_input()
            elif self.host_active and event.key == pygame.K_BACKSPACE:
                self.host = self.host[:-1]
            elif event.key == pygame.K_RETURN:
                self.refresh()

    def run(self):
        self.refresh()
        while self.running:
            for event in pygame.event.get():
                self._handle_event(event)
            self._handle_result()
            if (
                not self.refreshing
                and pygame.time.get_ticks() >= self.next_refresh_at
            ):
                self.refresh()
            self._draw()
            self.clock.tick(30)
        pygame.key.stop_text_input()
        pygame.quit()


if __name__ == "__main__":
    LeaderboardApp().run()
