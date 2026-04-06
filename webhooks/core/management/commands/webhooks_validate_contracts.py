from __future__ import annotations

from collections import defaultdict
import re

from django.core.management.base import BaseCommand, CommandError

from webhooks.core.registry import list_events, validate_event_contract


_VERSIONED_EVENT_TYPE_RE = re.compile(
    r"^(?P<family>[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+)\.v(?P<version>[1-9][0-9]*)$"
)


def _parse_event_type(event_type: str) -> tuple[str, int] | None:
    match = _VERSIONED_EVENT_TYPE_RE.match(event_type)
    if not match:
        return None
    return match.group("family"), int(match.group("version"))


def _required_fields(schema: dict | None) -> set[str]:
    if not isinstance(schema, dict):
        return set()
    required = schema.get("required")
    if not isinstance(required, list):
        return set()
    return {item for item in required if isinstance(item, str)}


class Command(BaseCommand):
    help = "Validate registered webhook contracts and basic version compatibility"

    def handle(self, *args, **options):
        events = list_events()
        errors: list[str] = []
        warnings: list[str] = []

        if not events:
            self.stdout.write(self.style.WARNING("No events are currently registered."))
            self.stdout.write("Tip: ensure your domain app is in INSTALLED_APPS and registry code runs in AppConfig.ready().")
            return

        families: dict[str, list[tuple[int, str, dict]]] = defaultdict(list)
        for event in events:
            event_type = event.get("type", "<missing>")
            contract_errors = validate_event_contract(event)
            for err in contract_errors:
                errors.append(f"{event_type}: {err}")
            parsed = _parse_event_type(event_type) if isinstance(event_type, str) else None
            if parsed:
                family, version = parsed
                families[family].append((version, event_type, event.get("payload_schema") or {}))

        for family, version_rows in families.items():
            ordered = sorted(version_rows, key=lambda item: item[0])
            versions = [row[0] for row in ordered]
            if versions and versions[0] != 1:
                warnings.append(f"{family}: version sequence starts at v{versions[0]} (expected v1)")

            if versions:
                expected = set(range(min(versions), max(versions) + 1))
                missing = sorted(expected.difference(versions))
                if missing:
                    warnings.append(
                        f"{family}: missing intermediate versions -> {', '.join('v' + str(item) for item in missing)}"
                    )

            for prev, nxt in zip(ordered, ordered[1:]):
                prev_required = _required_fields(prev[2])
                next_required = _required_fields(nxt[2])
                removed_required = sorted(prev_required - next_required)
                if removed_required:
                    warnings.append(
                        f"{nxt[1]}: possible compatibility break, required fields removed from previous version -> "
                        f"{', '.join(removed_required)}"
                    )

        if warnings:
            self.stdout.write(self.style.WARNING("Compatibility warnings:"))
            for warning in warnings:
                self.stdout.write(f"- {warning}")

        if errors:
            self.stdout.write(self.style.ERROR("Contract validation failed:"))
            for err in errors:
                self.stdout.write(f"- {err}")
            self.stdout.write("")
            self.stdout.write("How to resolve:")
            self.stdout.write("- Ensure each event defines `type` and `payload_schema`.")
            self.stdout.write("- Use semantic names ending in version suffix (e.g. `orders.created.v1`).")
            self.stdout.write("- Keep payload_schema.type as `object` and required as list.")
            raise CommandError(f"Found {len(errors)} invalid contract issue(s).")

        self.stdout.write(self.style.SUCCESS(f"Contracts valid: {len(events)} event(s) checked."))
