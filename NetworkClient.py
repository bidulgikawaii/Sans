"""게임 클라이언트의 서버 연결과 오프라인 대체 상태를 관리합니다."""

import pickle
import socket
import uuid
from dataclasses import dataclass, field

from Config import (
    GAME_MODE_NORMAL,
    MAX_PLAYERS,
    NETWORK_BUFFER_SIZE,
    SERVER_IP,
    SERVER_IP_FALLBACK,
    SERVER_PORT,
    SERVER_SEED,
)
from NetworkProtocol import FramedSocket


class OfflineClient:
    """서버 연결 없이도 로컬 연습 모드를 시작할 수 있게 합니다."""

    def __init__(self):
        self.initialized = False
        self.player_id = str(uuid.uuid4())

    def send(self, _data):
        del _data
        return None

    def sendall(self, _data):
        del _data
        return None

    def recv(self, _size):
        if _size <= 0:
            return b""
        if not self.initialized:
            self.initialized = True
            return pickle.dumps({"init_id": self.player_id, "seed": SERVER_SEED})
        return pickle.dumps({})

    def close(self):
        return None


@dataclass
class NetworkState:
    """연결 객체와 서버에서 받은 플레이어·로비 정보를 보관합니다."""

    client: object
    init_data: dict = field(default_factory=dict)
    player_id: str = ""
    lobby_status: dict = field(default_factory=lambda: {
        "count": 0,
        "max_players": MAX_PLAYERS,
        "mode": GAME_MODE_NORMAL,
        "started": False,
        "confirmed": False,
    })
    last_lobby_request_at: int = 0


def connect_to_server():
    """설정된 주소 순서대로 연결하고, 실패하면 오프라인 클라이언트를 반환합니다."""
    last_error = None
    for host in (SERVER_IP, SERVER_IP_FALLBACK):
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.settimeout(2.0)
        try:
            client_socket.connect((host, SERVER_PORT))
            return FramedSocket(client_socket)
        except (OSError, socket.timeout) as exc:
            last_error = exc
            client_socket.close()
    print(f"서버 연결 실패, 로컬 모드로 실행합니다: {last_error}")
    return OfflineClient()


network = NetworkState(connect_to_server())
network.init_data = pickle.loads(network.client.recv(1024))
network.player_id = network.init_data["init_id"]
print(f"내 아이디: {network.player_id} 입니다.")


def default_player_name(player_id=None):
    """닉네임을 입력하지 않았을 때 사용할 안정적인 기본 이름입니다."""
    selected_player_id = network.player_id if player_id is None else player_id
    return f"유저_{selected_player_id}"


def reconnect_to_server():
    """서버가 재시작되어도 새 연결과 플레이어 ID를 다시 확보합니다."""
    try:
        network.client.close()
    except OSError:
        pass

    try:
        network.client = connect_to_server()
        network.init_data = pickle.loads(network.client.recv(NETWORK_BUFFER_SIZE))
        network.player_id = network.init_data["init_id"]
        network.lobby_status = {
            "count": 0,
            "max_players": MAX_PLAYERS,
            "mode": GAME_MODE_NORMAL,
            "started": False,
            "confirmed": False,
        }
        network.last_lobby_request_at = 0
        return True
    except (OSError, EOFError, pickle.PickleError, KeyError):
        return False