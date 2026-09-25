"""Keep the home server on the private home network.

Requests from public addresses are refused, and the Host header must name this
computer, localhost or a private IP address (which blocks DNS-rebinding pages
on the internet from reaching the server through a family browser).
"""
from __future__ import annotations

import ipaddress
import json
import socket


def _address(value: str | None):
    if not value:
        return None
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped
    return address


def is_loopback(value: str | None) -> bool:
    address = _address(value)
    return bool(address and address.is_loopback)


def is_private(value: str | None) -> bool:
    address = _address(value)
    if address is None:
        return False
    if address.is_loopback or address.is_link_local:
        return True
    if isinstance(address, ipaddress.IPv4Address):
        return any(address in ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
    return address in ipaddress.ip_network("fc00::/7")


def allowed_host(host_header: str | None, extra: list[str] | tuple[str, ...] = ()) -> bool:
    if not host_header:
        return False
    host = host_header.strip().lower()
    if host.startswith("["):
        host = host[1:host.find("]")]
    elif host.count(":") == 1:
        host = host.rsplit(":", 1)[0]
    if is_private(host):
        return True
    names = {"localhost", socket.gethostname().lower(), f"{socket.gethostname().lower()}.local", "testserver",
             *(e.lower() for e in extra)}
    return host in names


class PrivateNetworkMiddleware:
    def __init__(self, app, extra_hosts=()):
        self.app = app
        self.extra_hosts = tuple(extra_hosts)

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        client = (scope.get("client") or (None,))[0]
        headers = dict(scope.get("headers") or [])
        host = headers.get(b"host", b"").decode("latin-1")
        if client != "testclient" and not is_private(client):
            return await _deny(send, "This server only accepts devices on the home network")
        if not allowed_host(host, self.extra_hosts):
            return await _deny(send, "Unrecognised server address")
        return await self.app(scope, receive, send)


async def _deny(send, message):
    body = json.dumps({"detail": message}).encode()
    await send({"type": "http.response.start", "status": 403,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})
