"""Service presets: the name -> port map, plus an optional user config file.

Ease of use is the point: ``mcp-host-bridge install n3fjp --to 192.168.1.50``
should be all a user needs. The preset name supplies the port *and* doubles as
the instance name. Custom services are still possible with ``--port``.

A built-in dict ships with the tool. Users may optionally add their own presets
in ``~/.mcp-host-bridge/services.ini`` (INI is used rather than TOML because
``tomllib`` is 3.11+ and the runtime must stay standard-library-only on 3.10).
The file is optional; its absence is completely fine.

Example ``services.ini``::

    [services]
    flrig = 12345
    wsjtx = 2237
"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass

CONFIG_DIR = os.path.expanduser("~/.mcp-host-bridge")
CONFIG_FILE = os.path.join(CONFIG_DIR, "services.ini")


@dataclass(frozen=True)
class Service:
    """A named service preset."""

    name: str
    port: int
    description: str = ""
    # Optional handshake the probe can send through the bridge to confirm the
    # remote service actually answers. (payload, expected-substring-in-reply)
    probe: tuple[bytes, bytes] | None = None


# Built-in presets. Keep this short and well-known; users add their own via the
# optional config file or the --port flag.
BUILTIN: dict[str, Service] = {
    "n3fjp": Service(
        "n3fjp",
        1100,
        "N3FJP contest/general logging TCP API",
        probe=(b"<CMD><PROGRAM></CMD>\r\n", b"PROGRAMRESPONSE"),
    ),
    "fldigi": Service("fldigi", 7362, "fldigi XML-RPC interface"),
}


def _load_config(path: str = CONFIG_FILE) -> dict[str, Service]:
    """Read user-defined presets from the optional INI file. Missing file -> {}."""
    if not os.path.exists(path):
        return {}
    parser = configparser.ConfigParser()
    try:
        parser.read(path)
    except configparser.Error:
        return {}
    out: dict[str, Service] = {}
    if parser.has_section("services"):
        for name, value in parser.items("services"):
            try:
                out[name] = Service(name, int(value), "user-defined (services.ini)")
            except ValueError:
                continue
    return out


def all_services(path: str = CONFIG_FILE) -> dict[str, Service]:
    """Built-in presets overlaid with any user-defined ones (user wins)."""
    merged = dict(BUILTIN)
    merged.update(_load_config(path))
    return merged


def resolve(name: str | None, port: int | None, path: str = CONFIG_FILE) -> Service:
    """Turn a service name and/or explicit port into a concrete :class:`Service`.

    Rules:
      * known preset name, no ``--port``      -> the preset
      * known preset name + ``--port``        -> preset port overridden
      * unknown name + ``--port``             -> a custom service on that port
      * unknown name, no ``--port``           -> error (suggest list-services)
    """
    services = all_services(path)
    if name and name in services:
        base = services[name]
        if port is not None:
            return Service(base.name, port, base.description, base.probe)
        return base
    if port is not None:
        return Service(name or f"port{port}", port, "custom")
    known = ", ".join(sorted(services)) or "(none)"
    raise ValueError(
        f"unknown service {name!r}. Use --port to define a custom one, or pick a known "
        f"preset: {known}. Run 'mcp-host-bridge list-services' for details."
    )


def format_list(path: str = CONFIG_FILE) -> str:
    """Human-readable table for the ``list-services`` command."""
    services = all_services(path)
    width = max((len(n) for n in services), default=4)
    lines = ["Available service presets:", ""]
    for name in sorted(services):
        svc = services[name]
        lines.append(f"  {name.ljust(width)}  {svc.port:<6}  {svc.description}")
    lines += [
        "",
        f"Config file (optional): {CONFIG_FILE}",
        "Add your own under a [services] section, e.g.  myrig = 5000",
    ]
    return "\n".join(lines)
