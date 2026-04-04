"""
Cliente HTTP de envío.
"""
import json
import time

import requests

from webhooks.core.signing import sign

def send(endpoint, payload, extra_headers=None, timeout_override=None, correlation_id=None, request_id=None):
    """Envia un webhook firmado usando timeout configurable por endpoint."""
    body = json.dumps(payload).encode()
    ts = str(int(time.time()))

    signature = sign(endpoint.secret, ts, body)

    meta = payload.get("meta") or {}
    resolved_correlation_id = correlation_id or meta.get("correlation_id")
    resolved_request_id = request_id or meta.get("request_id")

    headers = {
        "Webhook-Signature": signature,
        "X-Event-ID": payload["id"]
    }

    if resolved_correlation_id:
        headers["X-Correlation-ID"] = str(resolved_correlation_id)

    if resolved_request_id:
        headers["X-Request-ID"] = str(resolved_request_id)

    if extra_headers:
        headers.update(extra_headers)

    return requests.post(
        endpoint.url,
        data=body,
        headers=headers,
        timeout=timeout_override or endpoint.request_timeout_seconds,
    )