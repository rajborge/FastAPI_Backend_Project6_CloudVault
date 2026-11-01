import hashlib
import socket
import struct
from typing import BinaryIO

from ..core.config import settings


class ClamAVProtocolError(RuntimeError):
    pass


class ClamAVService:
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        timeout: int | None = None,
    ):
        self.host = host or settings.CLAMAV_HOST
        self.port = port or settings.CLAMAV_PORT
        self.timeout = timeout or settings.CLAMAV_TIMEOUT_SECONDS

    def scan_stream(self, stream: BinaryIO) -> tuple[str, str]:
        digest = hashlib.sha256()
        with socket.create_connection(
            (self.host, self.port),
            timeout=self.timeout,
        ) as connection:
            connection.sendall(b"zINSTREAM\0")
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
                connection.sendall(struct.pack("!I", len(chunk)))
                connection.sendall(chunk)
            connection.sendall(struct.pack("!I", 0))
            response = self._read_response(connection)

        if response.endswith(" OK"):
            return "CLEAN", digest.hexdigest()
        if response.endswith(" FOUND"):
            return "INFECTED", digest.hexdigest()
        raise ClamAVProtocolError(f"Unexpected ClamAV response: {response}")

    @staticmethod
    def _read_response(connection: socket.socket) -> str:
        response = bytearray()
        while not response.endswith(b"\0"):
            chunk = connection.recv(4096)
            if not chunk:
                raise ClamAVProtocolError("ClamAV closed the connection without a result")
            response.extend(chunk)

        return response.rstrip(b"\0").decode("utf-8", errors="replace")
