"""
Cliente HTTP de envío.
"""
import json
import time

import requests

from webhooks.core.signing import sign

def send(endpoint, payload, extra_headers=None, timeout_override=None):
    """Envia un webhook firmado usando timeout configurable por endpoint."""
    body = json.dumps(payload).encode()
    ts = str(int(time.time()))

    signature = sign(endpoint.secret, ts, body)

    headers = {
        "Webhook-Signature": signature,
        "X-Event-ID": payload["id"]
    }

    if extra_headers:
        headers.update(extra_headers)

    return requests.post(
        endpoint.url,
        data=body,
        headers=headers,
        timeout=timeout_override or endpoint.request_timeout_seconds,
    )