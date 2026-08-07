from collections.abc import Sequence

import pytest

from webhookhub.applications.application.security import (
    UnsafeEndpointError,
    hash_api_key,
    new_api_key,
    validate_endpoint_url,
)


def resolver(*addresses: str):
    async def resolve(_: str, __: int) -> Sequence[str]:
        return addresses

    return resolve


def test_api_keys_are_random_and_only_stored_as_hashes() -> None:
    first = new_api_key()
    second = new_api_key()

    assert first.startswith("whk_")
    assert first != second
    assert hash_api_key(first) != first
    assert len(hash_api_key(first)) == 64


@pytest.mark.asyncio
async def test_public_endpoint_is_normalized() -> None:
    result = await validate_endpoint_url(
        "https://EXAMPLE.com/hooks?source=test", resolver("93.184.216.34")
    )

    assert result == "https://example.com/hooks?source=test"


@pytest.mark.asyncio
async def test_public_ipv6_literal_keeps_url_brackets() -> None:
    result = await validate_endpoint_url("https://[2606:4700:4700::1111]/hook")

    assert result == "https://[2606:4700:4700::1111]/hook"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url,address",
    [
        ("http://localhost/hook", "127.0.0.1"),
        ("http://127.0.0.1/hook", "127.0.0.1"),
        ("http://service.internal/hook", "10.0.0.5"),
        ("http://metadata.test/hook", "169.254.169.254"),
        ("http://ipv6.test/hook", "::1"),
    ],
)
async def test_non_public_endpoints_are_rejected(url: str, address: str) -> None:
    with pytest.raises(UnsafeEndpointError):
        await validate_endpoint_url(url, resolver(address))


@pytest.mark.asyncio
async def test_mixed_public_and_private_dns_answer_is_rejected() -> None:
    with pytest.raises(UnsafeEndpointError):
        await validate_endpoint_url("https://example.com/hook", resolver("8.8.8.8", "10.0.0.1"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/hook",
        "https://user:secret@example.com/hook",
        "https://example.com/hook#fragment",
        "not-a-url",
    ],
)
async def test_malformed_or_unsafe_url_features_are_rejected(url: str) -> None:
    with pytest.raises(UnsafeEndpointError):
        await validate_endpoint_url(url, resolver("8.8.8.8"))
