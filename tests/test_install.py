"""Install-layer unit tests: naming and command building, no real services touched."""

from __future__ import annotations

import sys

from mcp_host_bridge import install


def test_label_naming_is_per_service():
    assert install.macos_label("n3fjp") == "com.mcp-host-bridge.n3fjp"
    assert install.macos_label("fldigi") == "com.mcp-host-bridge.fldigi"
    assert install.systemd_unit("n3fjp") == "mcp-host-bridge-n3fjp.service"
    assert install.windows_task("fldigi") == "mcp-host-bridge-fldigi"


def test_run_args_from_python_self_copies_relay(tmp_path, monkeypatch):
    monkeypatch.setattr(install, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    args = install._run_args("n3fjp", "192.168.1.50:1100", "127.0.0.1:1100")
    # [python, <copied relay.py>, "run", "--to", target, "--listen", listen]
    assert args[-5:] == ["run", "--to", "192.168.1.50:1100", "--listen", "127.0.0.1:1100"]
    assert args[1].endswith("relay.py")
    assert (tmp_path / "relay.py").exists()


def test_run_args_when_frozen_uses_the_binary(tmp_path, monkeypatch):
    fake_exe = tmp_path / "downloaded" / ("mcp-host-bridge.exe" if sys.platform == "win32"
                                          else "mcp-host-bridge")
    fake_exe.parent.mkdir(parents=True)
    fake_exe.write_bytes(b"#!binary\n")
    monkeypatch.setattr(install, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe), raising=False)
    args = install._run_args("n3fjp", "192.168.1.50:1100", "127.0.0.1:1100")
    # No python interpreter prefix: the binary is invoked directly.
    assert args[0] == str(tmp_path / fake_exe.name)
    assert args[1] == "run"
    assert (tmp_path / fake_exe.name).exists()
