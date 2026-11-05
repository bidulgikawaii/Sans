import json
import threading
import tkinter as tk
from http.client import HTTPException
from tkinter import ttk
from urllib.error import URLError
from urllib.request import urlopen

from Config import LEADERBOARD_PORT, SERVER_IP


class LeaderboardWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Sans - 실시간 킬 순위")
        self.root.geometry("760x420")
        self.root.minsize(520, 300)
        self.refreshing = False

        connection = ttk.Frame(self.root, padding=10)
        connection.pack(fill="x")
        ttk.Label(connection, text="서버 주소").grid(row=0, column=0, sticky="w")
        self.host = tk.StringVar(value=SERVER_IP)
        ttk.Entry(connection, textvariable=self.host, width=18).grid(
            row=0, column=1, padx=(6, 12), sticky="ew"
        )
        ttk.Button(connection, text="연결", command=self.refresh).grid(
            row=0, column=2
        )
        connection.columnconfigure(1, weight=1)

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

        self.status = tk.StringVar(value="게임 서버를 실행한 뒤 연결하세요.")
        ttk.Label(self.root, textvariable=self.status, padding=(10, 8)).pack(
            fill="x"
        )
        self.root.bind("<Return>", lambda _event: self.refresh())
        self.root.after(500, self.refresh)

    def refresh(self):
        if self.refreshing:
            return
        host = self.host.get().strip()
        if not host or any(character in host for character in "/?#@"):
            self.status.set("서버 주소를 입력하세요. 예: 192.168.0.10")
            self.root.after(2000, self.refresh)
            return

        self.refreshing = True
        self.status.set("서버 연결 중...")
        threading.Thread(
            target=self._fetch,
            args=(host,),
            daemon=True,
        ).start()

    def _fetch(self, host):
        url = f"http://{host}:{LEADERBOARD_PORT}/api/leaderboard"
        try:
            with urlopen(url, timeout=3) as response:
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
            if isinstance(error, URLError):
                message = (
                    "연결할 수 없습니다. 게임 서버가 실행 중인지, "
                    "주소와 방화벽을 확인하세요."
                )
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
