# Changelog

All notable changes to this project are documented here. The format is loosely
based on [Keep a Changelog](https://keepachangelog.com/), and this project aims
to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
