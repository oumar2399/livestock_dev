"""Exercise the actual MicroPython HTTP client, not a replacement of _http_post."""

import sys
from types import SimpleNamespace
import pytest

from firmware_helpers import load_firmware
from test_b4_firmware import fw


@pytest.fixture
def http(monkeypatch):
    monkeypatch.setitem(sys.modules, "b4_protocol", fw)
    module = load_firmware("b4_runtime")
    state = SimpleNamespace(tick=0, address_delay=0, connect_delay=0, io_delay=0,
                            send_limit=10000, read_limit=10000, send_result="normal",
                            raw=b"HTTP/1.1 201 Created\r\nContent-Length: 2\r\n\r\n{}",
                            sent=bytearray(), closed=0, timeouts=[], events=[], created=0,
                            read_calls=0, connect_error=False)
    modulus = 1 << 30
    module.time = SimpleNamespace(ticks_ms=lambda: state.tick % modulus,
        ticks_add=lambda a, b: (a + b) % modulus,
        ticks_diff=lambda a, b: (a - b + modulus // 2) % modulus - modulus // 2)

    class Socket:
        def __init__(self):
            state.created += 1
        def settimeout(self, timeout):
            state.timeouts.append(timeout)
        def connect(self, addr):
            assert addr == ("opaque-address", 8000)
            state.tick += state.connect_delay
            if state.connect_error:
                raise OSError("connect failed")
        def send(self, data):
            state.tick += state.io_delay
            if state.send_result != "normal":
                return state.send_result
            count = min(len(data), state.send_limit)
            state.sent.extend(data[:count])
            return count
        def recv(self, count):
            state.read_calls += 1
            state.tick += state.io_delay
            count = min(count, state.read_limit)
            result, state.raw = state.raw[:count], state.raw[count:]
            return result
        def close(self):
            state.closed += 1

    def address(host, port, family, kind):
        assert (host, port, family, kind) == ("127.0.0.1", 8000, 0, 1)
        state.tick += state.address_delay
        return [(0, 1, 0, "", ("opaque-address", 8000))]
    monkeypatch.setitem(sys.modules, "usocket", SimpleNamespace(
        getaddrinfo=address, socket=Socket, SOCK_STREAM=1))
    def post():
        return module._http_post("http://127.0.0.1:8000/telemetry", b"packet",
            {"Content-Type": "application/octet-stream"}, 1,
            observer=lambda name, data: state.events.append((name, data)))
    return module, state, post


@pytest.mark.parametrize("size", [1, 3, 10000])
def test_partial_writes_and_fragmented_response(http, size):
    _, state, post = http
    state.send_limit = state.read_limit = size
    response = post()
    header, body = bytes(state.sent).split(b"\r\n\r\n")
    assert b"Content-Length: 6" in header and body == b"packet"
    assert response.status_code == 201 and response.json() == {}
    response.close()
    response.close()
    assert state.closed == 1
    assert state.events[-1][1]["request_complete"] is True


@pytest.mark.parametrize("result", [None, 0, -1, 99999])
def test_nonprogressing_send_fails_and_closes(http, result):
    _, state, post = http
    state.send_result = result
    with pytest.raises(OSError):
        post()
    assert state.closed == 1 and state.read_calls == 0


@pytest.mark.parametrize("raw", [
    b"HTTP/1.1 201 OK\r\nContent-Length: 4097\r\n\r\n",
    b"HTTP/1.1 201 OK\r\nContent-Length: 2\r\n\r\nx",
    b"HTTP/1.1 201 OK\r\nContent-Length: -1\r\n\r\n",
    b"HTTP/1.1 201 OK\r\nContent-Length: 0\r\nContent-Length: 0\r\n\r\n",
    b"HTTP/1.1 201 OK\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n",
    b"HTTP/1.1 201 OK\r\nContent-Encoding: gzip\r\n\r\n",
    b"HTTP/1.1 100 Continue\r\n\r\n",
    b"HTTP/1.1 201 OK\r\nBad Header: value\r\n\r\n",
    b"HTTP/1.1 201 OK\r\nContent-Length: 0\r\n\r\nx",
    b"HTTP/1.1 204 OK\r\nContent-Length: 1\r\n\r\nx",
    b"garbage\r\n\r\n", b"HTTP/1.1 201 OK\r\nunfinished",
    b"HTTP/1.1 201 OK\r\nX: " + b"x" * 2048,
    b"HTTP/1.1 201 OK\r\n\r\n" + b"x" * 4097,
])
def test_invalid_or_oversized_response_fails_closed(http, raw):
    _, state, post = http
    state.raw = raw
    with pytest.raises(OSError):
        post()
    assert state.closed == 1


@pytest.mark.parametrize("length", [True, False])
def test_body_at_exact_limit(http, length):
    module, state, post = http
    state.raw = b"HTTP/1.1 200 OK\r\n" + (b"Content-Length: 4096\r\n" if length else b"") + b"\r\n" + b"x" * 4096
    assert len(post()._body) == module.HTTP_MAX_BODY_BYTES


def test_header_at_exact_limit_and_next_byte(http):
    _, state, post = http
    prefix = b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nX: "
    state.raw = prefix + b"x" * (2048 - len(prefix) - 4) + b"\r\n\r\n"
    raw = state.raw
    assert post().status_code == 200
    state.raw = raw[:-4] + b"x\r\n\r\n"
    with pytest.raises(OSError):
        post()


def test_401_does_not_wait_for_error_body(http):
    _, state, post = http
    state.raw = b"HTTP/1.1 401 Unauthorized\r\nContent-Length: 999999\r\n\r\n"
    assert post().status_code == 401
    assert state.read_calls == 1


def test_header_reader_works_without_bytearray_find(http, monkeypatch):
    module, state, post = http
    class MicroPythonBytearray(bytearray):
        def find(self, *args):
            raise AttributeError("MicroPython 1.12 bytearray has no find")
    monkeypatch.setattr(module, "bytearray", MicroPythonBytearray, raising=False)
    state.read_limit = 1
    assert post().json() == {}
    assert state.closed == 1


@pytest.mark.parametrize("phase", ["connect", "write", "response"])
def test_deadline_is_shared_across_blocking_calls(http, phase):
    _, state, post = http
    if phase == "connect":
        state.connect_delay = 1000
    elif phase == "write":
        state.send_limit, state.io_delay = 1, 100
    else:
        state.read_limit, state.io_delay = 1, 100
    with pytest.raises(OSError, match="deadline"):
        post()
    assert state.closed == 1 and state.tick <= 1100
    assert state.timeouts == sorted(state.timeouts, reverse=True)


def test_address_phase_is_reported_separately_and_not_socket_timed(http):
    _, state, post = http
    state.address_delay = 1500
    with pytest.raises(OSError, match="Address"):
        post()
    assert state.created == 0
    assert state.events[-1][1]["address_ms"] == 1500
    assert state.events[-1][1]["http_ms"] == 0


def test_wraparound_and_connection_error(http):
    _, state, post = http
    state.tick = (1 << 30) - 10
    state.connect_delay = 20
    assert post().status_code == 201
    state.connect_error = True
    with pytest.raises(OSError):
        post()
    assert state.closed == 2


@pytest.mark.parametrize("url", ["https://host", "http://host:0", "http://host:65536",
    "http://user@host", "http://host/\r\nInjected: x", "http://host/#x", "http://[::1]/"])
def test_invalid_urls(http, url):
    module, _, _ = http
    with pytest.raises(ValueError):
        module._parse_url(url)


def test_real_api_replies_fit_limits(binary_case, binary_client, http):
    from test_binary_telemetry_api import REFERENCE, URL, headers
    module, state, post = http
    for expected in (201, 200):
        response = binary_client.post(URL, content=REFERENCE, headers=headers(binary_case))
        assert response.status_code == expected
        assert len(response.content) <= module.HTTP_MAX_BODY_BYTES
        state.raw = ("HTTP/1.1 %d OK\r\nContent-Length: %d\r\n\r\n" %
                     (expected, len(response.content))).encode() + response.content
        assert post().json() == response.json()
