from __future__ import annotations

import binascii
import hmac
from hashlib import sha256


def verify_hmac(payload: bytes, signature: str, secret: str) -> bool:
    try:
        digest = binascii.unhexlify(signature.strip())
    except (binascii.Error, AttributeError, ValueError):
        return False

    computed = hmac.new(secret.encode("utf-8"), payload, sha256).digest()
    return hmac.compare_digest(computed, digest)
