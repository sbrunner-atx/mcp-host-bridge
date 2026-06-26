"""Per-OS install / uninstall / status for a bridge instance.

The user runs the *same* command everywhere; this module detects the OS and picks
the backend. Multiple services coexist because every artifact (launchd label,
systemd unit, scheduled task, netsh portproxy entry) is keyed by the service name
and/or its loopback listen port.

Backends:
  * macOS   -> launchd LaunchAgent (per-user, survives reboot)
  * Linux   -> systemd --user service
  * Windows -> ``netsh interface portproxy`` (native, no Python needed) with a
               Scheduled Task running the relay as a fallback.

When running as a frozen PyInstaller binary the installed service invokes the
copied executable directly (no Python on the box required). When running from a
Python install it self-copies the dependency-free ``relay.py`` to a stable
location so the service never depends on a venv or ``$PATH``.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import time

from . import relay
from .services import CONFIG_DIR

# Legacy artifact superseded by this tool (see seed brief / contest-mcp history).
LEGACY_MACOS_LABEL = "com.contest-mcp.forward"
LEGACY_MACOS_LISTEN_PORT = 1100


# --- naming ------------------------------------------------------------------


def macos_label(service: str) -> str:
    return f"com.mcp-host-bridge.{service}"


def systemd_unit(service: str) -> str:
    return f"mcp-host-bridge-{service}.service"


def windows_task(service: str) -> str:
    return f"mcp-host-bridge-{service}"


# --- the stable runner (frozen exe or self-copied relay.py) ------------------


def _stable_python() -> str:
    if sys.platform == "darwin" and os.path.exists("/usr/bin/python3"):
        return "/usr/bin/python3"
    return shutil.which("python3") or shutil.which("python") or sys.executable


def _runner_command(service: str) -> list[str]:
    """Return the argv prefix that launches the relay, copied to a stable path.

    Appended with ``["run", "--to", target, "--listen", listen]`` by callers.
    """
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if getattr(sys, "frozen", False):
        # Running as a single-file binary: copy the exe so deleting the download
        # doesn't break the service.
        suffix = ".exe" if sys.platform == "win32" else ""
        dest = os.path.join(CONFIG_DIR, f"mcp-host-bridge{suffix}")
        if os.path.abspath(sys.executable) != os.path.abspath(dest):
            shutil.copyfile(sys.executable, dest)
            os.chmod(dest, os.stat(dest).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return [dest]
    # Running from Python: self-copy the dependency-free relay module.
    dest = os.path.join(CONFIG_DIR, "relay.py")
    shutil.copyfile(os.path.abspath(relay.__file__), dest)
    return [_stable_python(), dest]


def _run_args(service: str, target: str, listen: str) -> list[str]:
    return _runner_command(service) + ["run", "--to", target, "--listen", listen]


# --- macOS (launchd) ---------------------------------------------------------


def _migrate_legacy_macos(listen_port: int) -> None:
    """Remove the old contest-mcp launchd agent if this bridge takes its port."""
    if listen_port != LEGACY_MACOS_LISTEN_PORT:
        return
    plist = os.path.expanduser(f"~/Library/LaunchAgents/{LEGACY_MACOS_LABEL}.plist")
    if not os.path.exists(plist):
        return
    subprocess.run(["launchctl", "unload", plist], capture_output=True)
    os.remove(plist)
    legacy_dir = os.path.expanduser("~/.contest-mcp")
    legacy_script = os.path.join(legacy_dir, "forward.py")
    if os.path.exists(legacy_script):
        try:
            os.remove(legacy_script)
            if not os.listdir(legacy_dir):
                os.rmdir(legacy_dir)
        except OSError:
            pass
    print(f"Migrated: removed legacy agent {LEGACY_MACOS_LABEL} (replaced by this bridge).")


def _install_macos(service: str, target: str, listen: str, listen_port: int) -> int:
    _migrate_legacy_macos(listen_port)
    label = macos_label(service)
    plist = os.path.expanduser(f"~/Library/LaunchAgents/{label}.plist")
    os.makedirs(os.path.dirname(plist), exist_ok=True)
    args = "".join(
        f"        <string>{a}</string>\n" for a in _run_args(service, target, listen)
    )
    plist_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n<dict>\n'
        f"    <key>Label</key><string>{label}</string>\n"
        "    <key>ProgramArguments</key>\n    <array>\n"
        f"{args}    </array>\n"
        "    <key>RunAtLoad</key><true/>\n"
        "    <key>KeepAlive</key><true/>\n"
        f"    <key>StandardOutPath</key><string>/tmp/mcp-host-bridge-{service}.log</string>\n"
        f"    <key>StandardErrorPath</key><string>/tmp/mcp-host-bridge-{service}.err</string>\n"
        "</dict>\n</plist>\n"
    )
    with open(plist, "w") as fh:
        fh.write(plist_xml)
    subprocess.run(["launchctl", "unload", plist], capture_output=True)
    subprocess.run(["launchctl", "load", plist], capture_output=True)
    print(f"Installed launchd agent {label}\n  plist: {plist}")
    return 0


def _uninstall_macos(service: str) -> int:
    label = macos_label(service)
    plist = os.path.expanduser(f"~/Library/LaunchAgents/{label}.plist")
    subprocess.run(["launchctl", "unload", plist], capture_output=True)
    if os.path.exists(plist):
        os.remove(plist)
    print(f"Removed launchd agent {label}.")
    return 0


def _status_macos(service: str) -> str:
    label = macos_label(service)
    out = subprocess.run(["launchctl", "list"], capture_output=True, text=True).stdout
    running = any(label in line for line in out.splitlines())
    return f"launchd agent {label}: {'loaded' if running else 'not loaded'}"


# --- Linux (systemd --user) --------------------------------------------------


def _install_linux(service: str, target: str, listen: str, listen_port: int) -> int:
    unit_dir = os.path.expanduser("~/.config/systemd/user")
    os.makedirs(unit_dir, exist_ok=True)
    unit_name = systemd_unit(service)
    unit = os.path.join(unit_dir, unit_name)
    exec_start = " ".join(_run_args(service, target, listen))
    with open(unit, "w") as fh:
        fh.write(
            f"[Unit]\nDescription=mcp-host-bridge loopback relay ({service})\n\n"
            f"[Service]\nExecStart={exec_start}\nRestart=always\n\n"
            "[Install]\nWantedBy=default.target\n"
        )
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", unit_name], capture_output=True)
    print(f"Installed systemd --user service {unit_name}\n  unit: {unit}")
    return 0


def _uninstall_linux(service: str) -> int:
    unit_name = systemd_unit(service)
    subprocess.run(["systemctl", "--user", "disable", "--now", unit_name], capture_output=True)
    unit = os.path.expanduser(f"~/.config/systemd/user/{unit_name}")
    if os.path.exists(unit):
        os.remove(unit)
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    print(f"Removed systemd --user service {unit_name}.")
    return 0


def _status_linux(service: str) -> str:
    unit_name = systemd_unit(service)
    rc = subprocess.run(
        ["systemctl", "--user", "is-active", unit_name], capture_output=True, text=True
    )
    return f"systemd --user {unit_name}: {rc.stdout.strip() or 'unknown'}"


# --- Windows (netsh portproxy, Scheduled Task fallback) ----------------------


def _netsh_add(listen_host: str, listen_port: int, target_host: str, target_port: int) -> bool:
    rc = subprocess.run(
        [
            "netsh", "interface", "portproxy", "add", "v4tov4",
            f"listenaddress={listen_host}", f"listenport={listen_port}",
            f"connectaddress={target_host}", f"connectport={target_port}",
        ],
        capture_output=True, text=True,
    )
    return rc.returncode == 0


def _netsh_delete(listen_host: str, listen_port: int) -> None:
    subprocess.run(
        [
            "netsh", "interface", "portproxy", "delete", "v4tov4",
            f"listenaddress={listen_host}", f"listenport={listen_port}",
        ],
        capture_output=True, text=True,
    )


def _install_windows_task(service: str, target: str, listen: str) -> int:
    tn = windows_task(service)
    cmd = " ".join(f'"{a}"' if " " in a else a for a in _run_args(service, target, listen))
    rc = subprocess.run(
        ["schtasks", "/Create", "/TN", tn, "/TR", cmd, "/SC", "ONLOGON", "/F"],
        capture_output=True, text=True,
    )
    if rc.returncode == 0:
        subprocess.run(["schtasks", "/Run", "/TN", tn], capture_output=True)
        print(f"Installed scheduled task '{tn}' (runs at logon).")
        return 0
    print(
        "Could not set up persistence automatically. Run this in a terminal and "
        "leave it open, or add it to startup:\n  " + cmd
    )
    return 1


def _install_windows(
    service: str,
    target: str,
    listen: str,
    listen_host: str,
    listen_port: int,
    target_host: str,
    target_port: int,
) -> int:
    # Prefer native netsh portproxy: persistent, no Python dependency.
    if _netsh_add(listen_host, listen_port, target_host, target_port):
        print(
            f"Installed netsh portproxy: {listen_host}:{listen_port} -> "
            f"{target_host}:{target_port} (native, survives reboot)."
        )
        return 0
    print("netsh portproxy unavailable; falling back to a Scheduled Task running the relay.")
    return _install_windows_task(service, target, listen)


def _uninstall_windows(service: str, listen_host: str, listen_port: int) -> int:
    _netsh_delete(listen_host, listen_port)
    tn = windows_task(service)
    subprocess.run(["schtasks", "/End", "/TN", tn], capture_output=True)
    subprocess.run(["schtasks", "/Delete", "/TN", tn, "/F"], capture_output=True)
    print(f"Removed netsh portproxy entry and scheduled task '{tn}' (whichever was present).")
    return 0


def _status_windows(service: str, listen_host: str, listen_port: int) -> str:
    out = subprocess.run(
        ["netsh", "interface", "portproxy", "show", "v4tov4"], capture_output=True, text=True
    ).stdout
    has_proxy = any(str(listen_port) in line and listen_host in line for line in out.splitlines())
    tn = windows_task(service)
    task = subprocess.run(["schtasks", "/Query", "/TN", tn], capture_output=True, text=True)
    has_task = task.returncode == 0
    bits = []
    if has_proxy:
        bits.append("netsh portproxy: present")
    if has_task:
        bits.append(f"scheduled task '{tn}': present")
    return ", ".join(bits) if bits else "no persistence entry found"


# --- public dispatch ---------------------------------------------------------


def install(
    service: str,
    listen_host: str,
    listen_port: int,
    target_host: str,
    target_port: int,
    probe: tuple[bytes, bytes] | None = None,
) -> int:
    target = f"{target_host}:{target_port}"
    listen = f"{listen_host}:{listen_port}"
    if sys.platform == "darwin":
        rc = _install_macos(service, target, listen, listen_port)
    elif sys.platform == "win32":
        rc = _install_windows(
            service, target, listen, listen_host, listen_port, target_host, target_port
        )
    else:
        rc = _install_linux(service, target, listen, listen_port)
    if rc == 0:
        _next_steps(service, listen_host, listen_port, probe)
    return rc


def uninstall(service: str, listen_host: str, listen_port: int) -> int:
    if sys.platform == "darwin":
        return _uninstall_macos(service)
    if sys.platform == "win32":
        return _uninstall_windows(service, listen_host, listen_port)
    return _uninstall_linux(service)


def status(
    service: str,
    listen_host: str,
    listen_port: int,
    probe: tuple[bytes, bytes] | None = None,
) -> int:
    if sys.platform == "darwin":
        state = _status_macos(service)
    elif sys.platform == "win32":
        state = _status_windows(service, listen_host, listen_port)
    else:
        state = _status_linux(service)
    print(f"Service '{service}'  ({listen_host}:{listen_port})")
    print(f"  persistence: {state}")
    payload, expect = (probe or (None, None))
    print(f"  probe: {relay.probe(listen_host, listen_port, payload, expect)}")
    return 0


def _next_steps(
    service: str,
    listen_host: str,
    listen_port: int,
    probe: tuple[bytes, bytes] | None,
) -> None:
    print(
        "\nNext steps:\n"
        f"  1. In the MCP connector settings, set the {service} host to {listen_host} "
        f"(port {listen_port}).\n"
        "  2. Save, then fully quit and reopen the MCP client (e.g. Cmd-Q / Alt-F4).\n"
        f"  3. Ask for the {service} status to confirm.\n"
    )
    time.sleep(1.5)  # let a just-started service bind before probing
    payload, expect = (probe or (None, None))
    print(f"Probe: {relay.probe(listen_host, listen_port, payload, expect)}")
