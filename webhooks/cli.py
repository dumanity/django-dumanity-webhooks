import argparse
import json
from types import SimpleNamespace

from webhooks import __version__
from webhooks.producer.services import probe_connection


def _print_test_endpoint_summary(result: dict) -> None:
    ok = bool(result.get("ok"))
    status_code = result.get("status_code")
    status = result.get("status")
    latency_ms = result.get("latency_ms")

    print("=== webhooks-info: test-endpoint ===")
    print(f"result: {'OK' if ok else 'FAILED'}")
    print(f"http_status: {status_code}")
    print(f"receiver_status: {status}")
    print(f"latency_ms: {latency_ms}")
    print("")
    if ok:
        print("next_steps:")
        print("- Endpoint accepts signed traffic.")
        print("- Proceed with real event publishing.")
    else:
        print("how_to_fix:")
        print("- Verify URL and network reachability.")
        print("- Verify shared secret and receiver API key.")
        print("- Check receiver logs for signature/rate-limit/integration errors.")
    print("")


def main() -> None:
    parser = argparse.ArgumentParser(prog="webhooks-info")
    subparsers = parser.add_subparsers(dest="command")

    test_parser = subparsers.add_parser("test-endpoint", help="Prueba conexión con un receiver")
    test_parser.add_argument("--url", required=True, help="URL del receiver")
    test_parser.add_argument("--secret", required=True, help="Secret HMAC compartido")
    test_parser.add_argument("--api-key", help="API Key del receiver (opcional)")
    test_parser.add_argument("--timeout", type=float, help="Timeout override en segundos")

    args = parser.parse_args()

    if args.command == "test-endpoint":
        endpoint = SimpleNamespace(
            url=args.url,
            secret=args.secret,
            request_timeout_seconds=args.timeout or 10,
        )
        result = probe_connection(
            endpoint=endpoint,
            api_key=args.api_key,
            timeout_seconds=args.timeout,
        )
        _print_test_endpoint_summary(result)
        print(json.dumps(result, indent=2, sort_keys=True))
        raise SystemExit(0 if result.get("ok") else 1)

    print(f"django-dumanity-webhooks {__version__}")


if __name__ == "__main__":
    main()
