from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import parse_qsl


def validate_init_data(init_data: str, bot_token: str) -> bool:
    if not init_data:
        return False

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return False

    try:
        auth_date = int(pairs.get("auth_date", "0") or "0")
    except ValueError:
        return False
    if abs(time.time() - auth_date) > 86400:
        return False

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(calculated, received_hash)
