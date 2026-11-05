import json
import os
import threading
import tkinter as tk
from http.client import HTTPException
from tkinter import ttk
from urllib.error import URLError
from urllib.request import Request, urlopen

from Config import LEADERBOARD_PORT, SERVER_IP


class LeaderboardWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Sans - 실시간 킬 순위")
        self.root.geometry("820x420")
        self.root.minsize(520, 300)
        self.refreshing = False

        connection = ttk.Frame(self.root, padding=10)
        connection.pack(fill="x")
        ttk.Label(connection, text="서버").grid(row=0, column=0, sticky="w")
        self.host = tk.StringVar(
            value=os.environ.get("SANS_LEADERBOARD_HOST", SERVER_IP)
        )
        ttk.Entry(connection, textvariable=self.host, width=18).grid(
            row=0, column=1, padx=(6, 12)
        )
        ttk.Label(connection, text="포트").grid(row=0, column=2, sticky="w")
        self.port = tk.StringVar(value=str(LEADERBOARD_PORT))
        ttk.Entry(connection, textvariable=self.port, width=8).grid(
            row=0, column=3, padx=(6, 12)
        )
        ttk.Label(connection, text="토큰").grid(row=0, column=4, sticky="w")
        self.token = tk.StringVar(
            value=os.environ.get("SANS_LEADERBOARD_TOKEN", "")
        )
        self.token_visible = tk.BooleanVar(value=False)
        self.token_entry = ttk.Entry(
            connection,
            textvariable=self.token,
            show="*",
            width=28,
        )
        self.token_entry.grid(
            row=0, column=5, padx=(6, 8)
        )
        ttk.Checkbutton(
            connection,
            text="표시",
            variable=self.token_visible,
            command=self._toggle_token_visibility,
        ).grid(row=0, column=6, padx=(0, 8))
        ttk.Button(connection, text="연결 / 새로고침", command=self.refresh).grid(
            row=0, column=7
        )
        connection.columnconfigure(5, weight=1)

        self.table = ttk.Treeview(
            self.root,
            columns=("mode", "rank", "name", "kills"),
            show="headings",
        )
        for column, title, width in (
            ("mode", "모드", 150),
            ("rank", "순위", 70),
            ("name", "플레이어", 300),
            ("kills", "킬", 80),
        ):
            self.table.heading(column, text=title)
            self.table.column(column, width=width, anchor="center")
        self.table.pack(fill="both", expand=True, padx=10)

        self.status = tk.StringVar(value="서버 토큰을 입력하고 연결하세요.")
        ttk.Label(self.root, textvariable=self.status, padding=(10, 8)).pack(
            fill="x"
        )
        self.root.bind("<Return>", lambda _event: self.refresh())
        self.root.after(500, self.refresh)

    def _toggle_token_visibility(self):
        self.token_entry.configure(
            show="" if self.token_visible.get() else "*"
        )

    def refresh(self):
        if self.refreshing:
            return
        host = self.host.get().strip()
        token = self.token.get().strip()
        if not host or any(character in host for character in "/?#@"):
            self.status.set("서버 주소를 확인하세요.")
            self.root.after(2000, self.refresh)
            return
        if len(token) < 32:
            self.status.set("32자 이상의 서버 토큰을 입력하세요.")
            self.root.after(2000, self.refresh)
            return
        try:
            port = int(self.port.get())
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            self.status.set("포트는 1~65535 사이의 숫자여야 합니다.")
            self.root.after(2000, self.refresh)
            return

        self.refreshing = True
        self.status.set("서버 연결 중...")
        threading.Thread(
            target=self._fetch,
            args=(host, port, token),
            daemon=True,
        ).start()

    def _fetch(self, host, port, token):
        url = f"http://{host}:{port}/api/leaderboard"
        request = Request(url, headers={"Authorization": f"Bearer {token}"})
        try:
            with urlopen(request, timeout=3) as response:
                raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise ValueError("서버 응답이 너무 큽니다.")
            snapshot = json.loads(raw.decode("utf-8"))
            if not isinstance(snapshot, dict):
                raise ValueError("서버 순위 데이터 형식이 올바르지 않습니다.")
            modes = snapshot.get("modes")
            if not isinstance(modes, list):
                raise ValueError("서버 순위 데이터 형식이 올바르지 않습니다.")
            self.root.after(0, lambda: self._show_snapshot(modes))
        except (
            HTTPException,
            URLError,
            TimeoutError,
            ValueError,
            UnicodeDecodeError,
        ) as error:
            message = str(error)
            self.root.after(0, lambda: self._show_error(message))

    def _show_snapshot(self, modes):
        for item in self.table.get_children():
            self.table.delete(item)
        row_count = 0
        for mode in modes:
            if not isinstance(mode, dict):
                continue
            label = str(mode.get("label", mode.get("id", "모드")))
            players = mode.get("players", [])
            if not isinstance(players, list):
                continue
            for player in players:
                if not isinstance(player, dict):
                    continue
                self.table.insert(
                    "",
                    "end",
                    values=(
                        label,
                        player.get("rank", ""),
                        player.get("name", "플레이어"),
                        player.get("kills", 0),
                    ),
                )
                row_count += 1
        self.status.set(
            "경기 중인 플레이어가 없습니다."
            if row_count == 0
            else f"실시간 업데이트 · {row_count}명"
        )
        self._finish_refresh()

    def _show_error(self, message):
        self.status.set(f"연결 실패: {message}")
        self._finish_refresh()

    def _finish_refresh(self):
        self.refreshing = False
        self.root.after(2000, self.refresh)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    LeaderboardWindow().run()
