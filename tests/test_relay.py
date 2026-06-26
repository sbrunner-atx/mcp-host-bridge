"""Relay tests: pure arg parsing plus one real end-to-end loopback hop."""

from __future__ import annotations

import socket
import threading
import time

from mcp_host_bridge.relay import serve, split_hostport


def test_split_hostport_with_and_without_port():
    assert split_hostport("192.168.1.50", 1100) == ("192.168.1.50", 1100)
    assert split_hostport("192.168.1.50:1234", 1100) == ("192.168.1.50", 1234)
    assert split_hostport("127.0.0.1:7362", 1100) == ("127.0.0.1", 7362)
    assert split_hostport("  10.0.0.5  ", 1100) == ("10.0.0.5", 1100)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _echo_server(port: int, ready: threading.Event) -> None:
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(5)
    ready.set()
    conn, _ = srv.accept()
    data = conn.recv(1024)
    conn.sendall(b"echo:" + data)
    conn.close()
    srv.close()


def test_relay_forwards_bytes_end_to_end():
    """A real listener on loopback proves serve() relays both directions."""
    upstream_port = _free_port()
    listen_port = _free_port()

    ready = threading.Event()
    threading.Thread(target=_echo_server, args=(upstream_port, ready), daemon=True).start()
    assert ready.wait(timeout=3)

    threading.Thread(
        target=serve,
        args=("127.0.0.1", listen_port, "127.0.0.1", upstream_port, 3.0),
        daemon=True,
    ).start()

    # Give the relay a moment to bind.
    deadline = time.time() + 3
    client = None
    while time.time() < deadline:
        try:
            client = socket.create_connection(("127.0.0.1", listen_port), timeout=1)
            break
        except OSError:
            time.sleep(0.05)
    assert client is not None, "relay never started listening"

    client.sendall(b"hello")
    client.settimeout(3)
    reply = client.recv(1024)
    client.close()
    assert reply == b"echo:hello"
