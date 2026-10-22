from types import SimpleNamespace

from app.access import CodePolicy, IpPolicy


def _req(headers: dict | None = None, peer: str = "10.0.0.9"):
    h = {k.lower(): v for k, v in (headers or {}).items()}
    return SimpleNamespace(headers=h, client=SimpleNamespace(host=peer))


def test_no_allowlist_allows_everyone():
    p = IpPolicy(allowed="", source="auto")
    assert not p.active
    assert p.allows("8.8.8.8")


def test_allowlist_with_cidr_and_single_ip():
    p = IpPolicy(allowed="212.95.1.10, 10.20.0.0/16", source="auto")
    assert p.allows("212.95.1.10")
    assert p.allows("10.20.44.3")
    assert not p.allows("212.95.1.11")
    assert not p.allows(None)
    assert not p.allows("kein-ip")


def test_auto_prefers_cloudflare_header_over_spoofed_xff():
    p = IpPolicy(allowed="212.95.1.10", source="auto")
    req = _req({"X-Forwarded-For": "212.95.1.10, 1.2.3.4", "CF-Connecting-IP": "1.2.3.4"})
    assert p.client_ip(req) == "1.2.3.4"
    assert not p.allows(p.client_ip(req))


def test_xff_first_and_last():
    req = _req({"X-Forwarded-For": "5.5.5.5, 6.6.6.6"})
    assert IpPolicy(allowed="", source="xff-first").client_ip(req) == "5.5.5.5"
    assert IpPolicy(allowed="", source="xff-last").client_ip(req) == "6.6.6.6"
    assert IpPolicy(allowed="", source="peer").client_ip(req) == "10.0.0.9"


def test_ipv6_network():
    p = IpPolicy(allowed="2a01:4f8::/32", source="auto")
    assert p.allows("2a01:4f8:1:2::3")
    assert not p.allows("2a02::1")


def test_code_policy_roundtrip():
    c = CodePolicy(code="studio-2026", secret="geheim")
    assert c.active
    assert c.check_code("studio-2026")
    assert not c.check_code("falsch")
    tok = c.token()
    assert c.check_token(tok)
    assert not c.check_token(tok + "x")
    assert not c.check_token("abc")
    assert not CodePolicy(code="", secret="").active
