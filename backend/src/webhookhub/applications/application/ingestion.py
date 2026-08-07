import json
from hashlib import sha256
from typing import Any


def canonical_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def payload_digest(payload: dict[str, Any]) -> str:
    return sha256(canonical_payload(payload)).hexdigest()
