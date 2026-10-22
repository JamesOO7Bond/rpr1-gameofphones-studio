"""Zugangsschutz: IP-Sperre plus optionaler Zugangscode.

IP-Sperre (ALLOWED_IPS): Komma-Liste aus IPs oder CIDR-Netzen, z. B.
    "212.95.1.10, 212.95.1.0/24, 2a01:4f8::/32"
Leer = keine IP-Sperre (dann warnt das Dashboard sichtbar).

Woher die Client-IP kommt (CLIENT_IP_SOURCE):
    auto            CF-Connecting-IP → True-Client-IP → X-Forwarded-For (links) → Peer
    cf              nur CF-Connecting-IP (Cloudflare vor Render), sonst Peer
    xff-first       erster Eintrag in X-Forwarded-For (laut Render die Client-IP)
    xff-last        letzter Eintrag in X-Forwarded-For
    peer            direkte Verbindung (nur ohne Proxy sinnvoll)
Mit /whoami lässt sich prüfen, was beim Dienst ankommt.

Zugangscode (ACCESS_CODE): zweites Schloss. Wer den Code einmal eingibt,
bekommt ein signiertes Cookie (COOKIE_SECRET) für 180 Tage.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import time

from starlette.requests import Request

COOKIE_NAME = "gop_zugang"
COOKIE_MAX_AGE = 180 * 24 * 3600


def _parse_networks(raw: str) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    nets = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            continue
    return nets


class IpPolicy:
    def __init__(self, allowed: str | None = None, source: str | None = None) -> None:
        self.networks = _parse_networks(allowed if allowed is not None else os.environ.get("ALLOWED_IPS", ""))
        self.source = (source or os.environ.get("CLIENT_IP_SOURCE", "auto")).strip().lower()

    @property
    def active(self) -> bool:
        return bool(self.networks)

    # ----- Client-IP bestimmen -----------------------------------------
    @staticmethod
    def _first_xff(headers) -> str | None:
        raw = headers.get("x-forwarded-for")
        if not raw:
            return None
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        return parts[0] if parts else None

    @staticmethod
    def _last_xff(headers) -> str | None:
        raw = headers.get("x-forwarded-for")
        if not raw:
            return None
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        return parts[-1] if parts else None

    def client_ip(self, request: Request) -> str | None:
        h = request.headers
        peer = request.client.host if request.client else None
        src = self.source
        if src == "peer":
            return peer
        if src == "cf":
            return h.get("cf-connecting-ip") or peer
        if src == "xff-first":
            return self._first_xff(h) or peer
        if src == "xff-last":
            return self._last_xff(h) or peer
        # auto
        return h.get("cf-connecting-ip") or h.get("true-client-ip") or self._first_xff(h) or peer

    def candidates(self, request: Request) -> dict[str, str | None]:
        h = request.headers
        return {
            "cf-connecting-ip": h.get("cf-connecting-ip"),
            "true-client-ip": h.get("true-client-ip"),
            "x-forwarded-for": h.get("x-forwarded-for"),
            "x-real-ip": h.get("x-real-ip"),
            "peer": request.client.host if request.client else None,
        }

    def allows(self, ip: str | None) -> bool:
        if not self.networks:
            return True
        if not ip:
            return False
        try:
            addr = ipaddress.ip_address(ip.split("%")[0])
        except ValueError:
            return False
        return any(addr in net for net in self.networks)


class CodePolicy:
    def __init__(self, code: str | None = None, secret: str | None = None) -> None:
        self.code = (code if code is not None else os.environ.get("ACCESS_CODE", "")).strip()
        self.secret = (secret if secret is not None else os.environ.get("COOKIE_SECRET", "")).strip() or self.code

    @property
    def active(self) -> bool:
        return bool(self.code)

    def _sign(self, issued: int) -> str:
        msg = f"{issued}".encode()
        return hmac.new(self.secret.encode(), msg, hashlib.sha256).hexdigest()

    def token(self) -> str:
        issued = int(time.time())
        return f"{issued}.{self._sign(issued)}"

    def check_token(self, token: str | None) -> bool:
        if not token or "." not in token:
            return False
        issued_s, sig = token.split(".", 1)
        if not issued_s.isdigit():
            return False
        issued = int(issued_s)
        if time.time() - issued > COOKIE_MAX_AGE:
            return False
        return hmac.compare_digest(sig, self._sign(issued))

    def check_code(self, given: str | None) -> bool:
        if not given:
            return False
        return hmac.compare_digest(given.strip(), self.code)
