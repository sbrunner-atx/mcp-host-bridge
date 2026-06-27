"""Service-preset resolution and the optional config file."""

from __future__ import annotations

import pytest

from mcp_host_bridge import services


def test_builtin_presets_present():
    svcs = services.all_services(path="/nonexistent/services.ini")
    assert svcs["n3fjp"].port == 1100
    assert svcs["n3fjp"].protocol == "tcp"
    assert svcs["fldigi"].port == 7362
    assert svcs["wsjtx"].port == 2237
    assert svcs["wsjtx"].protocol == "udp"
    assert svcs["wsjtx"].probe is None


def test_resolve_udp_preset_keeps_protocol_on_port_override():
    svc = services.resolve("wsjtx", 3000, path="/nonexistent.ini")
    assert svc.protocol == "udp"
    assert svc.port == 3000


def test_resolve_known_preset():
    svc = services.resolve("n3fjp", None, path="/nonexistent.ini")
    assert svc.name == "n3fjp"
    assert svc.port == 1100
    assert svc.probe is not None


def test_resolve_preset_with_port_override():
    svc = services.resolve("n3fjp", 1200, path="/nonexistent.ini")
    assert svc.port == 1200
    assert svc.name == "n3fjp"


def test_resolve_custom_service_needs_port():
    svc = services.resolve("myapp", 5000, path="/nonexistent.ini")
    assert svc.name == "myapp"
    assert svc.port == 5000


def test_resolve_unknown_without_port_errors():
    with pytest.raises(ValueError):
        services.resolve("bogus", None, path="/nonexistent.ini")


def test_user_config_overlays_and_extends(tmp_path):
    cfg = tmp_path / "services.ini"
    cfg.write_text("[services]\nflrig = 12345\nfldigi = 9999\n")
    svcs = services.all_services(path=str(cfg))
    assert svcs["flrig"].port == 12345          # added
    assert svcs["fldigi"].port == 9999          # user overrides built-in
    assert svcs["n3fjp"].port == 1100           # built-in still present

    resolved = services.resolve("flrig", None, path=str(cfg))
    assert resolved.port == 12345


def test_config_round_trips_protocol(tmp_path):
    cfg = tmp_path / "services.ini"
    cfg.write_text("[services]\nmyudp = 9000 udp\nmycomma = 9001,udp\nmytcp = 9002\n")
    svcs = services.all_services(path=str(cfg))
    assert svcs["myudp"].protocol == "udp"
    assert svcs["mycomma"].protocol == "udp"
    assert svcs["mytcp"].protocol == "tcp"
    assert svcs["myudp"].port == 9000


def test_malformed_config_is_ignored(tmp_path):
    cfg = tmp_path / "services.ini"
    cfg.write_text("[services]\nbad = not-a-number\ngood = 4242\n")
    svcs = services.all_services(path=str(cfg))
    assert "bad" not in svcs
    assert svcs["good"].port == 4242
