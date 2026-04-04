"""
Verificación multi-secret + anti-replay
"""
import time, hmac

def verify(secrets, sig_header, body, tolerance=300):
    if not sig_header:
        return False

    try:
        parts = dict(x.split("=", 1) for x in sig_header.split(","))
        ts = parts["t"]
        sig = parts["v1"]
    except (ValueError, KeyError):
        return False

    if abs(time.time() - int(ts)) > tolerance:
        return False

    for secret in secrets:
        payload = f"{ts}.{body.decode()}".encode()
        expected = hmac.new(secret.encode(), payload, "sha256").hexdigest()

        if hmac.compare_digest(expected, sig):
            return True

    return False