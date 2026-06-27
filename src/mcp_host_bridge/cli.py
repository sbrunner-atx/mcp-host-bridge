"""Command-line interface for mcp-host-bridge.

One command everywhere; the OS and the service's protocol are auto-detected.

TCP services (the connector is the client):

    mcp-host-bridge install   n3fjp  --to 192.168.1.50   # 127.0.0.1:1100 -> :1100
    mcp-host-bridge install   fldigi --to 192.168.1.50
    mcp-host-bridge install   myapp  --port 5000 --to 192.168.1.9

UDP services (inverted: the remote broadcasts in, replies route back):

    mcp-host-bridge install   wsjtx  --to 192.168.1.111  # 0.0.0.0:2237 -> deliver 127.0.0.1:2238

    mcp-host-bridge status    n3fjp
    mcp-host-bridge uninstall wsjtx
    mcp-host-bridge list-services
"""

from __future__ import annotations

import argparse
import sys

from . import install as installer
from . import services
from .relay import serve, serve_udp, split_hostport


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp-host-bridge",
        description=(
            "Bridge a loopback-only MCP connector to a service on another host. "
            "Point the connector at 127.0.0.1; this relay does the LAN hop (TCP or UDP)."
        ),
    )
    sub = parser.add_subparsers(dest="cmd")

    def add_target_opts(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "service", nargs="?", help="Service preset name (e.g. n3fjp, fldigi, wsjtx)."
        )
        p.add_argument(
            "--to", metavar="HOST[:PORT]",
            help="TCP: remote host (required). UDP: optional pinned remote peer.",
        )
        p.add_argument("--port", type=int, help="Service port (define/override).")
        p.add_argument("--name", help="Instance label (defaults to the service name).")
        p.add_argument(
            "--listen", metavar="HOST:PORT",
            help="Local bind. Default 127.0.0.1:<port> (TCP) or 0.0.0.0:<port> (UDP).",
        )
        p.add_argument(
            "--deliver", metavar="HOST:PORT",
            help="UDP only: loopback address the MCP server listens on "
            "(default 127.0.0.1:<port+1>).",
        )

    p_run = sub.add_parser("run", help="Run the relay in the foreground (Ctrl-C to stop).")
    add_target_opts(p_run)
    p_run.add_argument("--timeout", type=float, default=6.0)

    add_target_opts(
        sub.add_parser("install", help="Install + start a service that survives reboot.")
    )
    add_target_opts(sub.add_parser("uninstall", help="Stop and remove the background service."))
    add_target_opts(
        sub.add_parser("status", help="Show the service state and test the connection.")
    )
    sub.add_parser("list-services", help="List built-in and user-defined service presets.")
    return parser


def _resolve(args: argparse.Namespace):
    """Return (name, listen_host, listen_port, deliver_host, deliver_port, service)."""
    svc = services.resolve(getattr(args, "service", None), getattr(args, "port", None))
    name = getattr(args, "name", None) or svc.name
    if svc.protocol == "udp":
        if getattr(args, "listen", None):
            lh, lp = split_hostport(args.listen, svc.port)
        else:
            lh, lp = "0.0.0.0", svc.port
        if getattr(args, "deliver", None):
            dh, dp = split_hostport(args.deliver, svc.port + 1)
        else:
            dh, dp = "127.0.0.1", svc.port + 1
        return name, lh, lp, dh, dp, svc
    if getattr(args, "listen", None):
        lh, lp = split_hostport(args.listen, svc.port)
    else:
        lh, lp = "127.0.0.1", svc.port
    return name, lh, lp, None, None, svc


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    cmd = args.cmd
    if cmd is None:
        parser.print_help()
        return 0

    if cmd == "list-services":
        print(services.format_list())
        return 0

    try:
        name, lh, lp, dh, dp, svc = _resolve(args)
    except ValueError as exc:
        parser.error(str(exc))

    if cmd == "run":
        if svc.protocol == "udp":
            rh = rp = None
            if args.to:
                rh, rp = split_hostport(args.to, svc.port)
            try:
                serve_udp(lh, lp, dh, dp, rh, rp)
            except KeyboardInterrupt:
                return 0
            except OSError as exc:
                print(f"mcp-host-bridge failed: {exc}", file=sys.stderr)
                return 1
            return 0
        if not args.to:
            parser.error("--to is required for a TCP service")
        th, tp = split_hostport(args.to, svc.port)
        try:
            serve(lh, lp, th, tp, args.timeout)
        except KeyboardInterrupt:
            return 0
        except OSError as exc:
            print(f"mcp-host-bridge failed: {exc}", file=sys.stderr)
            return 1
        return 0

    if cmd == "install":
        if svc.protocol == "udp":
            return installer.install(
                name, lh, lp, "udp", deliver_host=dh, deliver_port=dp, probe=None
            )
        if not args.to:
            parser.error("--to is required for a TCP service")
        th, tp = split_hostport(args.to, svc.port)
        return installer.install(
            name, lh, lp, "tcp", target_host=th, target_port=tp, probe=svc.probe
        )

    if cmd == "uninstall":
        return installer.uninstall(name, lh, lp)

    if cmd == "status":
        return installer.status(
            name, lh, lp, svc.protocol, deliver_host=dh, deliver_port=dp, probe=svc.probe
        )

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
