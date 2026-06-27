# mcp-host-bridge

A tiny, configurable **loopback-to-remote TCP/UDP relay** so a sandboxed MCP
client can reach a service running on **another computer**.

[![CI](https://github.com/sbrunner-atx/mcp-host-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/sbrunner-atx/mcp-host-bridge/actions/workflows/ci.yml)
&nbsp;MIT licensed &nbsp;·&nbsp; standard-library only at runtime

```
mcp-host-bridge install n3fjp  --to 192.168.1.50      # TCP  127.0.0.1:1100 -> 192.168.1.50:1100
mcp-host-bridge install fldigi --to 192.168.1.50      # TCP  127.0.0.1:7362 -> 192.168.1.50:7362
mcp-host-bridge install wsjtx  --to 192.168.1.111     # UDP  0.0.0.0:2237  -> deliver 127.0.0.1:2238
```

---

## The problem this solves

Some MCP clients — **Claude Desktop** is the notable one — run their connectors
**sandboxed so the connector can only reach `127.0.0.1` (loopback), not LAN
addresses** (the private `10.x` / `172.16–31.x` / `192.168.x` ranges are blocked).
This holds even with macOS Local Network permission turned on; it is a deliberate
security boundary, not a bug.

So if you run a *local* MCP server (for example one that talks to a logging or
radio program over TCP) and point it at a **LAN IP** for the device, the
connector **times out** — even though `telnet`/Terminal on the same machine reach
that IP fine. Most MCP servers never hit this because they reach the *public
internet* or a hosted cloud; reaching a **private LAN device from a sandboxed
local connector** is the rare, blocked case.

**The fix:** run a small TCP relay *outside* the sandbox on the same machine as
the MCP client. It listens on loopback and forwards to the remote service. You
point the connector at `127.0.0.1`, and the relay does the LAN hop.

```
  ┌────────────────────┐        ┌──────────────────┐        ┌──────────────────┐
  │  MCP client         │  loop  │  mcp-host-bridge │  LAN   │  remote service  │
  │  (sandboxed)        │ ─────▶ │  127.0.0.1:PORT  │ ─────▶ │  192.168.x.x:PORT│
  └────────────────────┘  back  └──────────────────┘        └──────────────────┘
```

This is a **client-environment** workaround, not anything specific to a given MCP
server — which is exactly why it lives in its own generic tool instead of inside
any one server.

## Install

### Download a binary (no Python needed)

Grab the single file for your OS from the
[latest release](https://github.com/sbrunner-atx/mcp-host-bridge/releases):
`mcp-host-bridge-macos`, `mcp-host-bridge.exe`, or `mcp-host-bridge-linux`. Then
run the one command (see below).

> The v0.1 binaries are **unsigned**. See
> [Unsigned-binary notes](#unsigned-binary-notes) to get past Gatekeeper / SmartScreen.

### Or with Python

```bash
pipx install mcp-host-bridge      # or: uvx mcp-host-bridge ...
# or from source:
git clone https://github.com/sbrunner-atx/mcp-host-bridge.git
cd mcp-host-bridge && uv sync && uv run mcp-host-bridge --help
```

## Usage

Run it on the **same computer as your MCP client**.

```bash
# Persistent service (survives reboot), using a built-in preset:
mcp-host-bridge install n3fjp  --to 192.168.1.50
mcp-host-bridge install fldigi --to 192.168.1.50

# A custom app with no preset — just give it a port:
mcp-host-bridge install myapp  --port 5000 --to 192.168.1.9

# Check it / test the connection:
mcp-host-bridge status n3fjp

# Remove it:
mcp-host-bridge uninstall n3fjp

# Run in the foreground instead of installing a service:
mcp-host-bridge run n3fjp --to 192.168.1.50

# See known presets:
mcp-host-bridge list-services
```

Then in the MCP connector settings, set the service host to **`127.0.0.1`**, save,
and fully quit + reopen the client.

### UDP services (WSJT-X)

Some services speak **UDP**, which is connectionless and *bidirectional* — the
remote app broadcasts datagrams *in*, and control replies must return to whatever
address each datagram came from. The topology is therefore inverted versus TCP, so
UDP uses a `--listen` (LAN-facing) + `--deliver` (loopback) model instead of
`--listen` + `--to`:

```
  remote WSJT-X            bridge host                      wsjtx-mcp (loopback only)
  UDP Server =     ──►  --listen 0.0.0.0:2237   ──►   --deliver 127.0.0.1:2238
  <bridge-LAN-IP>:2237  (LAN socket)                  WSJTX_HOST/PORT = 127.0.0.1:2238
  control replies  ◄──  routed back to the datagram's source (auto-learned)
```

```bash
mcp-host-bridge install wsjtx --to 192.168.1.111   # --to is an optional hint; the
                                                   # remote peer is auto-learned
```

This listens on `0.0.0.0:2237` (where the remote WSJT-X sends) and delivers to
`127.0.0.1:2238` (where the MCP server listens). Then set the MCP server's host to
`127.0.0.1` port `2238`, and point WSJT-X's **UDP Server** at this host's LAN IP,
port `2237`. Override either side with `--listen` / `--deliver` if needed.

The same `install` / `uninstall` / `status` commands work on every OS — the tool
detects the platform and picks the backend. You never edit a plist or run `netsh`
by hand.

### Options

| Flag | Meaning |
|------|---------|
| `--to HOST[:PORT]` | Remote host (or `host:port`). Port defaults to the preset's port. |
| `--port N` | Define or override the service port. |
| `--listen HOST:PORT` | Local address to listen on (default `127.0.0.1:<port>`). |
| `--name LABEL` | Instance label (defaults to the service name). |

Multiple bridges coexist (n3fjp and fldigi side by side) — the service name is
the instance key.

### Service presets

Built-in: **`n3fjp` = 1100** (TCP), **`fldigi` = 7362** (TCP),
**`wsjtx` = 2237** (UDP). Add your own (optional) in
`~/.mcp-host-bridge/services.ini` — `name = port` is TCP, `name = port udp`
(or `port,udp`) is UDP:

```ini
[services]
flrig = 12345
mybeacon = 9000 udp
```

The file is optional; absence is fine. User entries override built-ins.

## How persistence works per OS

| OS | Backend | Notes |
|----|---------|-------|
| macOS | launchd LaunchAgent | per-user, `RunAtLoad` + `KeepAlive`. |
| Windows | `netsh interface portproxy` (TCP) | native, **no Python required**, persistent. UDP services use a Scheduled Task running the relay instead (netsh portproxy is TCP-only); TCP also falls back to a Scheduled Task if `netsh` is unavailable. |
| Linux | systemd `--user` service | `Restart=always`, `WantedBy=default.target`. |

When you run a downloaded binary, the installed service invokes that binary
directly, so the target machine needs no Python at all.

## Built-in OS alternatives

This is a standard networking primitive; if you'd rather not install anything,
the same loopback-to-LAN hop can be done by hand:

- **Windows:** `netsh interface portproxy add v4tov4 listenaddress=127.0.0.1 listenport=1100 connectaddress=192.168.1.50 connectport=1100`
- **macOS / Linux:** `socat TCP-LISTEN:1100,bind=127.0.0.1,fork,reuseaddr TCP:192.168.1.50:1100`
- **Anywhere with SSH:** `ssh -N -L 127.0.0.1:1100:192.168.1.50:1100 user@host`

`mcp-host-bridge` just wraps this in one cross-platform command with presets and
reboot-persistence.

## Unsigned-binary notes

The v0.1 release binaries are not code-signed.

- **macOS (Gatekeeper):** right-click the file → **Open** (once), or strip the
  quarantine flag: `xattr -d com.apple.quarantine ./mcp-host-bridge-macos`.
- **Windows (SmartScreen):** **More info → Run anyway**.

Signing may come in a later release.

## Security / scope

This is a **dumb, secure byte relay**: no authentication, no encryption. Use it
only on a **trusted LAN**, the same trust model as the underlying device APIs it
fronts (N3FJP, fldigi, etc.). It does not modify or inspect traffic.

## License

[MIT](LICENSE) © 2026 Stefan Brunner (AE5VG)
