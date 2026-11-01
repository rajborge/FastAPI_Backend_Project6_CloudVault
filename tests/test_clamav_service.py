from hashlib import sha256
from io import BytesIO

import pytest

from app.services import clamav_service as clamav_module
from app.services.clamav_service import ClamAVProtocolError, ClamAVService


class FakeSocket:
    def __init__(self, response):
        self.response = response
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def sendall(self, data):
        self.sent.append(data)

    def recv(self, size):
        response = self.response
        self.response = b""
        return response


@pytest.mark.parametrize(
    ("response", "expected_status"),
    [
        (b"stream: OK\0", "CLEAN"),
        (b"stream: Eicar-Test-Signature FOUND\0", "INFECTED"),
    ],
)
def test_scan_stream_returns_verdict_and_digest(monkeypatch, response, expected_status):
    content = b"file bytes for scanning"
    connection = FakeSocket(response)
    monkeypatch.setattr(
        clamav_module.socket,
        "create_connection",
        lambda address, timeout: connection,
    )

    status, content_sha256 = ClamAVService().scan_stream(BytesIO(content))

    assert status == expected_status
    assert content_sha256 == sha256(content).hexdigest()
    assert connection.sent[0] == b"zINSTREAM\0"
    assert connection.sent[-1] == b"\0\0\0\0"


def test_scan_stream_rejects_unknown_response(monkeypatch):
    connection = FakeSocket(b"stream: ERROR\0")
    monkeypatch.setattr(
        clamav_module.socket,
        "create_connection",
        lambda address, timeout: connection,
    )

    with pytest.raises(ClamAVProtocolError):
        ClamAVService().scan_stream(BytesIO(b"file bytes"))
