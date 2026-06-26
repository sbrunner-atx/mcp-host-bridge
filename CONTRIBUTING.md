# Contributing to mcp-host-bridge

Thanks for your interest! This is an experimental, MIT-licensed utility and
contributions are welcome.

## Development setup

```bash
git clone https://github.com/sbrunner-atx/mcp-host-bridge.git
cd mcp-host-bridge
uv sync
```

- **Lint:** `uv run ruff check .`
- **Test:** `uv run pytest` (no external services required; the end-to-end relay
  test uses an in-process listener on `127.0.0.1`)

## Project layout

```
src/mcp_host_bridge/
  relay.py      # the standard-library TCP relay; also standalone-runnable for `run`
  services.py   # service presets (name->port) + optional ~/.mcp-host-bridge/services.ini
  install.py    # per-OS install/uninstall/status (launchd / systemd / netsh + schtasks)
  cli.py        # argparse CLI; one command everywhere, OS auto-detected
tests/          # unit tests (no real LAN sockets; one localhost end-to-end hop)
```

`relay.py` is intentionally free of intra-package imports so the installer can
copy that single file to a stable path and the background service never depends
on a venv or `$PATH`.

## Guidelines

- **Keep the runtime standard-library only.** The point is a tiny, trustworthy
  relay with nothing to audit. Third-party tools (PyInstaller, ruff, pytest) are
  dev/build-only.
- **Keep it a dumb, secure byte relay** — no auth or crypto. It is for trusted
  LANs only, like the underlying device APIs (N3FJP, fldigi). Document that
  clearly; don't add a security surface.
- **Stay MCP-agnostic.** This solves a *client-environment* problem (sandboxing),
  not anything about a specific MCP server. No server-specific behavior creeps in
  beyond the optional preset table.
- Run `ruff` and `pytest` before opening a PR; CI runs them on 3.10–3.12.
- Test OS-specific install paths on the real OS where you can (the Windows
  `netsh portproxy` path in particular).

## License

By contributing you agree that your contributions are licensed under the
project's [MIT License](LICENSE).
