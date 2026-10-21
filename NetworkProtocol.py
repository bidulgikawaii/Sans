"""TCP 스트림에서 길이 헤더로 메시지 경계를 보존합니다."""

import socket
import struct


_HEADER = struct.Struct("!I")
_MAX_PACKET_SIZE = 16 * 1024 * 1024


class FramedSocket:
    """기존 send/recv 호출을 길이 프리픽스가 있는 메시지로 감쌉니다."""

    def __init__(self, connection):
        self.connection = connection

    def sendall(self, data):
        payload = bytes(data)
        if len(payload) > _MAX_PACKET_SIZE:
            raise ValueError("packet exceeds the maximum size")
        self.connection.sendall(_HEADER.pack(len(payload)) + payload)

    def send(self, data):
        self.sendall(data)
        return len(data)

    def recv(self, _size):
        header = self._receive_exactly(_HEADER.size, allow_clean_eof=True)
        if not header:
            return b""
        (payload_size,) = _HEADER.unpack(header)
        if payload_size > _MAX_PACKET_SIZE:
            raise ValueError("packet exceeds the maximum size")
        return self._receive_exactly(payload_size)

    def _receive_exactly(self, size, allow_clean_eof=False):
        chunks = bytearray()
        while len(chunks) < size:
            chunk = self.connection.recv(size - len(chunks))
            if not chunk:
                if allow_clean_eof and not chunks:
                    return b""
                raise ConnectionError("connection closed before packet was complete")
            chunks.extend(chunk)
        return bytes(chunks)

    def close(self):
        self.connection.close()