"""Command-line interface for mcp-host-bridge.

One command everywhere; the OS is auto-detected. Subcommands:

    mcp-host-bridge run       n3fjp  --to 192.168.1.50   # foreground
    mcp-host-bridge install   n3fjp  --to 192.168.1.50   # persistent service
    mcp-host-bridge install   fldigi --to 192.168.1.50
    mcp-host-bridge install   myapp  --port 5000 --to 192.168.1.9
    mcp-host-bridge status    n3fjp
    mcp-host-bridge uninstall n3fjp
    mcp-host-bridge list-services
"""

from __future__ import annotations

import argparse
import sys

from . import install as installer
from . import services
from .relay import serve, split_hostport


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp-host-bridge",
        description=(
            "Bridge a loopback-only MCP connector to a service on another host. "
            "Point the connector at 127.0.0.1; this relay does the LAN hop."
        ),
    )
    sub = parser.add_subparsers(dest="cmd")

    def add_target_opts(p: argparse.ArgumentParser, need_to: bool) -> None:
        p.add_argument("service", nargs="?", help="Service preset name (e.g. n3fjp, fldigi).")
        p.add_argument(
            "--to", required=need_to, metavar="HOST[:PORT]",
            help="Remote host (or host:port). Port defaults to the preset's port.",
        )
        p.add_argument("--port", type=int, help="Service port (define/override).")
        p.add_argument("--name", help="Instance label (defaults to the service name).")
        p.add_argument(
            "--listen", metavar="HOST:PORT",
            help="Local address to listen on (default 127.0.0.1:<port>).",
        )

    p_run = sub.add_parser("run", help="Run the relay in the foreground (Ctrl-C to stop).")
    add_target_opts(p_run, need_to=True)
    p_run.add_argument("--timeout", type=float, default=6.0)

    add_target_opts(
        sub.add_parser("install", help="Install + start a service that survives reboot."),
        need_to=True,
    )
    add_target_opts(
        sub.add_parser("uninstall", help="Stop and remove the background service."),
        need_to=False,
    )
    add_target_opts(
        sub.add_parser("status", help="Show the service state and test the connection."),
        need_to=False,
    )
    sub.add_parser("list-services", help="List built-in and user-defined service presets.")
    return parser


def _resolve(args: argparse.Namespace):
    """Return (name, listen_host, listen_port, service) from parsed args."""
    svc = services.resolve(getattr(args, "service", None), getattr(args, "port", None))
    name = getattr(args, "name", None) or svc.name
    if getattr(args, "listen", None):
        lh, lp = split_hostport(args.listen, svc.port)
    else:
        lh, lp = "127.0.0.1", svc.port
    return name, lh, lp, svc


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
        name, lh, lp, svc = _resolve(args)
    except ValueError as exc:
        parser.error(str(exc))

    if cmd == "run":
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
        th, tp = split_hostport(args.to, svc.port)
        return installer.install(name, lh, lp, th, tp, svc.probe)

    if cmd == "uninstall":
        return installer.uninstall(name, lh, lp)

    if cmd == "status":
        return installer.status(name, lh, lp, svc.probe)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
