#!/usr/bin/env python3
"""Lean load-test runner for `WebhookView` endpoints.

Sends signed webhook POST requests concurrently and reports latency/error stats.
Designed for single-operator teams: no extra infra required.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from webhooks.core.signing import sign


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = int(round((p / 100.0) * (len(ordered) - 1)))
    return ordered[k]


def build_payload(event_type: str, payload_size: int) -> dict:
    filler = "x" * max(0, payload_size)
    return {
        "id": str(uuid.uuid4()),
        "type": event_type,
        "data": {
            "entity_id": str(uuid.uuid4()),
            "filler": filler,
        },
    }


def send_one(url: str, api_key: str, secret: str, event_type: str, payload_size: int, timeout: float) -> tuple[int, float, str]:
    payload = build_payload(event_type, payload_size)
    body = json.dumps(payload, separators=(",", ":")).encode()
    ts = int(time.time())
    signature = sign(secret=secret, timestamp=ts, body=body)

    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Webhook-Signature": signature,
        "X-Event-ID": payload["id"],
        "Content-Type": "application/json",
    }

    start = time.perf_counter()
    try:
        response = requests.post(url, data=body, headers=headers, timeout=timeout)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return response.status_code, elapsed_ms, ""
    except Exception as exc:  # pylint: disable=broad-except
        elapsed_ms = (time.perf_counter() - start) * 1000
        return 0, elapsed_ms, str(exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a lean load test against a webhook receiver endpoint.")
    parser.add_argument("--url", required=True, help="Receiver URL, e.g. http://localhost:8000/webhooks/")
    parser.add_argument("--api-key", required=True, help="Inbound API key expected by receiver")
    parser.add_argument("--secret", required=True, help="HMAC secret shared with receiver integration")
    parser.add_argument("--requests", type=int, default=200, help="Total requests to send")
    parser.add_argument("--concurrency", type=int, default=20, help="Concurrent workers")
    parser.add_argument("--timeout", type=float, default=5.0, help="HTTP timeout in seconds")
    parser.add_argument("--event-type", default="benchmark.event.v1", help="Event type for generated payload")
    parser.add_argument("--payload-size", type=int, default=128, help="Approx bytes added in `data.filler`")
    args = parser.parse_args()

    total = max(1, args.requests)
    concurrency = max(1, min(args.concurrency, total))

    latencies: list[float] = []
    status_counts: dict[int, int] = {}
    error_count = 0

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(
                send_one,
                args.url,
                args.api_key,
                args.secret,
                args.event_type,
                args.payload_size,
                args.timeout,
            )
            for _ in range(total)
        ]

        for fut in as_completed(futures):
            status, latency_ms, err = fut.result()
            latencies.append(latency_ms)
            status_counts[status] = status_counts.get(status, 0) + 1
            if err:
                error_count += 1

    duration = time.perf_counter() - started
    ok_2xx = sum(count for code, count in status_counts.items() if 200 <= code < 300)
    throughput = total / duration if duration else 0.0

    print("\n=== Load Test Summary ===")
    print(f"URL: {args.url}")
    print(f"Requests: {total}")
    print(f"Concurrency: {concurrency}")
    print(f"Duration: {duration:.2f}s")
    print(f"Throughput: {throughput:.2f} req/s")
    print(f"2xx success: {ok_2xx}/{total} ({(ok_2xx/total)*100:.1f}%)")
    print(f"Errors (transport): {error_count}")
    print("Status counts:", dict(sorted(status_counts.items(), key=lambda item: item[0])))

    if latencies:
        print(f"Latency p50: {percentile(latencies, 50):.2f} ms")
        print(f"Latency p95: {percentile(latencies, 95):.2f} ms")
        print(f"Latency p99: {percentile(latencies, 99):.2f} ms")
        print(f"Latency mean: {statistics.mean(latencies):.2f} ms")


if __name__ == "__main__":
    main()
