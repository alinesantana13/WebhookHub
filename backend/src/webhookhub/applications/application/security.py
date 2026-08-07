import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Sequence
from hashlib import sha256
from secrets import token_urlsafe
from urllib.parse import urlsplit, urlunsplit


class UnsafeEndpointError(ValueError):
    """Raised when a webhook destination could reach a non-public network."""


Resolver = Callable[[str, int], Awaitable[Sequence[str]]]


def new_api_key() -> str:
    return f"whk_{token_urlsafe(32)}"


def hash_api_key(value: str) -> str:
    return sha256(value.encode()).hexdigest()


async def _resolve(host: str, port: int) -> Sequence[str]:
    def lookup() -> list[str]:
        return list(
            {str(item[4][0]) for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
        )

    try:
        return await asyncio.to_thread(lookup)
    except socket.gaierror as error:
        raise UnsafeEndpointError("Endpoint host could not be resolved") from error


def _is_public(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return address.is_global


async def validate_endpoint_url(value: str, resolver: Resolver = _resolve) -> str:
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError as error:
        raise UnsafeEndpointError("Invalid endpoint URL") from error
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeEndpointError("Endpoint URL must use HTTP or HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeEndpointError("Endpoint URL must not contain credentials")
    if parsed.fragment:
        raise UnsafeEndpointError("Endpoint URL must not contain a fragment")
    host = parsed.hostname.rstrip(".").casefold()
    if host == "localhost" or host.endswith(".localhost"):
        raise UnsafeEndpointError("Endpoint host must be public")
    resolved_port = port or (443 if parsed.scheme == "https" else 80)
    try:
        addresses = [host] if _is_ip_address(host) else await resolver(host, resolved_port)
    except (ValueError, OSError) as error:
        raise UnsafeEndpointError("Endpoint host could not be resolved") from error
    if not addresses or any(not _is_public(address) for address in addresses):
        raise UnsafeEndpointError("Endpoint host must resolve only to public addresses")
    rendered_host = f"[{host}]" if ":" in host else host
    netloc = rendered_host if port is None else f"{rendered_host}:{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path or "/", parsed.query, ""))


def _is_ip_address(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True
