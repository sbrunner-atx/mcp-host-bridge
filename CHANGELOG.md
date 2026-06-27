# Changelog

All notable changes to this project are documented here. The format is loosely
based on [Keep a Changelog](https://keepachangelog.com/), and this project aims
to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.1] - 2026-06-27

Bug-fix release. Fixes the UDP service when run from the **standalone binary**
(found while testing on real Windows: the v0.2.0 binaries forward TCP but the
installed UDP service failed to start).

### Fixed
- The frozen-binary entry point (`cli.main`) now accepts the bare relay-style
  invocations the installer generates — `run --udp --listen … --deliver …` and
  `run --to … --listen …` without a preset name. Previously only the Python
  `relay.py` path understood those, so binary installs of a UDP service (and TCP
  services that actually run the relay) failed with "unrecognized arguments". The
  new `run --udp` flag forces UDP mode with explicit addresses.
- Windows: `schtasks /Create` now falls back to `/RU SYSTEM` when an `ONLOGON`
  task can't be mapped to a user (service/SYSTEM contexts), instead of failing.

## [0.2.0] - 2026-06-26

Adds **UDP relay support** alongside the existing TCP relay, so connectionless,
bidirectional services (WSJT-X) can be bridged the same way. The TCP path is
unchanged.

### Added
- `serve_udp` relay for connectionless, bidirectional UDP: one LAN-facing socket
  and one loopback socket, with the remote peer auto-learned from the first
  inbound datagram (or pinned via `--to`).
- Built-in **`wsjtx`** preset (UDP, port 2237). `install wsjtx --to <rig>` listens
  on `0.0.0.0:2237` and delivers to `127.0.0.1:2238`.
- `protocol` field on service presets; the optional `services.ini` accepts
  `name = port udp` (or `port,udp`) while `name = port` stays TCP.
- `run --udp` / `--deliver` on the relay, and `--deliver` on the CLI. UDP listen
  defaults to `0.0.0.0:<port>`, deliver to `127.0.0.1:<port+1>`.
- UDP-appropriate `status` (persistence state + a listen-port-in-use check;
  no meaningless TCP-connect probe).

### Changed
- Windows: `netsh interface portproxy` is TCP-only, so UDP services skip it and
  use the Scheduled-Task-runs-the-relay path directly.

## [0.1.0] - 2026-06-26

Initial experimental release. Extracted and generalized from the forwarder that
previously shipped inside `contest-mcp`.

### Added
- Generic, configurable loopback-to-remote TCP relay (`run` subcommand),
  standard-library only at runtime.
- Service presets so a name + an IP is all that's needed:
  `mcp-host-bridge install n3fjp --to <ip>` / `... fldigi --to <ip>`.
  Built-in presets: **n3fjp** (1100), **fldigi** (7362).
- Optional user preset file `~/.mcp-host-bridge/services.ini` (absence is fine).
- Custom services via `--port` / `--name`; multiple bridges coexist.
- Cross-platform persistence with one uniform command set
  (`install` / `uninstall` / `status` / `list-services`):
  - macOS: launchd LaunchAgent.
  - Windows: native `netsh interface portproxy` (no Python required), with a
    Scheduled Task running the relay as a fallback.
  - Linux: systemd `--user` service.
- Frozen-binary aware: when run as a downloaded single-file executable the
  service invokes that binary directly (no Python on the box).
- Auto-migration of the legacy `com.contest-mcp.forward` launchd agent when a
  bridge takes over loopback port 1100.
- Connectivity probe (generic TCP connect; preset-specific handshake for n3fjp).

### Notes
- v0.1 binaries are **unsigned**; see the README for the macOS Gatekeeper and
  Windows SmartScreen workarounds.
