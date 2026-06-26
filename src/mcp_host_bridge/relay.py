"""A tiny loopback-to-remote TCP relay.

Why this exists: some MCP clients (notably Claude Desktop) run connectors
**sandboxed so they can only reach 127.0.0.1 (loopback), not LAN addresses**.
A *local* MCP server configured with a LAN IP for its device therefore times out,
even though Terminal on the same machine reaches that IP fine. This relay runs
*outside* the sandbox, listens on loopback, and forwards bytes to the remote
service. You then point the connector at ``127.0.0.1``.

This module is deliberately **standard-library only** and **self-contained**: it
can run as part of the installed package *or* as a single file copied to a stable
location by the installer (so the background service never depends on a venv or
``$PATH``). The ``run`` subcommand is parsed here so ``python3 relay.py run ...``
works on its own.
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading

__all__ = ["serve", "probe", "split_hostport", "run_main"]


def split_hostport(value: str, default_port: int) -> tuple[str, int]:
    """Split ``host`` or ``host:port`` into a ``(host, port)`` tuple.

    IPv6 literals are not special-cased; LAN/loopback IPv4 and hostnames are the
    intended inputs. A bare value uses ``default_port``.
    """
    value = value.strip()
    if ":" in value:
        host, _, port = value.rpartition(":")
        return host, int(port)
    return value, default_port


def _pipe(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(4096)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.close()
            except OSError:
                pass


def _handle(client: socket.socket, target: tuple[str, int], timeout: float) -> None:
    try:
        upstream = socket.create_connection(target, timeout=timeout)
    except OSError as exc:
        print(f"upstream connect to {target[0]}:{target[1]} failed: {exc}", flush=True)
        client.close()
        return
    threading.Thread(target=_pipe, args=(client, upstream), daemon=True).start()
    threading.Thread(target=_pipe, args=(upstream, client), daemon=True).start()


def serve(
    listen_host: str,
    listen_port: int,
    target_host: str,
    target_port: int,
    timeout: float = 6.0,
) -> None:
    """Block forever, relaying ``listen_host:listen_port`` to ``target_host:target_port``."""
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((listen_host, listen_port))
    srv.listen(50)
    print(
        f"mcp-host-bridge: {listen_host}:{listen_port} -> {target_host}:{target_port}",
        flush=True,
    )
    while True:
        client, _ = srv.accept()
        threading.Thread(
            target=_handle, args=(client, (target_host, target_port), timeout), daemon=True
        ).start()


def probe(
    listen_host: str,
    listen_port: int,
    payload: bytes | None = None,
    expect: bytes | None = None,
) -> str:
    """Test the listener, optionally sending a service handshake.

    With no ``payload`` this only confirms the local listener is up (a successful
    TCP connect). When a preset supplies a ``payload``/``expect`` pair, the bytes
    travel the full loopback->LAN path and the reply is checked, giving real
    end-to-end confirmation.
    """
    try:
        s = socket.create_connection((listen_host, listen_port), timeout=5)
    except OSError as exc:
        return f"FAILED: cannot reach the bridge on {listen_host}:{listen_port}: {exc}"
    try:
        if payload is None:
            return f"OK - bridge is listening on {listen_host}:{listen_port}."
        s.sendall(payload)
        s.settimeout(4)
        data = s.recv(400)
        if expect is not None and expect in data:
            return "OK - remote service answered through the bridge."
        if not data:
            return "connected to the bridge, but the remote service sent no reply (is it running?)."
        return f"connected; unexpected reply: {data[:120]!r}"
    except OSError as exc:
        return f"FAILED: {exc}"
    finally:
        try:
            s.close()
        except OSError:
            pass


def run_main(argv: list[str] | None = None) -> int:
    """Standalone entry point for the ``run`` subcommand.

    Lets a copied single file work via ``python3 relay.py run --to ... --listen ...``
    without importing the rest of the package.
    """
    parser = argparse.ArgumentParser(prog="mcp-host-bridge-relay")
    sub = parser.add_subparsers(dest="cmd")
    p_run = sub.add_parser("run", help="Run the relay in the foreground (Ctrl-C to stop).")
    p_run.add_argument("--to", required=True, metavar="HOST[:PORT]")
    p_run.add_argument("--listen", required=True, metavar="HOST:PORT")
    p_run.add_argument("--timeout", type=float, default=6.0)
    args = parser.parse_args(argv)
    if args.cmd != "run":
        parser.error("this file only runs the relay; use the mcp-host-bridge CLI for management")
    th, tp = split_hostport(args.to, 0)
    lh, lp = split_hostport(args.listen, 0)
    try:
        serve(lh, lp, th, tp, args.timeout)
    except KeyboardInterrupt:
        return 0
    except OSError as exc:
        print(f"mcp-host-bridge relay failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run_main())
